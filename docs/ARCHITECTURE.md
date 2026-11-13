# Architecture

**One sentence:** a judge places one item; from the home (watch) pose we notice it, move the wrist camera straight above it (the first motion: latency stops), measure it with color + depth, pick it with a shape-specific grasp, check it on the way to the bins in front of a fixed camera, and drop it in the box or the reject bin. Models run in Viam's OpenVINO services on the GPU; geometry is CPU code; nothing is learned from demonstrations.

## The cycle

```
WATCH    arm at home-pose, wrist cam straight down from ~64 cm. Half-resolution segmentation vs an
         empty-table reference (5 ms/frame). "Placed" = item present, no hand at the image border,
         centroid steady for 2 frames.                                   t_appeared, t_stable
HOVER    motion.move("cam", straight down, 260 mm above the item)       t_cmd, t_first_motion (is_moving poll)
LOOK     color + depth close-up: center, top height, long-axis yaw, length, width
         → shape class → grasp recipe        (+ next: initial defect guess on this view)
         L1: item not under the camera → home → WATCH
PICK     open → pre-grasp 80 mm above (planned, table obstacle) → straight descent (linear constraint)
         → grab → holding flag + jaw position.  L2: empty → open → back to HOVER, retry ×2
LIFT     straight up 120 mm
HOME     joint move to home-pose         (next: CHECKPOINT in front of the fixed camera, then DECIDE)
RELEASE  baseline: hold (Enter to open) | putback (put it where it was)
LOG      one judge line per item: runs/<run>/judge.jsonl
```

## Geometry (verified read-only on the station)

- **Pixel → world:** intrinsics from `cam.get_properties()`; cam → world from 4 concurrent `transform_pose` calls (one round trip), cached while the arm is still. Watch pose: ray ∩ table plane (z = −4 mm). Hover: depth.
- **Orientation:** Viam's orientation vector is `R = Rz(lon)·Ry(lat)·Rz(theta)`; it matched the frame system to 1e-4 for `gripper`, `cam`, `arm`. Pointing down: **x-axis heading = 180° − theta, y-axis heading = 90° − theta**. So the wrist angle for any jaw direction is computed (nearest of the two symmetric solutions, never more than a quarter turn).
- **Table obstacle:** passed per move as `world_state` (a box in front of the arm, top 6 mm below the table) for planned moves. The straight descent/lift go without it so the gripper geometry can reach the part. No config change needed.

## Grasp recipes (shape class, not fastener name)

| Class | Rule (from the hover look) | Grasp |
|---|---|---|
| `upright` | height ≥ 25 mm, footprint < 35 mm | across the shank, 15 mm below the top |
| `lying_long` | aspect ≥ 2, height > 7 mm | jaws across the long axis at the center, half height |
| `thin_screw` | aspect ≥ 2, height ≤ 7 mm | same, fingertips 2 mm above the table |
| `nut_flat` | aspect < 1.4, height ≤ 14 mm | across, half height |
| `nut_edge` | aspect ≥ 1.4, height 12–24 mm | across the thin direction |
| `flat_thin` | height ≤ 3.5 mm | **not graspable** top-down (washer) |
| `unknown` | anything else | generic across the narrow side; suspicious (shape defect?) |

Next: catalog of the real kit (length, diameter, head) → type name, per-type thresholds, shape-defect checks; grip bolts by the head so the shank is fully visible.

## Recovery levels

| Level | Event | Handling | Status |
|---|---|---|---|
| L1 | item moved during the approach | hover look re-measures; gone → WATCH | built |
| L2 | grasp missed | holding flag + jaw ≤ 15 → retry from hover ×2 | built |
| L3 | item taken from the gripper in transit | poll holding + jaw at ~10 Hz during moves, `stop()` | next |

## Defect detection (next)

Initial guess from the hover look (top side). Final decision at the **checkpoint**: on the way to the bins the arm stops ~0.3 s with the fingertips pointed at the fixed camera (shows the side that was on the table), plus a ±45° tilt. Reject if any view is anomalous or tape is seen; unsure → reject. PatchCore on the GPU (f32) via `ov-anomaly`.

## Dashboard without latency cost

- The loop sends **fire-and-forget UDP** to `dashboard/server.py` (separate process): small JSON events and the camera's own JPEG bytes (no re-encoding), chunked to 8 KB. Overlays (boxes, axes, jaw lines, map) are numbers drawn in the browser.
- **Measured cost:** 23 µs per event, 74 µs with a frame; identical when the dashboard is down (packets dropped, `sendto` never blocks). The loop reports its own telemetry overhead live.
- The server reassembles frames, streams to browsers (SSE, newest-frame-wins), and records each run to `runs/<run>/dash/` for replay (`--replay`).
- Shows: wrist camera with overlays (live / hover look / reference / height map), cycle state chain with per-state times, latency breakdown (placing / perceive+command / plan+controller start), item measurements and grasp, gripper jaw vs expected, top-down table map, span timeline, loop performance, items table (judge log), events.

## Latency

Watch loop per frame: camera RPC + 5 ms (half-res decode + segmentation, with OpenCV; ~8 ms with scipy only). Telemetry < 0.1 ms. Then `motion.move` planning + controller start, measured as `t_first_motion` by polling `is_moving()`. Run on the station; from a laptop every RPC adds 85–230 ms.

## Code map

| File | What |
|---|---|
| `run.py` | the cycle (`watch`, `pick`, `--live`, `--step`, `--fake`, `--release`) and the judge log |
| `pipeline/config.py` | every constant; env-var overrides; `MEASURE` marks values to calibrate |
| `pipeline/geometry.py` | orientation math, intrinsics, transforms, ray–plane, wrist angle for a jaw heading |
| `pipeline/perception.py` | segmentation, placement tracker, measurement, shape class, grasp recipe |
| `pipeline/station.py` | Viam wrapper: frames, planned/linear moves, first-motion timing, gripper, home, dry run |
| `pipeline/telemetry.py` | UDP telemetry |
| `pipeline/fake.py` | offline station from a real watch-pose image |
| `dashboard/` | server + single-page UI |
| `tests/test_pipeline.py` | offline tests |

## Bring-up before the first live pick (one driver, E-stop in reach)

1. `python run.py watch` with the arm at home: items detected, no false "hand" (tune `MASK_RECTS`, `HAND_PX`).
2. `python run.py pick --live --step`, stop after HOVER: is the item centered in the camera?
3. Continue to pre-grasp (80 mm above): are the jaws across the part? If they're 90° off, set `JAW_AXIS=y`.
4. Measure where the fingertips are relative to the gripper frame → `TCP_TIP_OFFSET_MM`.
5. Full pick per shape class; then `--cycles 6 --release putback` unattended.
