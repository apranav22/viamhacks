[codex/unknown · op Ali (git: Ali; github: unknown) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

# Curated Intel PatchCore training run

Completed through the existing Viam shell on armfarm04b. No robot commands, machine configuration changes, live model activation, or service restarts.

Candidate: `/opt/viam/sorter-ali/models/codex_curated_20261114_003525/bundle.json`. Job record and log: `/opt/viam/sorter-ali/jobs/codex_curated_20261114_003525/`. All 30 banks exported, no skipped groups; training process exited after the final BUNDLE message. Feature extraction executed on Intel xpu:0; coreset selection and export on CPU. Existing ResNet18 PatchCore script, part-top-v2 crops, default margin 1.15.

## Good-data coverage

All 143 usable current-recipe good picks were included: 75 training (375 crops), 34 calibration (169 crops), 34 test (170 crops). The missing completed run `20261113_185456_collect` was restored from the laptop to the shared station runs directory before training. Caution/probe thin-short captures and legacy recipes were excluded.

| Type | Train picks | Calibration picks | Good test picks |
|---|---:|---:|---:|
| button_ss_long | 11 | 5 | 5 |
| hex_bolt_partial | 16 | 7 | 7 |
| hex_bolt_short | 7 | 2 | 2 |
| hex_nut | 11 | 5 | 5 |
| socket_m16 | 20 | 10 | 10 |
| socket_thin_long | 10 | 5 | 5 |

## Saved-image evaluation

The built-in evaluation supplies the labelled part type directly; this does not test automatic size routing. Top-view results at the fixed 1.15 margin: 0/34 good rejected, 11/16 tape flagged, 6/6 marker flagged, 6/6 other-mark flagged (23/28 defects total). Five taped picks missed. Webcam views have additional false rejects; do not infer that using every view improves the decision. No threshold tuning or promotion performed.

These are repeated-pick development results, not independent physical-specimen or unseen-defect validation. No physical specimen identities were invented.

## Correction to earlier local-only coverage assessment

Existing station v4 already covers seven types and has a separate seven-type size catalog, `models/part_sizes_v4.json`. Its dataset has 149 good picks: 79 train (395 crops), 35 calibration (174 crops), 35 test (175 crops). It includes seven thin-short probe picks and lacks the newly restored short-bolt pick. The new candidate uses the catalog-approved six-type subset; it is not a replacement for v4 until reviewed.

## Provenance

```json
{
  "job": {
    "identity": "codex/unknown; operator Ali; host armfarm04b; branch ali/pipeline",
    "selected_runs": [
      "20261113_173414_collect",
      "20261113_173900_collect",
      "20261113_175140_collect",
      "20261113_181752_collect",
      "20261113_183403_collect",
      "20261113_185456_collect",
      "20261113_185701_collect",
      "20261113_171443_collect",
      "20261113_171810_collect",
      "20261113_172425_collect",
      "20261113_172711_collect",
      "20261113_173029_collect",
      "20261113_173920_collect",
      "20261113_183052_collect",
      "20261113_183322_collect",
      "20261113_183542_collect",
      "20261113_183719_collect",
      "20261113_184545_collect"
    ],
    "command": [
      "/opt/viam/sorter-ali/.train-venv/bin/python",
      "train_anomaly.py",
      "--runs",
      "runs/20261113_173414_collect",
      "runs/20261113_173900_collect",
      "runs/20261113_175140_collect",
      "runs/20261113_181752_collect",
      "runs/20261113_183403_collect",
      "runs/20261113_185456_collect",
      "runs/20261113_185701_collect",
      "runs/20261113_171443_collect",
      "runs/20261113_171810_collect",
      "runs/20261113_172425_collect",
      "runs/20261113_172711_collect",
      "runs/20261113_173029_collect",
      "runs/20261113_173920_collect",
      "runs/20261113_183052_collect",
      "runs/20261113_183322_collect",
      "runs/20261113_183542_collect",
      "runs/20261113_183719_collect",
      "runs/20261113_184545_collect",
      "--type",
      "each",
      "--background",
      "cardboard",
      "--out",
      "/opt/viam/sorter-ali/models/codex_curated_20261114_003525",
      "--train-device",
      "xpu",
      "--margin",
      "1.15"
    ],
    "cwd": "/opt/viam/sorter-ali/releases/20261113_194153",
    "output": "/opt/viam/sorter-ali/models/codex_curated_20261114_003525",
    "limitations": [
      "Pick splits repeat physical specimens; development evidence only.",
      "Probe/caution captures excluded. No live activation."
    ],
    "source_sha256": {
      "train_anomaly.py": "b866c27d2822d5be988de0357669bb959ecb40a17e9760dc5a0b05e85e1fec5d",
      "vh/anomaly_data.py": "1c40beef49f01cc727c0094f91278abc9c68c35f2545a20d3e57c74b9d67a281",
      "vh/anomaly.py": "0b639397d582a6e0d8589e44ae5b735ad4d312364c6565a298f8cc4ef376dbdc"
    },
    "pid": 517786
  },
  "results": {
    "candidate": {
      "bundle_exists": true,
      "dataset_exists": true,
      "banks": 30,
      "skipped": [],
      "types": {
        "button_ss_long": {
          "train": 11,
          "calibration": 5,
          "test": 9
        },
        "hex_bolt_partial": {
          "train": 16,
          "calibration": 7,
          "test": 19
        },
        "hex_bolt_short": {
          "train": 7,
          "calibration": 2,
          "test": 2
        },
        "hex_nut": {
          "train": 11,
          "calibration": 5,
          "test": 5
        },
        "socket_m16": {
          "train": 20,
          "calibration": 10,
          "test": 22
        },
        "socket_thin_long": {
          "train": 10,
          "calibration": 5,
          "test": 5
        }
      },
      "test_by_view": {
        "front|good": {
          "n": 34,
          "flagged": 3
        },
        "front|tape": {
          "n": 16,
          "flagged": 4
        },
        "pitch-25|good": {
          "n": 34,
          "flagged": 0
        },
        "pitch-25|tape": {
          "n": 16,
          "flagged": 6
        },
        "top|good": {
          "n": 34,
          "flagged": 0
        },
        "top|tape": {
          "n": 16,
          "flagged": 11
        },
        "yaw+35|good": {
          "n": 34,
          "flagged": 4
        },
        "yaw+35|tape": {
          "n": 16,
          "flagged": 5
        },
        "yaw-20|good": {
          "n": 34,
          "flagged": 2
        },
        "yaw-20|tape": {
          "n": 16,
          "flagged": 6
        },
        "front|marker": {
          "n": 6,
          "flagged": 4
        },
        "pitch-25|marker": {
          "n": 6,
          "flagged": 4
        },
        "top|marker": {
          "n": 6,
          "flagged": 6
        },
        "yaw+35|marker": {
          "n": 6,
          "flagged": 5
        },
        "yaw-20|marker": {
          "n": 6,
          "flagged": 3
        },
        "front|other": {
          "n": 6,
          "flagged": 0
        },
        "pitch-25|other": {
          "n": 6,
          "flagged": 3
        },
        "top|other": {
          "n": 6,
          "flagged": 6
        },
        "yaw+35|other": {
          "n": 6,
          "flagged": 4
        },
        "yaw-20|other": {
          "n": 6,
          "flagged": 4
        }
      },
      "good_picks": {
        "train": 75,
        "calibration": 34,
        "test": 34
      },
      "good_crops": {
        "train": 375,
        "calibration": 169,
        "test": 170
      },
      "dataset_skips": [
        {
          "pick": "20261113_173414_collect/item_005",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_181752_collect/item_009",
          "reason": "excluded on review: not grabbed (part not seen from hover)"
        },
        {
          "pick": "20261113_181752_collect/item_017",
          "reason": "excluded on review: top bbox = head fragment only (pre merge-fix)"
        },
        {
          "pick": "20261113_181752_collect/item_027",
          "reason": "excluded on review: top bbox = head fragment; dropped during view front"
        },
        {
          "pick": "20261113_183403_collect/item_022",
          "reason": "excluded on review: look not seen (loop)"
        },
        {
          "pick": "20261113_183403_collect/item_023",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_024",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_025",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_026",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_027",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_028",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_029",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_030",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_031",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_185456_collect/item_002",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_185701_collect/item_011",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_183052_collect/item_004",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_183719_collect/item_002",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_184545_collect/item_008",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_184545_collect/item_016",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_184545_collect/item_017",
          "reason": "not a completed collection of requested type"
        }
      ]
    },
    "v4": {
      "bundle_exists": true,
      "dataset_exists": true,
      "banks": 35,
      "skipped": [],
      "types": {
        "button_ss_long": {
          "train": 11,
          "calibration": 5,
          "test": 5
        },
        "hex_bolt_partial": {
          "train": 16,
          "calibration": 7,
          "test": 7
        },
        "hex_bolt_short": {
          "train": 6,
          "calibration": 2,
          "test": 2
        },
        "hex_nut": {
          "train": 11,
          "calibration": 5,
          "test": 5
        },
        "socket_m16": {
          "train": 20,
          "calibration": 10,
          "test": 10
        },
        "socket_thin_long": {
          "train": 10,
          "calibration": 5,
          "test": 5
        },
        "socket_thin_short": {
          "train": 5,
          "calibration": 1,
          "test": 1
        }
      },
      "test_by_view": {
        "front|good": {
          "n": 35,
          "flagged": 3
        },
        "pitch-25|good": {
          "n": 35,
          "flagged": 1
        },
        "top|good": {
          "n": 35,
          "flagged": 1
        },
        "yaw+35|good": {
          "n": 35,
          "flagged": 4
        },
        "yaw-20|good": {
          "n": 35,
          "flagged": 2
        }
      },
      "good_picks": {
        "train": 79,
        "calibration": 35,
        "test": 35
      },
      "good_crops": {
        "train": 395,
        "calibration": 174,
        "test": 175
      },
      "dataset_skips": [
        {
          "pick": "20261113_173414_collect/item_005",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_181752_collect/item_009",
          "reason": "excluded on review: not grabbed (part not seen from hover)"
        },
        {
          "pick": "20261113_181752_collect/item_017",
          "reason": "excluded on review: top bbox = head fragment only (pre merge-fix)"
        },
        {
          "pick": "20261113_181752_collect/item_027",
          "reason": "excluded on review: top bbox = head fragment; dropped during view front"
        },
        {
          "pick": "20261113_183052_collect/item_004",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_183403_collect/item_022",
          "reason": "excluded on review: look not seen (loop)"
        },
        {
          "pick": "20261113_183403_collect/item_023",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_024",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_025",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_026",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_027",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_028",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_029",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_030",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183403_collect/item_031",
          "reason": "excluded on review: loop"
        },
        {
          "pick": "20261113_183719_collect/item_002",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_184545_collect/item_008",
          "reason": "not a completed collection of requested type"
        },
        {
          "pick": "20261113_185701_collect/item_011",
          "reason": "not a completed collection of requested type"
        }
      ]
    },
    "process": "exited"
  }
}
```

Next: review the five missed taped picks and replay saved captures through frozen size-based routing before considering activation.


[codex/unknown · op Ali (git: Ali; github: unknown) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]

## Dashboard replay integration

Added `runs/_analysis/curated-candidate-top-replay.json` using the existing dashboard-replay-v1 contract. 171 top-view rows scored on station CPU, zero errors, all local original-image hashes verified. Fixed historical `models/part_sizes_v4.json` used for automatic routing; labelled-type scoring retained separately as oracle diagnostics. No frontend/backend changes or model activation.

Automatic routing on the 34 test good picks: 32 clear, 2 anomalous. On 28 defect picks: 22 anomalous, 5 clear, 1 unknown-type (uncertain/reject under the live policy, not an anomaly detection success). Across all 171 development rows, 18 selected types differ from supplied labels, including unknowns; this is not an independent routing accuracy estimate.

Review: `http://localhost:8875/?run=20261113_173029_collect&item=item_001#history`, select Results → Curated candidate · margin 1.15 · Intel CPU, select top capture. Existing V4 top replay is independently selectable. API verified to return both replays and input_verified=true. Browser rendering not inspected in this session.

Consolidation recommendation: use Astra's Live/History UI as the single review surface; add a model comparison view backed by the replay artifacts, with common evaluation membership, type/view breakdowns, clickable false rejects/misses/unknowns, routing versus known-type diagnostics, and train/calibration/test membership. Keep training workers separate. Do not aggregate five view rows as five independent items.
