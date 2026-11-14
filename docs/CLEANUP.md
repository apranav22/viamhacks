[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

# Repository consolidation

The cleanup lives in `/Users/alirizwan/Projects/Misc/viamhacks-cleanup`, an isolated worktree now on `ali/clean-base` (based on `ali/pipeline`). A background presentation session switched the shared checkout to `ali/judges-presentation`; cleanup-owned edits were restored there to their pre-cleanup contents after copying this snapshot. Background Live/History/Models, benchmark, catalog, training-evidence and judges-presentation changes were integrated from the shared checkout and are included in this reviewed snapshot. The shared checkout remains available for ongoing work; no branch was switched underneath another session.

## Changes

- Retired the `run.py` and `pipeline.py` executable generations, generated `api.py` scaffold, the obsolete root crop experiment, and the baseline's separate station/fake/perception implementation and unused probe telemetry adapter.
- Extracted active motion/grasp helpers to `vh/motion.py`, shared local-contrast detection to `vh/detection.py`, diagnostic depth scan to `vh/scan.py`, and tracking to `vh/tracking.py`. Extracted motion/grasp bodies were compared as Python ASTs against the preceding implementation; only type annotations changed.
- Moved seven maintained hardware utilities into `tools/`, with module commands documented in tools/README.md. Removed unused pad-detection helpers and their historical pad-size constant from the sorter.
- Replaced the old baseline's environment-overridable constants with measured config loading. Kinematics uses the same fingertip offset as grasping. Depth measurements no longer override the touch-measured table height in calibration helpers. Planned moves and sampled joint paths share workcell geometry, including fixtures.
- Recovered the station's seven-type part-size catalog. Verified that poses/checkpoint/obstacles/overview calibration agree with local files. Corrected stale jaw-offset and webcam statements in AGENTS.md; no measured poses were tuned.
- Removed 31 tracked historical log files from the active tree; retained their bytes locally under ignored `runs/_legacy_logs/`. Ignored local logs and agent scratch state.
- Updated deployment's explicit source/config list, excluded machine-config snapshots and archived experiments, and added revision/dirty-state provenance plus a clean-checkout default. The station launcher now respects an explicit dashboard host.
- Replaced the README/architecture's obsolete launch instructions and marked early event/planning records as historical.

## Station recovery

See [archive/station/README.md](../archive/station/README.md). All 299 inventoried files were recovered and checked. Historical source and model metadata are in a verified evidence archive; 1.57 GB of artifact/source bytes were accounted for. OpenVINO weights remain in ignored `models/`, shared locally between worktrees. V4 and the new curated candidate are now local. Differing same-name laptop/station bundles are retained separately.

No credentials, raw images or station logs were added to Git. No model was promoted. Station-only experimental grasp fixes were preserved, not silently merged into the live loop.

## Validation and remaining work

The maintained runtime/tools import without opening a robot connection. Offline unit tests cover extracted grasp/settling behavior, fixture geometry, deployment packaging, checksum-verified recovery and conflicting bundles. The surviving geometry/UDP checks, overview selftest and JavaScript reducer tests also run offline. Deployment artifacts were compiled and checked for retired imports and excluded files.

No deployment or physical rehearsal was performed. The original uncommitted WATCH reference-refresh change is retained; its assumptions require hardware review. Thin-part retention, upright picking, physical placement verification and independent-specimen model evaluation remain unresolved as documented in DAY1_RECAP.md and TRAINING_RUN_20261114.md.

Validation on this isolated snapshot: 80 Python unit tests passed with one optional training test skipped; three geometry/UDP checks and nine JavaScript reducer tests passed. All maintained runtime/tool modules imported without opening a robot connection; supported CLI help and the overview selftest passed.

This branch includes the latest monitored background dashboard, training evidence and presentation sources. Later edits in the shared checkout remain separate and need normal integration before another release. Do not deploy a dirty shared checkout solely to update UI assets.

A supplemental source-only station snapshot (`20261114T062337Z`) captures the deployed vh/ package and dashboard/config utility source as well as top-level scripts; its complete file inventory and verified archive are under archive/station/. No historical package code was promoted over the maintained runtime.

The integrated snapshot also passes the judges presentation TypeScript/production build under Node 22.23.1 and offline ZIP packaging. A temporary dashboard with preview/recording disabled returned HTTP 200 for the app, health, History archive and Models benchmark endpoints. Shared-source hashes were stable across final verification.
