[claude-code/claude-fable-5-2 · op aayus (git: aayus@sticker) · sticker · aayush/integration · 2026-11-14]

# EfficientAD handoff (for Ali)

## Result
Dashboard benchmark `development-v1` (62 held-out top captures: 34 good, 28 defective), top view, anomaly only:

| Version | Defects detected | Good rejected |
|---|---|---|
| EfficientAD-S + type classifier | 26/28 | 2/34 |
| EfficientAD-S, size routing | 26/28 | 5/34 |
| codex_curated PatchCore (previous best) | 22/28 | 2/34 |

Reports are in the station's `runs/_analysis/aayush-effad-*-top-replay.json` (Models tab).

## What exists
- `train_efficientad.py` + `trainable_backends.py`: trains EfficientAD-S per (type, pose, view, background) and exports
  OpenVINO with the SAME contract as PatchCore bundles (input [1,3,256,256] RGB 0..1; outputs `pred_score`,
  `anomaly_map`; same `bundle.json` schema). `vh.anomaly.AnomalyModels` loads it unchanged.
- Trained bundle: `models/effad_top_v1` on Aayush's PC (Sticker), top view, 7 types, ~32 MB per model. NOT on the
  station: the Viam shell file upload refuses these files. Copy by scp/USB, or `sync_data.py push --models effad_top_v1`
  with the HF token, or retrain on the station.
- Training needs anomalib 2.7 + torch, and `IMAGENETTE_DIR=<imagenette2-160/train>` (penalty images). ~40-90 s per
  model on an RTX 4070 Ti, 1000 steps. On the station use `.train-venv` with `--device xpu` (untested).
      IMAGENETTE_DIR=... python train_efficientad.py --runs runs/*_collect --type each --background cardboard \
          --views top --out models/effad_top_v1
  Add `--views under end_a end_b` for the coverage views once every type has good picks there.
- Run: `sort.py ... --anomaly-bundle models/effad_top_v1/bundle.json --type auto --decide top`

## Not done / unknown
- Never run in a live sort. Station CPU/GPU/NPU latency not measured (desktop CPU via OpenVINO: ~145 ms per crop;
  PatchCore is ~12 ms). Time it with `tools/device_bench.py`.
- Thresholds: max calibration good score x 1.15 (provisional). Scores are on a different scale from PatchCore (0.2-1.6).
- Top view only; no models for under / end / oblique views.

## Also on this branch
- `d136199`: judge-log `confidence` (vh/confidence.py) + type classifier (vh/type_clf.py, `--type-clf`,
  model already in the station's `models/type_clf_v1`). Held-out runs: type 92% vs 70% for the size rule.
- `train_anomaly.py --threshold cv-p95`: min(p95 of cross-run good, max-margin). Station bundle
  `models/each_cardboard_cvp95_v1` was training at 12:20 (log `/opt/viam/sorter-ali/train_cvp95.log`).
- `tools/`: device_bench.py, device_agreement.py (NPU = CPU decisions on 53 crops, 10.3 ms), dashboard_replay.py,
  threshold_replay.py.
