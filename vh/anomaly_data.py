"""Curated collection runs -> cropped samples, split by whole pick (never by view/frame).

Runs must be selected explicitly. This does not assume all historic runs are good quality.
A held-out pick of the SAME physical part is not an independent part-generalization test.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from .anomaly import CROP_POLICY, context_crop, group_key


def split_picks(pick_ids, seed=17):
    picks = sorted(set(pick_ids), key=lambda p: hashlib.sha256(f"{seed}:{p}".encode()).hexdigest())
    if len(picks) < 5:
        raise ValueError("At least 5 successful good picks required for train/calibration/test")
    n = max(1, len(picks) // 4)
    return {p: "calibration" if i < n else "test" if i < 2 * n else "train" for i, p in enumerate(picks)}


def collect_samples(run_dirs, part_type, background):
    records, skipped = [], []
    for root in map(Path, run_dirs):
        for line in (root / "decisions.jsonl").read_text().splitlines():
            row = json.loads(line)
            pick = f"{root.name}/item_{row['item']:03d}"
            folder = root / f"item_{row['item']:03d}"
            # part_type "any": one model per view over every part type's good picks (the judged run can't know the type)
            if row.get("decision") != "collect" or (part_type != "any" and row.get("type") != part_type):
                skipped.append({"pick": pick, "reason": "not a completed collection of requested type"})
                continue
            if not (folder / "meta.json").exists():
                skipped.append({"pick": pick, "reason": "missing meta.json (legacy data needs curation)"})
                continue
            meta = json.loads((folder / "meta.json").read_text())
            pose = row.get("pose", meta.get("pose"))
            if pose not in {"lying", "upright"}:
                skipped.append({"pick": pick, "reason": "unknown held pose"})
                continue
            common = {"pick_id": pick, "part_type": part_type, "pose": pose, "background": background,
                      "label": row.get("label", meta.get("label")), "source_run": str(root)}
            tops = [(name, v) for name, v in meta.get("top", {}).items() if v.get("bbox")]
            if tops:
                name, value = sorted(tops, key=lambda p: int(p[0].split('_')[-1]))[-1]
                bbox = value["bbox"]
                with Image.open(folder / f"{name}.jpg") as im:      # 640x480 before 17:05, 1280x720 after
                    w, h = im.size
                if bbox[0] > 3 and bbox[1] > 3 and bbox[2] < w - 4 and bbox[3] < h - 4:
                    records.append({**common, "view": "top", "image": str(folder / f"{name}.jpg"), "bbox": bbox})
                else:
                    skipped.append({"pick": pick, "reason": "top crop touches frame border"})
            for view, value in meta.get("views", {}).items():
                records.append({**common, "view": view, "image": str(folder / f"web_{view}.jpg"), "bbox": value["crop_box"]})
    return records, skipped


def build_dataset(run_dirs, output, part_type, background, seed=17):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite dataset: {output}")
    records, skipped = collect_samples(run_dirs, part_type, background)
    good = [r['pick_id'] for r in records if r['label'] == 'good']
    splits = split_picks(good, seed)
    output.mkdir(parents=True)
    samples = []
    for n, r in enumerate(records):
        split = splits[r['pick_id']] if r['label'] == 'good' else 'test'
        try:
            crop, box = context_crop(r['image'], r['bbox'])
        except (ValueError, OSError) as e:
            skipped.append({'pick': r['pick_id'], 'view': r['view'], 'reason': str(e)})
            continue
        filename = f'images/{n:05d}.png'
        (output / 'images').mkdir(exist_ok=True)
        crop.save(output / filename)
        samples.append({**r, 'image': filename, 'source_image': r['image'], 'crop': box, 'split': split,
                        'group': group_key(part_type, r['pose'], r['view'], background)})
    manifest = {'schema': 1, 'crop_policy': CROP_POLICY, 'seed': seed, 'samples': samples, 'skipped': skipped,
                'limitations': ['Pick-level split; samples may be the same physical item.',
                                'No rotation normalization or part/background masking in this baseline.',
                                'Background labels are supplied by the operator for explicitly selected runs.']}
    (output / 'dataset.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def groups(dataset):
    out = defaultdict(list)
    for sample in dataset['samples']:
        out[sample['group']].append(sample)
    return dict(out)
