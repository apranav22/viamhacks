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

[claude-code/claude-opus-5-5 · op Pranav · Pranavs-MacBook-Air · pranav/local-work · 15:30]
No arm motion this session (read-only probes and dry runs only; the arm was at the watch pose, someone else driving).
Done: grasp recovery (`grasp.py`, `tests/test_grasp.py`): after the close, lift `lift_check_mm` (20) and classify by
finger position against the part's width from the color look: good / empty / wrong / slipped. Next attempt changes the
likely cause: empty or slipped → 1 mm lower (floor 1 mm) at finger speed 600; wrong → jaws +90°; every 3 failures →
re-find the part (watch pose in sort.py, survey pose in motion_probe.py); give up after 5. Retries re-aim without the
planner (`Mover.reaim`, joint moves in sort.py). Wired into `motion_probe.py` and **sort.py's `pick()`** (Ali: please
review; behaviour on a first-try good grasp is unchanged except the 20 mm lift check before the lift to LIFT_Z).
`screws.detect` now also returns length and width (mm). `AGENTS.md` jaw row corrected: `jaw_offset_deg` is **90** with
the current y-axis `JawFrame` and `vh.kinematics.ik` (0 clamps parts end to end; nuts can't show the difference).
Fixed: the 9921ca9 merge had dropped motion_probe's ProbeTel setup while keeping three tel calls (crashed at start).
Not done: none of the retry path has run on the arm. Gripper force: `get_gripper_torque` returns `{}` here, so not used.
Next: live `motion_probe.py --live --step` and `sort.py --mode collect` on a bolt (not a nut) to see each outcome once.

[claude-code/claude-opus-5-5 · op Pranav · Pranavs-MacBook-Air · pranav/local-work · 15:55]
Merged ali/pipeline (b01706b upright parts, 6a3a607 collect drops) into pranav/local-work; on conflicts Ali's side won
(operator's call). So **sort.py is Ali's version**: its pick() keeps Ali's retry (1 + `retries`, jaws +90° per miss,
held = pos > 30 after the full lift), not grasp.py; the 15:30 entry's "wired into sort.py" no longer holds.
`config/poses.json` gets `retries: 2` back for it. grasp.py stays in motion_probe.py; adopting it in sort.py is Ali's call.
