# Anomaly inference baseline

[pi/unknown · op Ali · local workstation · ali/pipeline]

## What is implemented

- `vh/anomaly_data.py`: explicitly selected successful collection picks -> shared square-context crops. Whole picks,
  not individual frames, are assigned to train/calibration/test. Defects never build the normal memory bank.
- `train_anomaly.py`: frozen ImageNet ResNet-18 layer2/layer3 patch features + Anomalib PatchCore coreset, one bank per
  **part type × held pose × view × pickup background**. No gradient fine-tuning on tape. Full graph exported to OpenVINO,
  including normalization and nearest-neighbor search. Five separate compiled models currently repeat the backbone;
  sharing an extracted backbone is a possible later optimization, not required to establish this baseline.
- `vh/anomaly.py`: compile/warm before motion; float RGB NCHW in [0,1], raw `pred_score` and `anomaly_map` out.
  Explicit CPU/GPU/NPU only, no device fallback. Missing/wrong-background/invalid results cannot mean good.
- `sort.py --anomaly-bundle ...`: top and webcam inference using the same crop function as training. Required missing
  views reject as uncertain. A defect in any view rejects; a good decision requires all required views to pass.
  A top-view defect still moves to the reject checkpoint before opening the fingers.
- `replay_anomaly.py`: real OpenVINO results from saved picks, displayed on the dashboard. **No robot connection.**
- Dashboard: per-view scores/thresholds, inference times, heatmap toggle and reasons. Maps are 64x64 raw bytes (4 KB),
  coloured by the browser at a fixed scale (128 ~= threshold, 255 ~= twice threshold), not per-image min/max.
  The model adds inference time after picking; dashboard display does not fetch extra camera frames for inference.
- Idle wrist preview now uses `screws.detect`, as the loop does. The old saturation-based preview merged cardboard
  with the target and falsely labelled it a hand. Preview hand status is explicitly **not evaluated**, not "clear";
  the running loop owns its separate hand check. Neither is a certified safety interlock.

## What is NOT implemented / proved

No rotation normalization, part-only masks, empty-gripper subtraction, automatic part-type recognition, independent
physical-part holdout, station GPU/NPU benchmark, or live arm run with these inference changes. Full camera frames are
saved so preprocessing can be changed and models retrained without discarding the source images.

The upright-grasp collision reported by the operator is **unresolved**. This inference work does not fix or validate
upright motion. Do not use a successful offline replay as permission to repeat that grasp.

## Training and offline replay

Run from the repo root in an environment with the normal requirements, OpenVINO and Anomalib installed.
Tested here: anomalib 2.7.0, OpenVINO 2026.4.1, torch 2.15.0. Runtime does not import torch/anomalib.

```sh
python train_anomaly.py \
  --runs runs/20261113_153347_collect runs/20261113_153544_collect \
  --type button_ss_long --background white --out models/button_white_v1

python replay_anomaly.py \
  --bundle models/button_white_v1/bundle.json \
  --dataset models/button_white_v1/dataset/dataset.json --split test

python -m unittest discover -s tests -p test_anomaly.py -v
python tests/test_pipeline.py
```

Do not re-use an output directory: bundles/datasets are not silently overwritten. Models and run images stay local
and gitignored. Move them deliberately to the station when its deployment/runtime is ready.

`sort.py --mode sort --type button_ss_long --background white --anomaly-bundle models/button_white_v1/bundle.json`
would enable it in the real loop, but **moves hardware**: normal arm ownership, E-stop and warning procedures apply.
This is documentation, not a recommendation to launch that command before fixing the upright-grasp issue.

## Honest first result

Nine clean stainless button-head screw picks, 45 images, split 5 train / 2 calibration / 2 test picks. All images come
from the SAME physical part. Threshold per view = maximum good calibration score × 1.10; this small-data heuristic
is not a guaranteed false-reject rate. Test data never selected the threshold.

- All eight held-out webcam images passed.
- One of two held-out wrist images failed (15.090 vs threshold 14.929).
- Consequently one of two whole clean test picks was falsely rejected. **Do not tune to these test outcomes and keep
  calling them held out.** Get new independent good/defect picks before choosing the next configuration.
- OpenVINO vs PyTorch score differences were below 0.00004 on these test images.
- A separate synthetic sanity check raised top-view scores for both blue patches and black marks without training
  on either. This is NOT a real unseen-defect recall measurement.

Reports/artifacts: `models/button_white_v1/{bundle.json,replay_test.json,synthetic_sanity.json,dataset/}`.
Dashboard replay reports no physical motion latency. The model currently requires an explicit part type; other types,
poses or backgrounds have no model and must reject as uncertain.

## Cardboard verdict and next experiment

Part localization at the watch pose found the target in 10/10 cardboard and 10/10 white frames. The OLD preview
falsely flagged a hand in 10/10 cardboard frames versus 0/10 white frames. That compared segmentation, NOT anomalies.

Provisional demo choice: **white**, because the clean normal dataset is on white and pickup surface height remains
known. No evidence yet shows white has better anomaly accuracy. Cardboard's seams/height/warping are nuisance changes;
a uniform matte thin brown surface could still help contrast.

To compare anomaly performance, collect the same SKUs with matched camera poses, lighting and placements on BOTH
surfaces, with separate normal training banks. Hold out independent clean and physically defective picks (including
non-blue defects) on each. Compare whole-item false rejects, defect recall, heatmap location and end-to-end time.
Do not reuse a white-trained threshold on cardboard and call its domain shift a defect.

The camera-only centring test (separate from the sort loop) lowered lens height from 463 to 300 mm, increased the
small target bbox from 22x25 to 32x29 px, and returned to the watch pose without gripper actuation. That pose has NOT
replaced the loop's capture pose. Training and deployed crops must stay consistent if it is adopted.
