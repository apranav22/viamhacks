# Spot it, sort it

[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

Viam × Intel Track 3 fastener inspection. One item is placed on the pad; the arm finds it with the wrist camera, picks it, presents it to the fixed webcam, and releases it over the good or reject compartment. PatchCore anomaly models run locally through OpenVINO. Unknown or unavailable model evidence rejects as uncertain.

The collection and sorting loop has run on the Intel station. Picking remains unreliable for some small parts; upright grasping is disabled by default. Saved-image evaluation uses repeated grasps of a few physical specimens, so it does not establish unseen-part or unseen-defect accuracy. See the [day-one recap](docs/DAY1_RECAP.md) and [latest training evidence](docs/TRAINING_RUN_20261114.md).

## Start here

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python dashboard/server.py --no-preview
# Open http://localhost:8765: Live telemetry, saved-run History and Models; no robot connection.
```

For local model scoring, also install `requirements-anomaly.txt`. Training has a separate environment; tested Intel/XPU dependencies are documented in [ANOMALY.md](docs/ANOMALY.md). Credentials belong in ignored `api-key.json` or `.env`; see `station.py`.

## Supported commands

| Purpose | Command / entrypoint |
|---|---|
| Live / History / Models dashboard | `python dashboard/server.py --no-preview` |
| Download team captures/models | `python sync_data.py pull` (see [DATA_PLAN.md](docs/DATA_PLAN.md)) |
| Export a static run catalog | `python catalog.py` → `runs/index.html` |
| Train a candidate on selected runs | `python train_anomaly.py --help` |
| Score saved picks / compare calibrated policies | `python eval_bundle.py --help` / `python compare_anomaly.py --help` |
| Benchmark explicit OpenVINO devices | `python benchmark_anomaly.py --help` |
| Training jobs and model management | `python train_dashboard.py` (separate station service) |
| Read-only quality reports | `python monitor_quality.py --help` |
| Station source/model recovery | `python -m tools.recover_station --help` |
| Calibration and diagnostics | [tools/README.md](tools/README.md) |

`sort.py` is the **only supported robot loop**. Both modes move the arm; there is no implicit dry-run mode:

```sh
# Examples for an authorized, supervised station session only; follow AGENTS.md first.
python sort.py --mode collect --background cardboard --type socket_m16 --label good --reps 6
python sort.py --mode sort --background cardboard --type auto \
  --anomaly-bundle models/REVIEWED_BUNDLE/bundle.json --anomaly-device CPU --decide top --items 6
```

`--decide top` makes webcam anomaly scores evidence-only; the tape rule still checks captured views. Model selection is explicit; `--anomaly-bundle active` reads the existing `models/ACTIVE` pointer. Recovery of a candidate does not activate it.

`station_run.py start/status/stop` manages the station loop. Pass `--dash-host 127.0.0.1` after `start --` when the dashboard runs on the station; otherwise the launcher uses the laptop address. `deploy_station.py` builds a release from source and refuses a dirty checkout unless explicitly overridden. See [dashboard deployment notes](dashboard/README.md).

## Code and configuration

- `sort.py`: watch → pick → lift → inspect → decide → release → return; collection reuses the same capture path.
- `vh/`: shared detection, motion, kinematics, anomaly preprocessing/inference, datasets, telemetry and preview support.
- `config/poses.json`, `config/checkpoint.json`: measured geometry; `config/part_sizes.json`: latest recovered seven-type size catalog. No environment overrides of measured constants.
- `dashboard/`: operational Live/History/Models interface. Training workers remain separate.
- `tools/`: maintained hardware diagnostics, calibration and recovery utilities.
- `presentation/`: judges presentation; `cd presentation && npm ci && npm run build` (Node 22.12+). See its README for presenter mode and offline packaging.
- `archive/station/`: provenance and recovered historical station experiments; these are not deployed as runtime code.
- `runs/`, `models/`, `logs/`: ignored local artifacts. Old tracked logs were retained locally under `runs/_legacy_logs/`.

## Verification

```sh
python -m unittest discover -s tests
python tests/test_motion.py
node --test tests/test_dashboard_ui.cjs
```

These checks use local fixtures, mocked robot interfaces and saved data. They do not command the arm or establish physical grasp/placement reliability. The optional training integration test needs its separate dependencies.

## Team and judging references

[Architecture](docs/ARCHITECTURE.md) · [Operating rules](AGENTS.md) · [Current cleanup/recovery notes](docs/CLEANUP.md) · [Event/scoring](docs/CONTEXT.md) · [Data and sharing](docs/DATA_PLAN.md) · [Calibration protocol](docs/ANOMALY_CALIBRATION.md) · [Chronological agent log](docs/AGENT_LOG.md).

`site/` contains the design explanation and historical experiment figures (`python site/build.py`). Treat dated planning and experiment notes as historical evidence; the current entrypoints and configuration are described above.
