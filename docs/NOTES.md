# Notes: findings and failures

One line per surprise, newest last. This is raw material for "what failed, what we'd change" in the design explanation.

## Day 1

- **Teleop: both arms "drooped" on start.**
  - `leader_hold: manual` makes the SO-101 leader limp; unheld, it fell, and the follower copied the fall ×2.5.
  - It stopped on a self-collision (arm base vs claws).
  - Fix: hold the leader the whole time, `stop` before letting go.
- **Teleop config pointed at `vacuum-gripper`** (disabled); the station's gripper is `gripper`.
- **The leader logged a servo voltage error and serial timeouts once:** power or cable?
- **The arm is an xArm850, not the xArm6 from the slides.**
- **Table/wall/ceiling obstacles are disabled by our fragment mods, and the table box sits ~19 mm too low** (real surface z ≈ −4 mm).
- **Pixel → world verified:** 31 table points at an angle map to z = −4 ± 5 mm.
- **Home looks straight down from ~64 cm:** ≈50 × 68 cm at 1.06 mm/px. Good for finding parts, too coarse for tape.
- **First segmentation from home:** zinc parts found; stainless parts partly missed; touching parts merge; the gripper finger is always in the bottom-right corner.
- **Laptop → station:** RPCs 85–230 ms, a color+depth frame 1.1–1.3 s, color-only 15–85 ms. Run on the station.
- **Depth at 17 cm is at the D435's limit** (67% valid). A bolt still reads ~12 mm above the table.
- **The machine API key lists the org's datasets but can't download images;** use `viam dataset export` from a logged-in account.
- **Tape can face the table** → pick everything and present the underside to a fixed camera.
- **`overview-cam` is too far and has a busy background for that as placed** → move it closer to a presentation spot (asking staff).
- **From last night's prep (MacBook, offline):**
  - PatchCore coreset 0.01 matches 0.1 in accuracy at a third of the latency.
  - GPU/NPU f16 shifts scores by up to 0.1, so calibrate on the deploy device.
  - OpenVINO's CPU cache ignores the precision hint.
  - A 1B VLM answers from the prompt, not the image; a 4B VLM gets 5/8 and is slow. The VLM explains, it doesn't detect.
- **Run format changed:** one item at a time; the judge may move it during the approach or after the grasp.
- **Bolts can stand upright.** From above an upright bolt looks like a nut; only depth separates them (53 mm vs ~10 mm).
- **A blue-topped nut (nylon-insert lock nut?)** would trip a pure "blue = tape" rule; the anomaly model must learn it as normal.
- **Washers can't be grasped top-down** by the two-finger claw.
- **Orientation math verified:** R = Rz(lon)·Ry(lat)·Rz(theta) matches the frame system to 1e-4; pointing down, x heading = 180° − theta.
- **Without an empty-table reference, a laptop at the image edge looks like a hand.** The run captures a reference at start.
- **Watch-loop perception was 28 ms/frame;** half-resolution decode (JPEG DCT scaling) + OpenCV morphology → 5 ms, same item within 1 px.
- **Telemetry cost measured:** 23 µs/event, 74 µs with a frame, same with the dashboard down.
- **Webcam moved to the back-right corner of the table** (lens ≈ (−40, −196, 25) mm, clamped at the table edge next to the arm base, facing +x at the grey front divider). Located with the wrist RealSense's depth after a base sweep.
- **Checkpoint found and reached live:** TCP (202, −166, 90), tool axis pointing back at the lens, 250 mm away, 15° above it. The part sits against the black claw bar with the divider behind; ~3.5 px/mm. `config/checkpoint.json`.
- **The wrist RealSense can't see a held part:** it projects ~64 px below the image and is ~14 cm away, under the D435 minimum depth. The "opposite" view of the webcam is the hover look before the grasp.
- **The jaws close along the gripper's y axis, not x** (filmed at the checkpoint). `JawFrame` assumed x, so grasps were aimed 90° off: `jaw_offset_deg` 90 → 0.
