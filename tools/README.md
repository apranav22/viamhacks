[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

# Supporting tools

Run these from the repository root with `python -m tools.<name>`. `sort.py` is the supported robot loop. Follow [AGENTS.md](../AGENTS.md) for every hardware session.

| Tool | Purpose | Effect |
|---|---|---|
| `probe` | Resources, poses, camera formats | Read-only robot RPCs |
| `check_services` | Reference anomaly service and device diagnostics | Read-only inference/benchmark RPCs |
| `screws` | Color part tracking | Cameras/RPCs and local diagnostic logs |
| `overview` | Legacy fixed-camera calibration and feedback diagnostics | `selftest` offline; `watch` read-only; `calibrate --live` moves |
| `motion_probe` | Supervised motion/geometry bring-up | Defaults dry run; `--live` moves |
| `pad_touch` | Touch-measure the pad surface | `--dry` read-only; otherwise moves with operator input |
| `record_pose` | Record a manually positioned destination | Read-only pose RPC; writes local measured config |
| `recover_station` | Retrieve station source/config/model artifacts | Remote reads, local writes; no deployment or activation |
| `still_report` | Still-frame waits per capture (from `runs/<id>/timeline.jsonl`) and picture sharpness vs a baseline run | Offline, read-only |

For example: `python -m tools.motion_probe --help`, `python -m tools.overview selftest`.

Set `VH_AGENT` to your actual tool/model identity when using a calibration command; omitted identity fields remain `unknown`. Calibration notes derive the operator and branch from the current Git checkout.

Calibration reads the same measured grasp settings and obstacle definitions as the sorter. Write the measurement date, method and your identity when recording new calibration. Hardware tools retain their own prerequisites; they are not an unattended demo workflow.

Recovered nut/head-grasp experiments live in `archive/station/` with provenance. They can include temporary lower clearances, gate bypasses and historical imports; they are evidence for a future reviewed fix, not supported launch commands.
