[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

# Current architecture

`sort.py` owns the station robot loop. The early `pipeline.py` and `run.py` executable prototypes have been retired; their useful shared primitives now live in `vh/`.

## One item through the system

1. **WATCH:** wrist color frames, the shared local-contrast detector, a fixed pick zone, placement stability and the hand/reference gate.
2. **PICK:** move to the camera-centred look pose, save a top image, re-detect the part, orient the jaws, descend and close. Collection makes one attempt; sorting retains the configured retries. Upright grasping is disabled by default.
3. **LIFT:** lift and check settled finger position. The small-part slip and transfer failures documented in DAY1_RECAP remain unresolved.
4. **INSPECT:** present the held item at recorded webcam views over the reject compartment. Each saved view retains its crop, tape evidence and anomaly result.
5. **DECIDE:** apply the selected anomaly-view policy and the tape rule. Missing/failed model evidence is uncertain. Automatic type selection uses measured top-view size and `config/part_sizes.json`.
6. **RELEASE/RETURN:** release over reject or move over the good compartment; collection places the item back. Return to WATCH. A commanded release is not independent physical placement confirmation.

Each item writes `runs/<run>/decisions.jsonl` and `item_NNN/meta.json` with saved captures. Existing legacy records can lack confidence, timestamps, model identity, or an unambiguous retry association. The dashboard preserves those gaps rather than inventing them.

## Runtime modules

| Module | Responsibility |
|---|---|
| `sort.py` | Collection/sorting stages and decision records |
| `station.py` | One credential-loading and Viam connection path |
| `vh/config.py` | Repository paths and measured config loading; no calibration overrides |
| `vh/detection.py` | Wrist projection and local-contrast part detection, shared with preview |
| `vh/motion.py` | Motion wrapper, gripper settling, transforms and grasp geometry |
| `vh/kinematics.py` | Recorded URDF geometry, IK and sampled joint-path obstacle checks |
| `vh/anomaly.py` | Shared crop policy, explicit-device OpenVINO inference, type routing and score contract |
| `vh/anomaly_data.py` | Curated capture selection, exclusions and whole-pick splits |
| `vh/telemetry.py` | Non-blocking UDP events and JPEG chunks |
| `vh/geometry.py`, `vh/live_detect.py` | Dashboard preview transforms and overlays |
| `vh/scan.py`, `vh/tracking.py` | Supporting calibration/diagnostic code |

The shared grasp geometry and kinematics read the closed fingertip offset from `config/poses.json`. Planned moves and sampled joint paths use the same workcell obstacle definitions, including tripod, lamp and box. Direct descent/lift retains its existing implementation; sampled path checks are an approximation, not a proof of collision freedom.

## Measured configuration

`poses.json` holds the touch-measured bare-table/cardboard surfaces, fingertip offset and grasp settings. `checkpoint.json` holds the re-measured webcam projection, capture views and watch pose. `part_sizes.json` was recovered from the deployed station release and covers seven types. The recovery inventory records hashes of the original files. Values were recovered, not re-fit.

The physical jaw axis is **y**. `jaw_offset_deg: 90` is the desired closing direction relative to a part's long axis in the current calculation. It is not an axis identifier. Station and local `poses.json` agree on 90; the former AGENTS.md claim of 0 was stale.

## UI, training and data

The loop sends UDP to `dashboard/server.py`; the UI receives SSE. Live follows current telemetry; History reads saved runs and optional hash-verified offline replays. Preview is optional and adds camera RPC load; benchmark it before judged runs. No dashboard dependency sits in the robot's critical path.

`train_anomaly.py` trains and exports candidates in a separate environment. `benchmark_anomaly.py`, `eval_bundle.py` and `compare_anomaly.py` evaluate saved data. `train_dashboard.py` manages jobs and explicit model activation; `monitor_quality.py` reports evidence. Recovery never changes the ACTIVE model pointer. Multiple historical browsing/export tools remain available, but Live/History is the primary operational review interface.

Pick-level dataset splits keep views from one grasp together. Repeated grasps of the same physical part remain dependent evidence. See ANOMALY_CALIBRATION.md for specimen-level calibration/audit requirements and TRAINING_RUN_20261114.md for the latest candidate results.

## Releases and station recovery

`deploy_station.py` packages an explicit runtime/config allowlist with per-file SHA256 hashes, source commit and dirty-state provenance. Runs and models remain shared across station releases. Machine-config snapshots, credentials and archived experimental scripts are excluded. Deployment requires a clean checkout by default.

`tools.recover_station` uses read-only station shell/file-transfer calls, preserves station source plus model descriptors under `archive/station/`, and downloads model weights into ignored `models/`. Different artifacts with the same model name are preserved separately. Recovered grasp probes are historical experiments, not automatically integrated or activated.

The pre-existing WATCH reference refresh edit is retained in `sort.py`; it has not been physically validated. This cleanup has not been deployed or rehearsed on the arm.
