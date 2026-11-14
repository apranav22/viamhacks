# Offline anomaly-only calibration and promotion

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/live-dashboard · 2026-11-13]

`compare_anomaly.py` is an OFFLINE candidate tool. No robot connection, motion, live threshold edits or activation.
The live tape overrides and manual margins remain unchanged until a reviewed comparison supports removing them.

## 1. Rescore frozen inputs

Use a frozen bundle plus its matching cropped dataset. The scorer checks crop-policy equality, loads/warms the
existing `AnomalyModels` runtime once, and records bundle/model/image/dataset hashes, device, precision, raw scores,
original thresholds, errors and logged tape fractions. Crops are already materialized; they are NOT cropped twice.

```sh
python compare_anomaly.py score \
  --bundle models/each_cardboard_v3/bundle_m103.json \
  --dataset models/each_cardboard_v3/dataset/dataset.json \
  --device CPU --out runs/comparison_v1_scores.json
python compare_anomaly.py specimens \
  --scores runs/comparison_v1_scores.json --out runs/comparison_v1_specimens.json
```

If this bundle isn't local, fetch it using `python sync_data.py pull '__no_runs__' --models each_cardboard_v3`.
Run from the repo root so dataset source-run paths resolve. Existing output files are never overwritten.

**Scope:** this scores the bundle's frozen dataset only. Captures collected after training must first be curated and
materialized into a matching dataset manifest using the SAME crop policy; they are not silently included by globbing
all runs. A mismatched dataset/bundle is refused. Do not infer that new defect runs have been evaluated just because
an older bundle's embedded dataset was rescored.

**Routing:** supplied dataset category (including pooled `any`) is used directly. This is an oracle-category diagnostic,
NOT a test of live size-based routing. No minimum-anomaly-score bank search is used here. Before promotion, replay raw
captures through size routing with the frozen size catalog and record routing errors as well as detector errors.

## 2. Review specimen identities and roles

The generated file is a blank template, NOT a verified split. Fill in the real physical specimen ID and one role per
pick. All views and all picks of the SAME physical object, including before/after adding tape or marker, must share
one role. Feature-training specimens must stay in `train`. The tool also prevents original model-calibration specimens
from becoming a purported untouched audit.

```json
{
  "20261113_173900_collect/item_001": {"specimen_id": "actual-physical-bolt-A", "role": "train"},
  "separate_run/item_001": {"specimen_id": "actual-physical-bolt-B", "role": "calibration"},
  "later_run/item_001": {"specimen_id": "actual-physical-bolt-C", "role": "development"}
}
```

`calibration`: verified good specimens only. `development`: already inspected examples and repeated model comparisons.
`audit`: genuinely untouched specimens/session after choices are frozen. A dataset split named `test` is not automatic
permission to call it an audit. All training-pick identities must also be supplied; otherwise physical leakage cannot
be checked. If historic captures cannot be mapped to real specimens, keep them as development evidence and collect a
new controlled calibration/audit set. Do not invent identities from filenames.

## 3. Choose the rejection budget explicitly

```sh
# EXAMPLE ONLY: .05 is not an agreed product target.
python compare_anomaly.py report \
  --scores runs/comparison_v1_scores.json --specimens runs/comparison_v1_specimens.json \
  --views top --max-good-reject-rate .05 --out runs/comparison_v1_report.json
```

Per item, combine selected views as `max(score / original_bundle_view_threshold)`. The original thresholds are fixed
normalization constants, not manually retuned by this tool. Per category/pose/background, take each calibration
specimen's maximum across repeated picks, then the upper finite-sample good-score quantile at rank
`ceil((n+1)*(1-alpha))`. A candidate anomaly is strictly ABOVE this cutoff (ties pass).

At a 5% budget, at least 19 independent good specimens PER GROUP are needed for a finite cutoff. Repeated grasps of
five screws do not meet that requirement. If rank exceeds n, the cutoff is absent and the group rejects as uncertain;
no arbitrary multiplier is substituted. Coverage statements require exchangeable independent specimens, fixed models,
and a stable recipe. They do not guarantee defect recall, nor survive later model/device/crop changes.

If the available inventory cannot support this, report a provisional empirical operating point and its limited
independent count; do not claim a calibrated 5% rate. This conservative tool deliberately does not invent that fallback.

## 4. Read the comparison and failure list

Report JSON contains:
- `cutoffs`: candidate ratio cutoff and independent calibration specimen count by group.
- `summaries`: separate development/audit, category and defect-label metrics.
- `items`: exact pick IDs/images, scores relative to bundle thresholds, errors and both decisions.
- `source`: bundle/model/dataset hashes and deployment device, plus score/identity file hashes.

Baseline = bundle score threshold OR recorded tape fraction (.01 top, .04 webcam) over the SELECTED views.
This is a matched-view policy comparison, not a reproduction of the live `--decide top` mode, which still allows tape
on other webcam views to override. Missing tape fractions make the baseline unassessable rather than silently negative.
The report must not be presented as a full end-to-end live-policy benchmark.

Missing/invalid required views and uncalibrated categories reject as uncertain. `operational_defect_reject_rate`
includes these reject outcomes; `confirmed_defect_flags` does not credit invalid/uncalibrated rejects as detection.
Unknown labels are excluded from labeled accuracy totals but counted explicitly. View count does not inflate specimen
counts. Decisions remain per pick; the report shows both picks and independent specimens, not confidence intervals
that falsely assume all repeated picks are independent.

## 5. Promotion gate (not implemented as automatic activation)

1. Review held-out failure images, especially subtle/non-blue defects and type-routing mistakes.
2. Fix crop/routing problems before compensating with thresholds. Validate webcam crops before requiring them.
3. Replay anomaly-only with the actual view recipe and size-routing path; measure independent audit miss/false-reject,
   unknown/error rates and missing-category coverage. Don't retune after seeing audit results.
4. Verify on the station and selected device; pin model + cutoff + crop + size catalog + views + precision for the run.
5. Only after human review: remove tape as a reject override (keep it as explanation), activate between runs, retain rollback.
6. Keep compilation, uploads, training, image encoding and dashboard work out of the hot inference path.

## Verified in this implementation pass

- Real local CPU smoke: `button_white_v1` bundle against its matching frozen dataset produced
  `runs/calibration_smoke_button_cpu_scores.json`: 45 image scores, all valid. This is laptop inference, NOT a claimed
  station benchmark or independent calibration result. The unfilled specimen template was correctly refused.
  Smoke artifacts are local under gitignored `runs/`, not a published benchmark.
- Offline regression tests cover leakage, insufficient independent counts, ties, missing views/tape, unknown labels,
  calibration-only fitting, invalid scores, operational-vs-detector metrics and immutable output artifacts.
- Remaining human inputs: verified specimen IDs/roles, numeric good-reject budget, supported category/view recipe.

## Team access to the private dataset

Ali is currently `aliriz` with no HF org. Create a free org at https://huggingface.co/organizations/new, then use its
**Settings → Members → Invite members** to invite teammates using their HF accounts. Give data contributors write
permission and readers read permission as appropriate. Send the org slug to the operator of the sync setup.
Move `aliriz/armfarm04-fastener-runs` into that org, then update BOTH `config/data_repo.json` and `VH_DATA_REPO` in the
installed station cron wrapper. Verify access with a teammate's own login. Nobody needs Ali's token. A scoped station
token remains preferable to the currently installed full-access token.
