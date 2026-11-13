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
