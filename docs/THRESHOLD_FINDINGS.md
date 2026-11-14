# Thresholds, new captures, and mistakes — day-1 handoff

[pi/unknown · op Ali · Alis-MacBook-Air.local · ali/live-dashboard · 2026-11-13 evening]

Evidence: `docs/AGENT_LOG.md`, saved run decisions/images, and the Intel station's
`/opt/viam/sorter-ali/exp/run.log`. These are small, repeated-pick experiments, not independent-specimen accuracy guarantees.

## Where the evidence lives

- Code/docs: this GitHub repo, branch `ali/live-dashboard`; data sync setup is also on `ali/pipeline`.
- Images, metadata, decisions, exclusions, models: private HF dataset
  https://huggingface.co/datasets/aliriz/armfarm04-fastener-runs . See `DATA_PLAN.md` for pull/push commands.
- Verified shared snapshot `68db3dd684a8ded39fe777c6d6f0b2445d34b864`: 24 runs, 199 picks, 8 bundles.
  Later finished station runs upload automatically every 10 minutes when `sort.py` is not running.
- Private personal namespace is still an access blocker for teammates: move into an HF team org and invite them.
  Do not share Ali's full-access token with teammates. Station uses that token by explicit operator choice; replace with a scoped token.

## New station defect captures (station names use MST, laptop names EST)

| Run | Part | Label | Picks |
|---|---|---|---:|
| `20261113_171443_collect` | hex_bolt_partial | tape | 6 |
| `20261113_171810_collect` | hex_bolt_partial | marker | 6 |
| `20261113_172425_collect` | socket_m16 | tape | 6 |
| `20261113_172711_collect` | socket_m16 | other, non-blue mark | 6 |
| `20261113_173029_collect` | button_ss_long | tape | 4 |

These five runs are verified on HF. Newer station runs include `173234_sort` (live mistakes below) and
`173920_collect` (20 socket_thin_long good picks per operator-session log); verify their presence in the shared index
before assuming they are backed up. Collection completion does not imply successful grasps or verified-good training eligibility.

## Threshold is not ranking quality

Saved top-crop experiment: 61 training picks, 20 calibration picks, 24 held-out-good picks and 8 taped examples.
Features fitted on Intel XPU; crop policy `part-top-v2`. At threshold = 1.02 × calibration-good maximum:

| Backbone / bank selection | AUROC | Good false rejects | Tape caught |
|---|---:|---:|---:|
| ResNet18 pooled | .990 | 2/24 | 8/8 |
| ResNet18 per type | 1.000 | 6/24 | 8/8 |
| wide_resnet50_2 pooled | 1.000 | 7/24 | 8/8 |
| wide_resnet50_2 per type | 1.000 | 7/24 | 8/8 |

Perfect AUROC does NOT mean the deployed threshold is good. Small calibration sets underestimate the spread of real
normal appearances. Higher backbone capacity did not automatically reduce false rejects.

`each_cardboard_v3/bundle.json` uses margin 1.15. `bundle_m103.json` uses 1.03, selected after inspecting the
hex-bolt tape/marker development examples. Do not report those examples as untouched final evaluation.
Session-reported socket_m16 evaluation with known type, margin 1.03: 0/10 good rejected, 6/6 tape and 6/6 other caught.
With best-fitting-bank auto type, only 4/6 taped sockets were caught: they matched a hex-bolt bank instead.

Next: freeze a separate calibration set and a genuinely untouched audit set, grouped by physical specimen (not just
view or pick). Choose an explicit good-rejection budget and report misses and false rejects per category. Do not keep
adjusting thresholds on the same supposed holdout. More repeated views do not create more independent specimens.

## Mistakes that changed the design

- **Threshold too high:** `180637_sort`: taped hex-bolt top scores 21.6/21.7 vs good 16–18.7, but threshold 26.8.
  Tape went to GOOD. Good-calibration outliers and preprocessing variability matter as much as score separation.
- **Blue rule under LED:** tape color ratios failed. Ratio changed 0.6 → 0.4 and top fraction .02 → .01 after reviewing
  tape fractions 2.3–3.9% versus 36 good tops ≤ .08%. These are development observations, not universal constants.
- **Blue zinc is not tape:** `184840_sort` falsely rejected a clean socket_m16 at 1.9% webcam tape fraction.
  Webcam threshold raised to .04 (observed good maximum 2.2%); top remains .01. Non-blue defects still require anomaly detection.
- **Cross-type escape:** `173234_sort` missed a black-taped short hex bolt (18.3 vs threshold 18.3, using long-bolt bank)
  and tiny yellow tape on a thin socket (no thin-socket bank; matched button). Minimum anomaly score over all banks
  can hide defects. Auto type now uses measured top-view size (`part_sizes.py`, `config/part_sizes.json`), not best score.
  Leave-one-out size assignment was 95/101 on four types; unknown size distance >6 rejects. This is not a proven SKU classifier.
- **Missing coverage:** thin-socket normal collection was added after that miss. Missing models must not silently mean good.
- **Pose/view false rejects:** earlier hexbolt_cardboard_v1 held-out-good results: top 0/7, pitch-25 0/7, yaw-20 0/7,
  front 1/7, yaw+35 3/7. `--decide top` logs webcam anomaly evidence but doesn't use it to reject; tape in any view still rejects.
  This trades view robustness against hidden-side coverage; explicitly report that limitation.
- **Bad top crops:** `172508_collect` predates the morphology-scale fix; one crop showed only the bolt head.
  Do not train from it without curation. Rotation-normalized `part-top-v2` now shares crop code between training and runtime.
- **Depth falsely says upright:** lying bolts read 42–48 mm; a diagonal bolt's square axis-aligned bbox looked round.
  Fill-ratio filtering helped, but upright handling remains unvalidated. `173234_sort` also had a false upright, a not-seen,
  and a dropped nut; physical failures belong in totals, not just successful classifications.
- **Collection loops:** `183403_collect` items 22–31 repeatedly missed a screw merged with the table edge.
  `exclude.json` marks them; placement moved inward and repeated misses stop the run.
- **Safety incidents:** upright descent collision at 15:48 remains unresolved; upright grasp is off by default.
  `185701_collect` ended with misses, nudged bolt, torn cardboard, and operator E-stop. Exact cause unproven;
  collection now uses one grasp attempt and stops on a miss. No automatic E-stop reset.
- **Stop bug:** station PID file held a `setsid` wrapper PID, so SIGTERM did not stop the loop. Operator session verified
  termination by process match and changed `station_run.py` stop/status to process lookup. Treat timeout outcomes as unknown.

## Capture recipe and device evidence

Wrist 1280×720, recorded camera settings, fixed lamp LED, cardboard surface z≈6.5 mm, lens 190 mm above surface.
White/background/resolution mismatch is filtered in training; never mix recipes silently. Camera settings and crop
policy are part of the model contract, not incidental setup.

Tiny ResNet18 bundle measured on Intel: CPU ~6.4–6.7 / NPU ~7.7 / GPU ~8.5 ms p50 per view. CPU can win.
The separate event reference PatchCore Viam service uses GPU f32 (~31.7 ms p50 over 437 calls); it is NOT our new bundle.
Do not conflate their timings or claim station model performance from laptop results.

Latest verified backup (19:49 EST): `c20ea5403599f18b9aec8b50ebde1eea0036d068` adds `173234_sort` (13 picks), `173920_collect` (20 good thin-socket picks), and `174637_collect` (1 good pick). Young/in-progress runs remain subject to the two-minute quiet period.
