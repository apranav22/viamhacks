# Dashboard

[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

One server, three views at `http://localhost:8765`:

- **Live** receives the existing UDP telemetry. Choose a camera, follow the active item or inspect an earlier item, and select any captured attempt. Anomalib and tape evidence are separate from the decision trigger. A release remains unconfirmed physical placement.
- **History** opens with a run picker, previous/next item controls, camera image with its saved box, crop, one plain-language result, and numbered capture buttons. The newest available offline replay is selected initially and labeled “Rechecked image.” Details holds model selection, original decisions, scores, timings, routing, run filters, notes and raw records. Derived crops appear beside their source image rather than being counted as another camera exposure.

- **Models** compares saved results on a fixed benchmark, browses failures with the camera image and model crop, and opens the exact capture and selected model in History. Incomplete or unverified comparisons stay unavailable. Model controls and styling are scoped to this tab; History keeps its minimal layout. Details dialogs hold the technical evidence and remain scrollable on small screens.

Without the robot, start with:

```sh
python3 -I dashboard/server.py --no-preview
```

`--runs-dir /path/to/runs` selects another saved-data root. History never connects to the robot. A deep link can select a run and item: `/?run=20261113_173234_sort&item=item_001#history`. `/history` and `/explore` on this server redirect to History. Existing catalog/training tools remain separate utilities; this dashboard exposes no model activation or robot controls.

Missing data stays explicit. Older records may omit capture timestamps, detector thresholds, model identities, or which top retry was scored. They are not reconstructed as facts. Model heatmaps are not drawn over untransformed source images. Saved inspection crops are labeled as such.

Solid boxes show saved top-view blob detections; dashed boxes show saved inspection regions. Where a model input is unavailable but a valid box exists, “Detection crop” displays that camera region. “Inspected crop” displays a saved crop or a verified replay reconstruction; Details states which. “Defect missed” requires a saved defective-item label and an explicit negative model result. An unscored or unavailable capture says “Not checked”; failed or uncertain scoring says “Could not check.” Replay verdicts never borrow tape flags from the original run. These are capture results, not physical sorting confirmations.

Optional offline evaluations are read from `runs/_analysis/*.json` with `schema: "dashboard-replay-v1"`, a `label`, and `rows` containing `pick`, `file`, `image_sha256` and `routed` score fields. Optional `oracle`, `type` and `selected_type` fields expose known-type diagnostics. Results appear as a separate selector and never replace recorded decisions. A source-image hash mismatch blocks the score. Top crop reconstruction requires matching `runtime_sha256` and `crop_policy: "part-top-v2"`; it uses the existing Pillow/SciPy preprocessing, never runs inference, and is labeled as a reconstruction. Without these optional dependencies the original images/results still work.

The read-only endpoints are `/api/history/runs`, `/api/history/run?run=…`, `/api/history/item?run=…&item=…`, and validated image/crop endpoints. The application uses the same `/events` SSE transport as the preceding dashboard.

[pi/unknown · op Ali (git: Ali, github: unknown) · Alis-MacBook-Air.local · ali/live-dashboard]

The server displays telemetry; it does not control motion. Camera tabs stay selected across run events. Inspection evidence remains in the strip and per-item progress records observed milestones. A decision or completed release sequence is not physical placement confirmation.

## Intel station

`deploy_station.py` now includes `dashboard/` in release archives. Deploy only a reviewed release: the deployment script also includes the current working copies of motion code and config. Do not deploy a dirty shared tree just to update this UI.

After approved deployment, run from the station release directory using its runtime:

```
cd /opt/viam/sorter-ali/current
/opt/viam/sorter-ali/.venv/bin/python3.12 -I dashboard/server.py --preview-during-run --run-preview-fps 1 --udp-host 127.0.0.1
```

Serve HTTP on loopback and use an approved SSH/Viam port forward for port 8765; open the forwarded `http://localhost:8765/` on the laptop. Alternatively `--host 0.0.0.0` exposes the unauthenticated dashboard to the trusted station network; do not expose it publicly.

For a separately authorized station sorting run, route telemetry with `--dash-host 127.0.0.1`. The `station_run.py` launcher preserves an explicit `--dash-host 127.0.0.1`; without that option it uses the laptop address. Starting this dashboard does not start a sorting run.

Run preview is opt-in, camera-only, defaults to 1 FPS per camera and is capped at 2 FPS. It skips detection, geometry and arm polling during active runs. It adds camera RPC load and needs station latency validation before judged runs. Without the flag, preview still pauses during runs; saved frames are explicitly timestamped and marked stale/snapshot rather than presented as continuous video.

## Offline checks (no robot)

```
python3 -m unittest discover -s tests -p 'test_dashboard*.py'
node --test tests/test_dashboard_ui.cjs
python3 -I dashboard/server.py --no-preview --port 8875 --udp-host 127.0.0.1 --udp-port 8876 --record ''
```

Frontend assets are read per request: reload the browser for UI changes. Backend options require a server restart. This consolidation has been tested locally with saved data and synthetic telemetry; it has not been deployed to the Intel station. `DEPLOYMENT.md` describes earlier isolated deployments and their rollback instructions.


[codex/unknown · op Ali (git: Ali, github: unknown) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

## Models and viewport layout

Live, History, and Models fit the browser height. Images occupy the remaining space; example navigation uses previous/next controls and selectors. History retains numbered capture buttons, paginated in groups of six. Portrait phones stack the two images. History keeps its model selector inside Details. Live switches between Camera and Inspection rather than stacking both. Details opens a dialog with separate pages; it does not expand the document. Full legacy records can be saved as JSON.

Models reads frozen benchmark membership from `config/benchmarks/*.json` and hash-verified CPU replay artifacts from `runs/_analysis/*.json`. The initial Development set contains 34 test good and 28 defective top captures. Labels are recorded collection labels, and specimen independence is unverified. A model must have exactly one matching result for every member, all in its test split; missing/duplicate results, hash/label disagreement, and training/calibration overlap block its comparison. No partial denominators are silently substituted. Unknown-type verdicts are counted separately from detected defects.

The latest candidate shows five missed defects, two good rejections, and one unknown type. Previous v4 is blocked on this membership because of split overlap. This is not a common independent audit set; curate new specimens before a fair final comparison. No training/inference/activation is triggered by viewing the dashboard, and the old Intel training service has not been stopped or replaced remotely.

Failure examples show original capture, verified reconstructed crop, and a plain diagnosis. Details separates routed scores from the labelled-type diagnostic. “Wrong item type selected” is causal only when the known-type check fixes the verdict; otherwise both routing and scoring are implicated. Localisation accuracy and physical handling stay explicitly unmeasured.

Local review server for this implementation: `http://localhost:8877/#models` (camera preview and recording disabled). Launch with:

```sh
../sorter/.venv/bin/python -I dashboard/server.py --no-preview --port 8877 --udp-host 127.0.0.1 --udp-port 8878 --record ''
```

Additional checks: `python3 -m unittest discover -s tests -p 'test_benchmarks.py'`.

## Starting runs from the dashboard

The Live tab has a **Start a run** panel: **Capture run** (`sort.py --mode collect`: part type, label, picks) or
**Live anomaly detection** (`sort.py --mode sort`: items, model bundle, which views decide). Both take the surface,
the view set (coverage/classic) and where to run: *This computer* (telemetry straight to this dashboard) or *Station*
(the **deployed** release, via `station_run.py`; deploy first if the code changed).

Safety (AGENTS.md §2): Start stays disabled until "A person is at the E-stop" is ticked, asks for confirmation, and
unticks after each start. The server refuses while any run is sending telemetry or another `sort.py` runs on this
computer; sort.py itself refuses while teleop runs or the joints are moving. Each start/end appends
`ARM: taken` / `ARM: released` to `docs/AGENT_LOG.md`. Stop terminates the run (station: `station_run.py stop`).
Only whitelisted options reach sort.py; requests must be same-origin JSON. The panel is hidden with
`--no-run-control`, `--no-preview` or `--replay`. Bind to `127.0.0.1` (the default) unless you want other machines on
the network to be able to start the arm.
