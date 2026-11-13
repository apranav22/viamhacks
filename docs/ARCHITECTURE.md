# Architecture

**One sentence:** the arm surveys from home, moves above each part (that move is the "response" for latency), inspects the top with the wrist camera, picks **every** part, shows its underside to a fixed camera, and then drops it in the box or the reject bin. Models run on the station's GPU through Viam's OpenVINO services; everything geometric is cheap CPU code; nothing is learned from demonstrations.

## Pipeline

```
SURVEY  arm at home-pose, wrist cam looks straight down from ~64 cm (1.06 mm/px)
  │ color frame → segment parts on the white table → world XY + yaw per part    [CPU, ms]
  │ part seen: t_seen
  ▼
INSPECT  move straight above the part at a fixed height (~25 cm)   ← t_first_motion (latency stops)
  │ close-up frame → canonical crop (centered, long axis horizontal, 256×256)
  │ → ov-anomaly (PatchCore, GPU f32, ~25 ms): top score + anomaly map
  │ → tape check (tape-blue hue fraction)
  │ → refined XY + yaw for the grasp
  ▼
PICK     pre-grasp 80 mm above → straight descent → grab → IsHoldingSomething?
  │      no → back to INSPECT (the part moved), retry ×2
  ▼
LIFT ── top view confidently defective? ── yes ──────────────────────────────┐
  │ no                                                                        │
  ▼                                                                           │
PRESENT  taught joint pose: fingertips pointed at the presentation camera     │
  │ 3 views: fingertips at camera (underside), wrist tilted +45°, −45° (sides)│
  │ → fixed-ROI crop → ov-anomaly-present (second PatchCore, GPU f32) + tape  │
  ▼                                                                           │
DECIDE   any view anomalous → reject, else box; confidence → log line ◀──────┘
  ▼
PLACE    taught box / reject pose → open → back to SURVEY
  ▼ (after the arm is moving, never delaying it)
EXPLAIN  VLM on GPU names the defect for the dashboard and the pitch
```

**Timing at 60 deg/s:** about 18–22 s per item, so ~2 min for 6 items out of the 5-minute run. Only the first move counts toward latency. On the station, item seen → arm moving should be ~100–200 ms.

## Why each choice

- **No RL or imitation learning for picking.** The camera measures the part's position and the motion planner computes the joints.
  - A learned policy needs dozens of demonstrations and an hour of training per try.
  - It plans seconds of motion without looking again, and the arm stalls up to 10 s at every gripper change during a policy run.
  - It copes poorly with parts in new positions, which is exactly what recovery tests.
- **Pixel → world:** `X = (u − cx)·d/fx`, `Y = (v − cy)·d/fy`, `Z = d`, then `machine.transform_pose(PoseInFrame("cam", …), "world")`. From the survey height we intersect the pixel's ray with the table plane (z ≈ −4 mm) instead of trusting depth, whose noise is about a fastener's height. Verified flat to ±5 mm.
- **Grasp:**
  - Straight down (`o = (0, 0, −1)`), fingertips a few mm above the table.
  - Jaws across the part's short side: across the shank for bolts, across the flats for nuts.
  - `motion.move(component_name="gripper", …)` so the planner handles the 150 mm tool offset and obstacles.
- **Two looks before the grasp.** The survey gives XY to ±5–10 mm; the close-up gives ±2 mm and the high-resolution crop.
- **Canonical crops.** PatchCore compares patches against memory. Object-centered, orientation-normalized crops at a fixed scale make it react to the part, not to where it lies. A few dozen good examples per fastener type are enough. Crops at exactly the model's input size make the exported graph's resize a no-op, so local, cloud and on-station models score the same.
- **Pick everything + present.** Tape can face the table. After a top-down grasp, the face that was on the table faces out past the fingertips, so **pointing the fingertips at a fixed camera shows exactly the hidden side**.
  - Spinning about the gripper's own axis only rotates the picture.
  - Tilting the wrist ±45° shows the sides.
  - The strip under the fingertips was already seen by the wrist camera.
  - Bonus: the presentation view also confirms the part is really in the gripper.
- **Early exit:** if the top view is already confidently defective, skip presenting.
- **Decision:**
  - Reject if any view is anomalous; unsure → second look → still unsure → reject.
  - Each view's threshold is set from good-part scores, so that **all views together** give few false alarms. More views mean more chances to false-alarm.
  - The tape check is the explanation for known defects; the anomaly model catches the unseen defect type.
- **Device placement:**
  - Both PatchCore models on the GPU in f32 (measured 23–31 ms vs CPU 75 ms vs NPU 158 ms or no compile).
  - The VLM on the GPU, after motion starts.
  - Segmentation, geometry and orchestration on the CPU.
  - NPU candidate: a PaDiM/EfficientAD second opinion in parallel, if it measurably helps.
- **Where code runs:** models in Viam services on the station (measurable by `ov-diag`); the orchestrator on the station via the shell service, since laptop RPCs add 0.5–1.5 s per item.

## The presentation camera

`overview-cam` as it sits now (behind the arm base, ~1 m, low angle, busy background, 640×480) is **not** good enough. To make it work:

1. **Ask staff whether we may move the stand**, then place it so the camera looks at a presentation spot 20–30 cm away, with a **white card behind the spot**.
2. **Test focus and resolution first:** a teammate holds a bolt at 20 / 30 / 40 cm; check sharpness, and try 1280×720 in the webcam config.
3. **Teach the presentation pose as joints** (arm card or `arm-position-saver`), plus ±45° tilt variants. Add the stand as an obstacle.
4. **Lock exposure and white balance if the webcam allows it.** The tape check relies on hue.
5. **Collect data with the arm itself:** pick each good part, present it at the three angles. 10 parts × 3 views × 2 grasps ≈ 60 images in 15 min, then train (local 1 min / cloud 10 min).

## Recovery

- **Never trust old positions:** re-look before every grasp.
- **After grabbing:** `IsHoldingSomething`. Empty → re-locate → retry ×2 → log and continue.
- **Item identity across looks:** nearest blob with matching size, so the log keeps the same item number.
- **Any failed move:** stop, home, re-survey.

## The judge log

One line per item, written when the decision is final:

```json
{"item": 3, "decision": "reject", "confidence": 0.93, "timestamp": "2026-11-14T15:41:07.412-07:00",
 "t_seen": "...", "t_first_motion": "...", "latency_ms": 184, "scores": {"top": 0.31, "under": 0.88, "left": 0.4, "right": 0.35},
 "tape_frac": 0.12, "device": "GPU", "model_top": "...", "model_present": "...", "reason": "underside anomalous + tape"}
```

Timestamps in ms with time zone. The rich per-item run folder (frames, heatmaps, stage timings) feeds the dashboard and the pitch.

## Safety and calibration before any planned motion

1. **Re-enable the table obstacle** at z ≈ −4 mm (top surface). Add the box, the bin and the camera stand as obstacles.
2. **Theta convention test:** one hover to see which gripper rotation lines the jaws up with world x.
3. **Hover test:** 50 mm above a located part, measure the XY error; then 10 mm; then grasp each part type.
4. **One driver at a time**, E-stop within reach.
