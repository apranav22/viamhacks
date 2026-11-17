"""Evaluate an anomaly bundle (PatchCore or EfficientAD; same OpenVINO contract) on the coverage pipeline views.

python exp_coverage_anomaly.py --bundle models/pc_coverage_v1/bundle.json \
    [--defect-runs runs/A runs/B] [--device CPU] [--out runs/_analysis/pc_coverage_v1-coverage-eval.json]

No robot connection, no training, no threshold changes. Three evidence sources, reported separately:
  1. held-out GOOD test picks from the bundle's own dataset split (false rejects; never seen in train/calibration)
  2. SYNTHETIC defects pasted onto those same held-out good crops (seeded; tape / marker / cutpaste / chip).
     A proxy only: it says whether a view's model reacts to local surface changes, NOT real-defect recall.
  3. REAL defects from --defect-runs (non-good labels), scored through the same crop code. Day-1 defect runs only
     have the top view in common with the coverage pipeline, so this is top-view only unless new runs exist.
Held-out good picks are usually the SAME physical part as training (one specimen per type): not part-generalization.
"""
import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from vh.anomaly import model_crop, group_key
from vh.anomaly_data import collect_samples

KINDS = ('tape', 'marker', 'cutpaste', 'chip')


def rng_for(*parts):
    return random.Random(int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:12], 16))


def synth(image, kind, rng):
    """Local surface change near the crop centre (parts are centred in every coverage crop)."""
    im = image.convert('RGB').copy()
    w, h = im.size
    s = min(w, h)
    cx, cy = w / 2 + rng.uniform(-0.12, 0.12) * w, h / 2 + rng.uniform(-0.08, 0.08) * h
    if kind == 'tape':                       # opaque coloured strip, like the day-1 tape defects
        a, b = rng.uniform(0.10, 0.16) * s, rng.uniform(0.05, 0.08) * s
        col = rng.choice([(40, 90, 200), (230, 200, 40), (235, 235, 235), (200, 40, 40)])
        patch = Image.new('RGBA', (int(2 * a), int(2 * b)), col + (235,))
        patch = patch.rotate(rng.uniform(0, 180), expand=True)
        im.paste(patch, (int(cx - patch.width / 2), int(cy - patch.height / 2)), patch)
    elif kind == 'marker':                   # dark ink stroke
        d = ImageDraw.Draw(im)
        pts = [(cx + rng.uniform(-0.12, 0.12) * s, cy + rng.uniform(-0.06, 0.06) * s) for _ in range(4)]
        d.line(pts, fill=(25, 25, 30), width=max(3, int(0.018 * s)), joint='curve')
    elif kind == 'cutpaste':                 # CutPaste (Li et al. 2021): move a patch of the same image
        pw, ph = int(rng.uniform(0.08, 0.14) * s), int(rng.uniform(0.04, 0.08) * s)
        sx, sy = rng.randrange(0, w - pw), rng.randrange(0, h - ph)
        patch = im.crop((sx, sy, sx + pw, sy + ph)).rotate(rng.choice([90, 180, 270]), expand=True)
        im.paste(patch, (int(cx - patch.width / 2), int(cy - patch.height / 2)))
    elif kind == 'chip':                     # missing material: background colour from the crop border
        border = np.concatenate([np.asarray(im)[:4].reshape(-1, 3), np.asarray(im)[-4:].reshape(-1, 3)])
        col = tuple(int(v) for v in np.median(border, 0))
        r = rng.uniform(0.04, 0.07) * s
        ImageDraw.Draw(im).ellipse((cx - r, cy - r * 0.7, cx + r, cy + r * 0.7), fill=col)
    return im


def auroc(neg, pos):
    """P(score_pos > score_neg), ties count half. None if either side is empty."""
    if not neg or not pos:
        return None
    n = np.asarray(neg)[:, None]
    p = np.asarray(pos)[None, :]
    return float(((p > n).sum() + 0.5 * (p == n).sum()) / (n.size * p.size))


class Scorer:
    def __init__(self, bundle_path, device):
        import openvino as ov
        self.bundle = json.loads(Path(bundle_path).read_text())
        self.root = Path(bundle_path).parent
        self.core, self.device, self.cache = ov.Core(), device, {}

    def __call__(self, key, image):
        entry = self.bundle['models'][key]
        if key not in self.cache:
            req = self.core.compile_model(str(self.root / entry['xml']), self.device).create_infer_request()
            self.cache[key] = req
        size = entry['image_size']
        x = np.asarray(image.convert('RGB').resize(tuple(size), Image.Resampling.BILINEAR), np.float32)
        req = self.cache[key]
        req.infer({0: np.ascontiguousarray(x.transpose(2, 0, 1)[None] / 255)})
        out = next(o for o in req.model_outputs if 'pred_score' in o.get_names())
        return float(req.get_tensor(out).data.reshape(-1)[0])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--defect-runs', nargs='*', default=[], type=Path)
    p.add_argument('--background', default='cardboard')
    p.add_argument('--device', default='CPU')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    score = Scorer(a.bundle, a.device)
    models = score.bundle['models']
    dataset_dir = a.bundle.parent / 'dataset'
    dataset = json.loads((dataset_dir / 'dataset.json').read_text())

    groups = {}
    picks = defaultdict(dict)                 # pick -> view -> anomalous (held-out good)
    synth_hits = defaultdict(list)            # kind -> whole-pick caught (defect on one view, clean other views)
    for key, entry in sorted(models.items()):
        test_ids = set(entry['test_pick_ids'])
        samples = [s for s in dataset['samples'] if s['group'] == key and s['label'] == 'good' and s['pick_id'] in test_ids]
        thr = entry['threshold']
        good, syn = [], defaultdict(list)
        for s in samples:
            with Image.open(dataset_dir / s['image']) as im:
                im.load()
            v = score(key, im)
            good.append(v)
            picks[s['pick_id']][entry['view']] = v >= thr
            for kind in KINDS:
                syn[kind].append(score(key, synth(im, kind, rng_for(s['pick_id'], entry['view'], kind))))
        g = {'part_type': entry['part_type'], 'view': entry['view'], 'threshold': thr,
             'n_train': len(entry['train_pick_ids']), 'n_cal': len(entry['calibration_pick_ids']), 'n_test_good': len(good),
             'good_rejected': sum(v >= thr for v in good), 'good_max_over_thr': max(good) / thr if good else None,
             'synthetic': {k: {'auroc': auroc(good, syn[k]), 'caught': sum(v >= thr for v in syn[k]), 'n': len(syn[k])}
                           for k in KINDS},
             'good_scores': good, 'synthetic_scores': dict(syn)}
        groups[key] = g
        print(f"{key:48s} thr {thr:8.4f} good rej {g['good_rejected']}/{len(good)}  " +
              '  '.join(f"{k} {g['synthetic'][k]['caught']}/{len(good)} auc {g['synthetic'][k]['auroc'] or 0:.2f}" for k in KINDS),
              flush=True)

    # whole pick (conservative fusion: any scored view over threshold rejects)
    by_type = defaultdict(lambda: {'picks': 0, 'rejected': 0, 'views': set()})
    for pick, views in picks.items():
        ty = next(g['part_type'] for k, g in groups.items() if pick in models[k]['test_pick_ids'])
        t = by_type[ty]
        t['picks'] += 1
        t['rejected'] += any(views.values())
        t['views'] |= set(views)
        for kind in KINDS:                    # inject on each view in turn; other views keep their clean verdict
            for view in views:
                key = group_key(ty, 'lying', view, a.background)
                if key not in groups:
                    continue
                g = groups[key]
                i = [s['pick_id'] for s in dataset['samples'] if s['group'] == key and s['label'] == 'good'
                     and s['pick_id'] in set(models[key]['test_pick_ids'])].index(pick)
                hit = g['synthetic_scores'][kind][i] >= g['threshold']
                synth_hits[kind].append(hit or any(v for vv, v in views.items() if vv != view))
    whole = {ty: {'held_out_good_picks': t['picks'], 'good_picks_rejected': t['rejected'], 'views': sorted(t['views'])}
             for ty, t in sorted(by_type.items())}
    whole_synth = {k: {'caught': int(sum(v)), 'n': len(v)} for k, v in synth_hits.items()}

    # real defects (non-good labels) through the same crop code, wherever a model for that group exists
    real = []
    if a.defect_runs:
        records, _ = collect_samples(a.defect_runs, 'each', a.background)
        for r in records:
            if r['label'] == 'good':
                continue
            key = group_key(r['part_type'], r['pose'], r['view'], a.background)
            if key not in models:
                continue
            try:
                crop, _ = model_crop(r['image'], r['bbox'], r['view'])
            except (ValueError, OSError) as e:
                print('SKIP', r['pick_id'], r['view'], e)
                continue
            v = score(key, crop)
            real.append({'pick_id': r['pick_id'], 'label': r['label'], 'group': key, 'score': v,
                         'threshold': models[key]['threshold'], 'caught': v >= models[key]['threshold']})
    real_by = defaultdict(lambda: [0, 0, []])
    for r in real:
        k = real_by[r['group']]
        k[0] += r['caught']
        k[1] += 1
        k[2].append(r['score'])
    real_summary = {k: {'caught': c, 'n': n, 'auroc_vs_held_out_good': auroc(groups[k]['good_scores'], s)}
                    for k, (c, n, s) in sorted(real_by.items())}

    print('\nWHOLE PICK held-out good (any view rejects):')
    for ty, w in whole.items():
        print(f"  {ty:20s} {w['good_picks_rejected']}/{w['held_out_good_picks']} rejected  views {w['views']}")
    print('WHOLE PICK synthetic (defect on one view):', {k: f"{v['caught']}/{v['n']}" for k, v in whole_synth.items()})
    print('REAL defects:', {k: f"{v['caught']}/{v['n']} auc {v['auroc_vs_held_out_good'] or 0:.2f}" for k, v in real_summary.items()} or 'none scored')

    report = {'schema': 1, 'bundle': str(a.bundle), 'device': a.device,
              'backbones': sorted({m.get('backbone', '?') for m in models.values()}),
              'groups': groups, 'whole_pick': whole, 'whole_pick_synthetic': whole_synth,
              'real_defects': real_summary, 'real_defect_rows': real,
              'limitations': ['Synthetic defects are a sensitivity proxy, not real-defect recall.',
                              'Held-out good picks are mostly the same physical specimen as training.',
                              'Thresholds are the bundle\'s own (calibration max x margin); none tuned here.']}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=1))
        print('REPORT', a.out)


if __name__ == '__main__':
    main()
