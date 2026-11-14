[codex/unknown · op Ali (git: Ali; github: unknown) · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]

# Intel dashboard assessment

Read-only observations at approximately 11:08–11:10 EST on 2026-11-14, through the existing Viam shell. No service stop/restart, file upload/deletion, deployment, camera read, gripper/motion command, machine-config change, or model activation.

## Running interfaces

| Port | Process | Working directory | Assessment |
|---|---|---|---|
| 8765 | PID 341686, old live dashboard | `/tmp/vedant-viamhacks-dashboard` | Old UI; temporary deployment; no shared runs/models links here. |
| 8770 | PID 343830, training dashboard | `/opt/viam/sorter-ali/releases/20261113_172001` | Old training UI, links shared runs/models. |
| 8771 | PID 363746, training/explorer | `/opt/viam/sorter-vedant-explorer/browser-896d886` | Second old training/explorer UI, links shared runs/models. |
| 8775 | PID 360569, isolated live dashboard | `/opt/viam/sorter-ali/dashboard-releases/20261113_193740` | Old UI, shared runs link, no benchmark definitions. |
| 8899 | PID 341800, Python static HTTP server | `/tmp/vedant-viamhacks-dashboard/site` | Older Track 3 static presentation; assess separately from dashboards. |
| 8888 | capture-control | Viam-managed module | Capture infrastructure, not a dashboard replacement target. |
| 8080 | viam-server | Viam-managed runtime | Robot infrastructure; preserve. |

All four dashboard roots answered HTTP successfully but lacked the new Models UI and `/api/models/benchmarks` endpoint. Both Intel live dashboards returned stale pipeline packet ages (approximately 314 s on 8765 and 4512 s on 8775 at first check). These values are a snapshot, not a persistent diagnosis.

## Already deployed, not served

Current robot release: `/opt/viam/sorter-ali/releases/20261114_110630`. All nine inspected dashboard files and `config/benchmarks/development-v1.json` match the laptop byte-for-byte by SHA256. `DASHBOARD_RELEASE` still points to the old November 13 isolated dashboard release. No running process serves the current consolidated UI.

`/opt/viam/sorter-ali/runs/_analysis` contains no top-level replay JSON. The Models view needs the laptop replay artifacts imported, with every source-image hash validated against Intel captures. The candidate model itself is present in `models/codex_curated_20261114_003525`; its model-directory replay is not automatically discovered by the UI.

The new UI is currently read-only model review. It does not replace training/evaluation job launch controls. Preserve CLI training/evaluation tools and their environments when retiring old UI processes.

## Active robot/controller and telemetry

Initial observation: PID 829985 ran a two-pick coverage collection/speed test. Second observation: PID 830479 ran `sort.py --mode collect --views coverage --label good --type hex_bolt_partial --reps 60 ... --dash-host 172.16.0.39`, explicitly using `each_cardboard_v4/bundle_m103.json`. This changing process state means another operator session is working. Do not stop/restart it for dashboard cleanup. No physical arm state was queried.

The destination is the laptop's current IP, 172.16.0.39. Laptop PID 63780 serves port 8765 and listens on UDP 8766. No laptop relay process was found. Laptop review instances also run on 8875/UDP8876 and 8877/UDP8878. Therefore the active run is routed to the laptop, while the Intel live dashboards receive no fresh pipeline traffic. Do not infer controller state from a fresh camera preview. A station-only dashboard needs telemetry directed to its UDP listener in a subsequent coordinated run; changing a web server alone will not fix the route.

## Startup and persistence

`viam-agent.service` is enabled and running. All surveyed dashboard processes are in its cgroup, launched as detached Python processes or children of interactive shells. No dedicated dashboard service unit was found. Restarting viam-agent as a dashboard cleanup action would also affect robot infrastructure and inherited processes; do not do that. A replacement dashboard should have its own explicit startup/stop/rollback ownership.

Root cron runs `/opt/viam/sorter-ali/tools/sync_cron.sh` every ten minutes. The script exists; sync.log was updated at 11:00 EST. A fresh log timestamp is not proof that every new run/model has been backed up. Backup completeness was not checked in this assessment.

## Preserve

- Shared `runs/` (236 MB), `models/` (3.1 GB), `jobs/`, exclusions, review/evaluation data, logs and pose/config provenance.
- Current robot release and measured configurations. Preserve the model explicitly selected by active controllers.
- Runtime `.venv` (659 MB) and training `.train-venv` (8.0 GB).
- Viam agent/server, capture-control, sync cron and credentials (not read or copied).
- Legacy releases as rollback/archive until the replacement has passed verification.

There are 16 robot release directories (372 MB combined), one isolated dashboard release, and eleven model directories. Nine contain the standard anomaly bundle format; `button_xpu_v1` has no bundle and `type_clf_v1` uses another layout. Do not label or delete either as disposable without inspecting their provenance. Standard anomaly bundles cover classic views only; no coverage-view banks were found.

Disk is 85% used with 34 GB available. Old UI directories are only a few MB each. Transfer remnants (`parts/` 79 MB and `joined-release.tar.gz` 79 MB) and superseded release trees are archive candidates after verification, but they do not explain most of the 188 GB used. No storage was deleted.

## Recommended dashboard-only cutover

1. Record PIDs, command lines, release pointers and source hashes; retain rollback artifacts.
2. Stage a permanent isolated dashboard release from the verified new UI; link shared runs/models and supply benchmark definitions plus hash-verified replay JSON. Avoid full `deploy_station.py`, which also switches robot code/config.
3. Start it on an unused test port with camera preview disabled. Verify History, Models denominators/crop reconstruction and active/stale status. Keep the old interfaces available during this check.
4. Coordinate telemetry for the next run after the current controller is released. Prefer station-local UDP so judged operation does not rely on a laptop relay.
5. Cut over one documented URL and retire the four duplicate dashboard processes individually. Keep capture-control, Viam, sync, training workers and the static presentation separate. Archive old UI directories rather than deleting data or environments.

No cleanup or cutover executed.
