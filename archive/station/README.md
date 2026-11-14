[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

# Recovered station evidence

Snapshot `20261114T060306Z` came from `/opt/viam/sorter-ali`, deployed release `releases/20261113_194153`. All **299 files / 1,574,233,076 bytes** were verified against the station SHA256 inventory. Recovery used remote reads only; no robot commands, config changes, deployment, training launch or model activation.

- `inventory.json`: original station paths, sizes and SHA256 hashes.
- `recovery.json`: verified local locations, bundle conflicts and the evidence archive hash.
- `evidence.tar.gz`: 14 experiment scripts, 14 deployed source files, five station setup/job scripts, five measured config files, and model JSON descriptors/dataset membership/device reports.
- OpenVINO XML/BIN artifacts are in ignored local `models/`, including V4 (35 banks) and the curated candidate (30 banks). Weights are deliberately outside Git; the inventory and recovery command make them retrievable.

Two existing model names had different laptop/station bytes: `any_cardboard_v2` and `hexbolt_cardboard_v1`. Complete station copies are under `models/_station/20261114T060306Z/<name>/`; original laptop copies were preserved. No ACTIVE pointer was downloaded or changed.

Inspect recovered source without adding executable historical scripts to the maintained tree:

```sh
tar -tzf archive/station/20261114T060306Z/evidence.tar.gz
tar -xOzf archive/station/20261114T060306Z/evidence.tar.gz experiments/nut_center.py
tar -xOzf archive/station/20261114T060306Z/evidence.tar.gz models/each_cardboard_v4/bundle.json
```

The experiments include `one_grasp_head.py`, `one_grasp_probe.py`, `one_grasp_retention.py`, `head_target_preview.py`, `nut_center.py`, `nut_retries.py`, `nut_overlay.py`, `nut_relaunch.sh`, watch probes and crop/evaluation experiments. They preserve temporary clearances and gate bypasses exactly as found. They are historical evidence, **not supported launch commands**. Original authorship is not independently verified; see AGENT_LOG.md and follow AGENTS.md before building on them.

The deployed poses/checkpoint/obstacles/overview calibration matched the local measured files. Its seven-type size catalog replaced the older four-type local catalog; no values were re-fit. The station source lacks the pre-existing local WATCH reference-refresh patch, which remains unvalidated on hardware.

Recover a fresh snapshot with `python -m tools.recover_station --models`; resume an interrupted transfer with `--resume <snapshot-directory>`. Once complete, `--pack <snapshot-directory>` verifies every file, assembles conflicting bundles, and packs the historical source/metadata. Credentials, raw captures, process controls and log files are excluded from recovery.

Supplemental snapshot `20261114T062337Z` verifies 55 source/config files (2764479 bytes), including deployed `vh/` and dashboard/config utility source. Its separate evidence archive retains the full deployed source context without adding old package implementations to the maintained Python tree.
