# Context: event, scoring, station, Viam pieces

Sources: the event slides, the reference sheet (version 2026-11-13 08:28, the authority where they differ), module READMEs, and read-only probes of our station through the Viam SDK and app API.

## Schedule

- **Day 1:** hacking 10:30 → 21:00 (lunch 13:00, dinner 18:00).
- **Day 2:** 9:30 resume, lunch 12:30, **15:30 demos and judging**, 17:00 awards.

## How we're scored

One **five-minute run on 6 judge items** (good, defective, and **at least one defect type we've never seen**), then a **five-minute design explanation**.

| Weight | What | What it means for us |
|---|---|---|
| **30%** | Detection precision and recall, **from our own log** | One line per item: number, decision, confidence, timestamp. **No log = no decision or latency points** |
| **30%** | Item ends where we decided to send it | Reliable grasp and place of small fasteners |
| **10%** | Latency: item enters view → arm starts its response | Correct decisions only. **An inspection move counts as the response** (team decision) |
| **10%** | Device placement with a measured reason, shown through diagnostics | `ov-diag` benchmarks + live stats |
| **20%** | Design explanation | What it does, why each choice, what failed, what we'd change |

The slides also mention recovery: the system keeps working when a judge moves an item mid-run. **Reject bin = hold area**, so there are two destinations.

## The station (`armfarm04b`, measured)

| Thing | Fact | Consequence |
|---|---|---|
| Arm | **`viam:ufactory:xArm850`** (not xArm6), 6 joints, 60 deg/s, controller collision detection off | Our obstacles matter |
| Gripper | `viam:ufactory:gripper` (two-finger), frame = arm + 150 mm. `DoCommand {"get":true}` → `pos` 0–850 (≈857 open). **`IsHoldingSomething` works** | Grasp check for recovery comes free |
| `cam` | RealSense D435 on the wrist, 640×480 color + aligned depth, fx≈fy≈605, cx 338, cy 247. **In the frame system as a child of `arm`** | Pixel → world works through `transform_pose` |
| `overview-cam` | Webcam on a stand, 640×480, behind the arm base, ~1 m from the parts at a low angle; parts are 30–60 px; laptops and people in the background | Useful only if moved closer for the presentation step (see ARCHITECTURE) |
| Table | White and uniform. **Surface at world z ≈ −4 mm** | Color segmentation is easy |
| Obstacles | `table`, `wall-front`, `wall-side`, `ceiling` exist (fragment `armfarm-workcell-obstacles`) but are **disabled by our fragment mods**. The table box assumes a −23 mm top | Re-enable before planned motion; set `table-translation` z ≈ −104 |
| Home | `home-pose` joints (deg) [0, 22.6, −50.7, 0, −74.0, 0]; switch position 2 = go, 1 = save current | Home is our survey pose |
| Shell | `ViamShellDanger` fragment → shell service | Our script can run on the station (allowed by staff) |
| Not configured yet | `ov-diag`, mlmodel, anomaly vision service, VLM | Person C's first job |

**Verified on the live station (read-only):**
- **Pixel → world is right.** 31 table pixels seen at an angle (33–47 cm away) all map to world z = −4 ± 5 mm.
- **Survey from home:** the camera looks straight down from z ≈ 636 mm and covers x 112–619, y −297…383 (≈50 × 68 cm) at **1.06 mm/px**. Enough to find parts and their angle; too coarse for tape detail.
- **Segmentation** from the survey view found every zinc part with world XY, size and grasp angle. To fix:
  - Shiny stainless screws and washers are partly missed.
  - Touching parts merge into one blob.
  - The gripper finger is always visible bottom-right; mask it.
- **Depth** at ~17 cm: 67% valid pixels, a bolt reads ~12 mm above the table. That's near the D435's minimum range; look from ≥ 25 cm.
- **Latency from a laptop:** connect 4 s, RPCs 85–230 ms, a color + depth frame 1.1–1.3 s, color-only 15–85 ms. Hence the judged run runs on the station.

**Teleop lessons:**
- `leader_hold: manual` makes the SO-101 leader limp, so hold it the whole time teleop runs.
- `scale 2.5` amplifies any sag.
- A self-collision between the arm base and the claws ends the session.
- The leader logged a servo **voltage** error and serial timeouts once (power or cable?).

## What Viam gives us for Track 3

| Piece | What it does | Our use |
|---|---|---|
| `viam:viam-openvino` → `viam:openvino:mlmodel` | Runs OpenVINO IR / ONNX on `CPU`/`GPU`/`NPU` with an explicit device, precision, cache, request pool and on-device preprocessing. A missing explicit device is a hard failure | `ov-anomaly`: PatchCore on **GPU, f32** |
| → `viam:openvino:diagnostics` | `list_devices`, `get_compiled_properties` (execution device, cache hit), `benchmark` (mean/p50/p90/p99), `stats` (rolling) | The device-placement score |
| `viam-labs:anomalib:vision` 0.1.5 | `GetClassifications` (`anomalous`, conf = score), `GetDetections`, `DoCommand heatmap`, `CaptureAllFromCamera`; default threshold 0.2 | Baseline and heatmaps; our loop sends its own crops |
| `hackathons:anomalib-train` 0.4.0 | Cloud training, ~10 min, ≥10 `normal` (+ ≥4 `anomalous` optional), `model=patchcore\|padim\|stfpm\|efficient_ad\|fastflow`. Export: input `[1,3,S,S]` 0–1 → `pred_score`, `anomaly_map` | Same contract as our local trainer |
| Reference model `fastener-patchcore` v1 / dataset `fastener-anomaly` (`6af5edb82deac4224da1b4cd`, 169 normal + 83 anomalous) | Another station's wrist cam, 256 px | Day-1 baseline. Our machine key can't read the images: `viam dataset export --destination=… --dataset-id=6af5edb82deac4224da1b4cd` from a logged-in account |
| Measured PatchCore 256 px | **GPU f32 23–31 ms, CPU 75–77 ms, NPU 158 ms or no compile**. GPU f16 → empty `anomaly_map` | Placement: GPU f32 |
| `viam:openvino-genai` → `vlm` | Qwen2.5-VL on GPU, `DoCommand ask` with an image | Name the defect, off the critical path |
| `viam:obstacles-pointcloud` (`obstacles-depth`), `viam:detections-to-segments`, `viam-labs:grasp-pose` | Depth → 3D objects → ranked top-down parallel-jaw grasps | Plan B for locating and grasping |
| `erh:vmodutils` | `obstacle`, `obstacle-open-box`, `arm-position-saver`, `multi-arm-position-switch` | Box and bin as obstacles; taught poses |
| `viam:camera-calibration` | ChArUco hand-eye calibration | Only if the XY touch test is off by more than ~3 mm |
