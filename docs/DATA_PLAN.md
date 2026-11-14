# Data plan: part classes, splits, holdout defects

[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:45] First version, from the kit photo
(12 parts on the table). Correct the inventory once the parts are handled.

## The label space is not symmetric

- **Part type is a closed set.** We know every SKU in the kit; each has one canonical "good" appearance.
- **Defects are an open set.** Tape is the one type we can see; the judges add at least one we haven't. Unseen defects
  can't get their own bin, so we never train a "defect class". A defect is *distance from that part type's good
  appearance*.
- **Decision = box / reject. Reason in the log** = `good` · `known: tape` · `anomaly: unknown`. That gives the explanation
  without needing defect classes.

## Classes in the kit (from the photo)

| Family | SKUs seen | Taped (defective) examples |
|---|---|---|
| Hex-head bolt, zinc | short (≈20 mm) ×3, long partly threaded ×2 | short: tape on head, tape at thread tip; long: tape on shank by the head |
| Socket-head cap screw, zinc | large cyan-zinc ×1, long thin ×2 | large: tape on head edge; thin: tape wrapped mid-shank |
| Button-head screw, stainless | long ×2 | one with tape at the head |
| Hex nut, zinc | ×2 (one has a bluish inner ring) | tape in the bore |

≈ 12 parts, ~7 SKUs, 4 families, ~7 taped / 5 clean. Several SKUs come as a clean + taped pair: the ideal training and
test unit.

## Model: per-type normal model, not a defect classifier

1. **Type first** (closed set): length, diameter, head shape from the hover look (depth + outline), nearest SKU in a
   small catalog. A part that matches no SKU is itself anomalous → reject.
2. **Anomaly score per (type, view)**: PatchCore (frozen pretrained backbone) with a memory bank of **good** patches of
   that type, in that view (wrist top / webcam front / tilt). Per-type banks matter here: the large socket screw's
   zinc is strongly cyan and the nut's ring is blue, so a shared bank can match a tape patch to a *good* patch of
   another type and miss it.
3. **Tape check** (hue rule) as a separate known-defect channel, OR-ed with the anomaly score. It names the defect; it
   never decides "good".
4. Item score = max over views; unsure → reject.

**Don't fine-tune the backbone on tape.** Supervised training on 7 tape samples turns the features into a blue-tape
detector: great validation numbers, worse on the unseen type, and a threshold set on tape will be too high for subtle
defects. If we want a supervised signal, use **synthetic** anomalies (pasted color patches, strokes, cut-paste), which
don't teach "blue".

## Splits

| Split | Contents | Used for |
|---|---|---|
| `train/good` | good parts, every SKU, several placements and grasps, all views | memory banks (fit) |
| `val/good` | good parts, **different placements** from train | threshold per type: max good score + margin (sets the false-reject rate) |
| `val/tape` | taped parts, varied tape positions | known-defect recall, tape-rule tuning |
| `holdout/other` | defects nobody fits or tunes on: Sharpie marks, other-color tape, sticker dot, grease/dirt, scratch, a part not in the kit | **unseen-defect recall**, looked at only for go/no-go |

Rules: thresholds come from good data only; `holdout/other` is never used to choose a model or threshold (if it is, make a
new holdout). Leave-one-defect-type-out evaluation when there's time.

## Getting more data from the same kit

- Tape is removable: peel it to get good samples of every SKU, then re-tape at new spots (head, under the fingers,
  bore, tip, underside) for defect variety. Ask staff first, they're their props.
- One pick gives 1 wrist view + 1–3 webcam views; vary placement and grasp each time. ~15 s per pick.

## Two reference frames, stacked (15:55, [claude-code/claude-opus-5-5 · op Ali])

| | Stage 1: top (wrist cam at hover) | Stage 2: webcam (held at the checkpoint over reject) |
|---|---|---|
| background | plain table | busy (fingers, arm, backboard) but identical per view: recorded joint poses |
| scale | fixed hover height, ~0.45 mm/px | fixed pose, ~6 px/mm |
| input | crop at the detected bbox, rotated so the long axis is horizontal; part pixels only (detector colour mask) | crop at the projected fingertips (`meta.json` crop_box); part = differs from `config/webcam_refs/<view>.jpg` (empty gripper) outside the fingers |
| memory banks | `top/lying`, `top/upright` | one per view: front, yaw-20, yaw+35, pitch-25 (held across); end, side0, side+120, side-120 (held upright) |

One frozen backbone (OpenVINO) for both, separate PatchCore banks per view. "Canonical" = the bank of good patches
for that view, filled with many placements / faces / grip points (collect mode drops the part from 20-35 mm half the
time so it lands on a random face; upright parts set down stay upright, dropped ones tip over).
Decision: stage 1 confident defect -> drop at once (already over reject); else stage 2 views; tape OR anomaly in any
view; unsure -> reject. Splits by pick (all views of a pick in one split). Synthetic defects (cut-paste, colour blobs,
strokes on part pixels) are for validation only.

Per pick on disk: `runs/<run>/item_NNN/` watch.jpg, top_N.jpg, web_<view>.jpg (1080p), crop_<view>.jpg, meta.json
(bboxes, yaw, pose, height, jaw, crop boxes, joints, how it was placed next); the run's decisions.jsonl has labels.

## Sharing the data with the team (19:27, [claude-code/claude-opus-5-5 · op Ali · Alis-MacBook-Air.local · ali/pipeline])

Collected runs lived in two places only (Ali's laptop `runs/`, the station's `/opt/viam/sorter-ali/runs/`), with no
backup and no way in for teammates. The shared home is now **one public Hugging Face dataset repo** (made public by Ali; anonymous index download verified), managed by
`sync_data.py`. Layout in the repo = layout on disk (`runs/<run>/item_NNN/...`, `models/<name>/...`) plus
`index.json` (per run: host, items, labels, types, backgrounds, excluded, content fingerprint).

```sh
pip install huggingface_hub==2.4.0                     # no login needed for public downloads
# hf auth login                                        # required only for authorized uploads
python sync_data.py status                               # what's shared, what's only here, what differs
python sync_data.py pull                                 # every shared run you don't have (or 'pull "*_18*"')
python sync_data.py push                                 # your finished runs (skips runs written < 2 min ago)
python sync_data.py push --models any_cardboard_v2       # share a trained bundle too
python sync_data.py pull --revision <commit>             # exact snapshot a model was trained on
```

**Repo:** https://huggingface.co/datasets/aliriz/armfarm04-fastener-runs (public, `config/data_repo.json`).
Anyone can browse/download; teammates do not need an invite or Ali's token. Public visibility does NOT grant write
access. The team org is `viamhacks` (display name "viam hacks 4b"); transferring there was denied by the current
OAuth credentials, so the repo remains under `aliriz` and station syncing needs no namespace change.
If team-managed uploads are wanted later, transfer ownership via HF settings and grant appropriate org roles.
First push 19:35: 19 laptop runs + 3 models
(`any_cardboard_v2`, `button_white_v1`, `hexbolt_cardboard_v1`); pull round trip verified byte-identical.

**Station (automatic):** root cron every 10 min runs `/opt/viam/sorter-ali/tools/sync_cron.sh` (= `station_sync_cron.sh`)
-> `sync_data.py --root /opt/viam/sorter-ali push` (prefers `current/sync_data.py`, falls back to `tools/`). It skips
while any `python3 ... sort.py` runs, so uploads never compete with a live run; log `/opt/viam/sorter-ali/sync.log`.
Models are not in the cron: push them with `tools/sync_cron.sh --models '<name>'` on the station.
Auth: Ali's HF token in `/root/.cache/huggingface/token` (0600; Ali chose this over a repo-scoped token). Replace it with
a fine-grained token (write: this repo only) when convenient. Remove: `crontab -e` (delete the line), `rm` the token.
Same-name bundles trained separately on laptop and station (e.g. `any_cardboard_v2`) are refused as collisions: rename one.

Rules it enforces: unchanged runs are skipped (cheap, idempotent); a run edited later (e.g. a new `exclude.json`) is
re-pushed; a run name already shared from another host with different content is refused (name collision); `pull` never
overwrites a local run that differs from the shared copy; nothing is ever deleted in the repo; `dash/` is not uploaded.
Runs from before 15:31 have no `meta.json`: they are shared as-is, with labels from `decisions.jsonl` (index
`without_meta`). Every push prints its commit: record it with a model to know exactly which data trained it.

Run names use the clock of the machine that collected them (laptop EST, station MST/Phoenix), so name order is not
time order across machines; the timestamps inside `decisions.jsonl` carry their offset.
