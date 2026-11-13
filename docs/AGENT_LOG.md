# Agent log

Append-only. One entry per session or event, newest last, each starting with the identity one-liner from `AGENTS.md`:
`[tool/model · op <human> · <host> · <branch> · HH:MM]`. Log: work started/finished, `ARM: taken` / `ARM: released`,
machine config changes (before → after, how to revert), handoffs.

---

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 13:00–14:30]
Arm sessions (operator go-ahead each time; teleop off, arm-still check before every run): checkpoint search in front of
the webcam, jaw-axis test, 10-view capture sweep holding a socket screw, base sweeps to locate the webcam. Arm left at
home, gripper open. ARM: released.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:26]
CONFIG: `overview-cam` attributes YUYV 640×480 → MJPEG 1920×1080 (30 fps). Full backup:
`sorter/config_backups/before_cam1080_142629.json` on Ali's laptop. Revert: set `format` YUYV, `width_px` 640,
`height_px` 480.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:45]
Wrote `AGENTS.md`, `CLAUDE.md`, this log, `docs/DATA_PLAN.md`. Open: re-measure the webcam (moved to a tripod) and redo
the capture views over the reject compartment; `config/checkpoint.json` is stale until then.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:50]
ARM: taken (Ali: "take the arm, it's all yours"). Teleop off, arm at home. Plan: calibrate the raised webcam from
fingertip positions (empty gripper, grid over the reject compartment), then re-find the capture views holding a part.
Decision (Ali): reject = the NEAR compartment (x ≈ 245–370), good = far (x ≈ 410–545).

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:55]
Webcam calibrated (DLT from 18 fingertip positions): lens (-101, -206, 347), looking +x, 8° down. Checkpoint over the
reject compartment at TCP (285, -150, 260), 5 views recorded with joints in `config/checkpoint.json`. Picked the taped
socket screw from the pad with Pranav's grasp steps (poses.json unchanged except pick_region limited to the pad) and put
it back. Obstacles in `config/obstacles.json`. Arm at the watch pose over the pad (200, 310, 330), gripper open.
Timing: lift → first view 4.0 s (planner), view → view 0.5–0.75 s, checkpoint → good 7.3 s (planner chose a wrapped
joint-1 config): both long legs must become recorded joint moves.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 15:08]
ARM: still taken. First live run of sort.py (collect mode, the taped nut, 2 reps).

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 15:20]
ARM: taken. sort.py now chimes + says 'Robot arm moving' at run start and pings before each pick/place (team asked).
Collect run: taped hex nut, 3 reps.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 15:20]
sort.py collect mode works end to end: 4 picks of the taped hex nut, each with top + 4 webcam crops, placed back at a
random spot, latency 366-433 ms, cycle 12.5-17 s. Found: the cardboard pad gets pinched and dragged (grasp is 2 mm above
the TABLE); switched to a fixed pick zone on the bare table x 220-450, y 260-395. Releases now wait for the fingers to
open (a nut was carried off once). Warning chime + "Robot arm moving" before every run, ping before each pick/place.
ARM: released (at the watch pose, gripper open).

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 15:40]
ARM: taken. Upright parts: depth height check at a high hover, grasp halfway up, side views pointing down. Collect run: taped thin socket screw, starting upright.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 15:47]
Collect run 152536: 5 picks of a short taped hex bolt standing on its threads (was labelled socket_thin_long; relabelled
hex_bolt_short in decisions.jsonl). Upright threshold 40 -> 15 mm: the 22 mm bolt was gripped as 'lying' and the webcam
only saw its head. ARM: released (watch pose, open); team is arranging parts on the table.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 16:00]
ARM: taken (Ali: go). --refs, then collect: clean long stainless button-head screw, 8 picks.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 16:10]
ARM: taken (Ali: go). Collect: clean long stainless button-head screw, 8 picks, gentle set-down.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T15:44:03]
ARM: taken. Operator confirmed E-stop attended and everyone clear. Collect: clean large socket-head screw, 8 reps, gentle set-downs. sort.py performs teleop and arm-still checks before motion.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T15:48:16]
SAFETY INCIDENT: operator reports using E-stop because an upright bolt contacted the arm/gripper body during descent, preventing jaw closure. No collection process remains active. Upright grasp is NOT verified safe; do not repeat it or reset E-stop automatically. Logs in run 20261113_154405_collect show height estimates of 20–22 mm and 80 mm for the same item over different picks; exact collision cause remains unverified. Operator requests demo continue and debugging deferred: only a separately verified lying-flat path is eligible, not the upright routine. Saved captures still need quality review; do not count every completed cycle as verified training data.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 16:00:20]
ARM: taken for operator-approved lower/centred camera-only test. Teleop off, joints stable; no gripper commands.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 16:00:38]
ARM: released after camera-only test. Returned to starting pose, gripper unchanged. Images: runs/camera_closeup_20261113_160017/. No grasp performed.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T16:24:20]
Done: offline anomaly pipeline (curated pick-level split, frozen ResNet18 PatchCore, OpenVINO IR export/runtime, per-type/pose/view/background keys, conservative fusion) and real-score dashboard replay/heatmaps. No robot connection in training/replay. Five white-background stainless-screw models fitted on 9 picks: 5 train, 2 calibration, 2 test. Both physical-part-independent and real-defect/background holdouts are still missing. One of two held-out clean picks falsely rejected by the wrist model; all 8 webcam test images passed. No threshold tuning to hide that error. Synthetic blue and black marks raised scores (sanity only, not real recall).
Verified: 10 anomaly unit/integration tests + 6 existing pipeline tests, JS syntax, browser score/heatmap rendering and toggle, no browser errors. Replay telemetry mean ~198 us, max ~695 us; CPU per-view scoring observed ~52-61 ms in that replay. GPU/NPU not benchmarked.
Preview correction: screws.detect now supplies part overlays; idle preview hand status is explicitly not evaluated, rather than treating cardboard saturation as a hand. Actual running-loop hand checks untouched.
Keep: motion poses/primitives and teammate site/EDA work left unchanged. Missing models/views reject; source images and local models are preserved and gitignored.
Not done: live inference on robot, upright clearance correction, part masks, rotation normalization, automatic type recognition, matched cardboard/white anomaly comparison.
Next: collect new independent normal and taped/non-blue-defect picks of the same SKU/background at the deployment capture poses; inspect false-positive heatmaps before adding masking or backbone fine-tuning.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T16:56:05]
ARM: taken for user-approved, E-stop-attended camera-only height sweep. Teleop off; arm stable. 380/320/285 mm camera world-z; planned moves with table/walls/ceiling/tripod/lamp/box obstacles. No gripper actuation. Will return to starting watch pose, not issue a new home move.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T16:56:40]
ARM: released. Camera-only sweep completed; returned to starting watch pose within 0.28 mm. Gripper unchanged (no commands); not a home/grasp validation. Images: runs/camera_height_sweep_20261113_165601. No camera configuration changed.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T17:00:03]
CONFIG TEST approved by Ali: back up to config/backup-camera-test-170002.json; test wrist 640x480 -> 1280x720, RGB brightness 0 -> 8 -> 16; gain/exposure unchanged. No motion. Restore original resolution and brightness in finally; do not overwrite other config changes.

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T17:00:36]
CONFIG TEST finished: status=completed, restored=True; wrist resolution back to (640, 480), RGB brightness 0; no motion. Images/report runs/camera_settings_20261113_170001. Restore errors: []

[claude-code/claude-opus-5-5 · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T17:04:55]
CONFIG (approved by Ali): wrist cam resolution (640, 480) -> (1280, 720) via fragment mod; backup config/backup-cam1280-170454.json. Revert: set that mod back to 640/480. RGB brightness -> 8 via v4l2 (not persistent across camera/module restart). No motion.

[claude-code/claude-opus-5-5 · op Ali · Alis-MacBook-Air.local · ali/pipeline · 2026-11-13T17:05:26]
Camera lock test done: final [1280, 720], controls 'brightness: 8\ngain: 64\nwhite_balance_automatic: 1\nauto_exposure: 3 (Aperture Priority Mode)'. Exposure/WB back on auto pending choice. Report runs/camera_lock_20261113_170453.

[claude-code/claude-opus-5-5 · op Ali · Alis-MacBook-Air.local · ali/pipeline · 17:07]
CONFIG (approved by Ali): wrist cam stays 1280x720 (fragment mod; backup config/backup-cam1280-*.json; revert = mod back to
640/480). RGB v4l2: brightness 8, manual exposure 100 (10 ms), auto WB (manual temps gave a red cast). sort.py now applies +
verifies these at run start (set_camera) and records them in each item's meta.json; refuses to run if not 1280x720.
screws.detect scales its pixel constants by frame height/480; sort.zone_px clamps to the real frame size. Offline: detect
finds the same blobs at 640 and 1280 (areas x2.3); tests/test_pipeline.py + anomaly tests pass. No arm motion.

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 17:10]
Took over the Intel-station work from pi/unknown. Added deploy_station.py (chunked, hash-verified releases; shared
runs/ + models/), dashboard speaks/pings for runs from the station (no speaker there), sort.py waits 2.5 s after the
warning off-macOS, upright grasp OFF by default (--allow-upright; 15:48 E-stop), `--type any` pooled training, top
crop border check uses the real frame size (was 640x480-only). Deployed release 20261113_170857. Training
models/any_white_v1 on the station XPU (log /opt/viam/sorter-ali/train_any_white_v1.log). No motion, no config change.
Noted: another claude-code session switched the wrist cam to 1280x720 at 17:04:55 (logged above); depth is aligned at
1280x720 too, so depth_look stays valid; the top-view banks were fitted on 640x480 images and need refitting.
