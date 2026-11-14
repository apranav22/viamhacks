"""Offline anomaly-only candidate calibration. No robot imports or live activation.

score: rescore a bundle's frozen, already-cropped dataset with the existing OpenVINO runtime.
report: require reviewed specimen identities/roles and an explicit good-reject budget; compare
bundle thresholds + logged tape rule against a calibrated anomaly-only item-level policy.

Dataset 'test' defaults to DEVELOPMENT, not an untouched audit. Routing is the dataset's supplied
category (oracle diagnostic), NOT live size classification. See docs/ANOMALY_CALIBRATION.md.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, data):
    path = Path(path)
    if path.exists():
        raise ValueError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write('\n')


def fit_cutoff(values, alpha):
    """Finite-sample upper good-score quantile; reject strictly ABOVE the cutoff.

    Inputs must be independent good specimen maxima, not frames. Rank n+1 means there
    is insufficient calibration evidence for a finite cutoff at this budget.
    """
    if not 0 < alpha < 1:
        raise ValueError('good-reject budget must be strictly between 0 and 1')
    values = sorted(values)
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('calibration requires finite nonnegative good scores')
    k = math.ceil((len(values) + 1) * (1 - alpha))
    return values[k - 1] if k <= len(values) else None


def item_records(scored, identities, views):
    """Preserve invalid/missing views as operational failures, not silently dropped examples."""
    rows = scored['rows']
    original_cal = set(scored.get('model_calibration_pick_ids', []))
    picks = {r['pick_id'] for r in rows} | set(scored['train_pick_ids']) | original_cal
    missing = picks - set(identities)
    if missing:
        raise ValueError(f'Missing reviewed specimen identity/role for {len(missing)} picks: {sorted(missing)[:3]}')
    roles = defaultdict(set)
    for pick in picks:
        i = identities[pick]
        if not i.get('specimen_id') or i.get('role') not in {'train', 'calibration', 'development', 'audit'}:
            raise ValueError(f'Invalid identity/role: {pick}')
        if pick in scored['train_pick_ids'] and i['role'] != 'train':
            raise ValueError(f'Training pick cannot be relabeled held-out: {pick}')
        roles[i['specimen_id']].add(i['role'])
    original_cal_specimens = {identities[p]['specimen_id'] for p in original_cal}
    if any(i['role'] == 'audit' and i['specimen_id'] in original_cal_specimens for i in identities.values()):
        raise ValueError('Original model calibration specimen cannot become an untouched audit specimen')
    if any(len(r) != 1 for r in roles.values()):
        raise ValueError('Physical specimen crosses roles (including before/after defect changes)')
    grouped = defaultdict(dict)
    for r in rows:
        if r['view'] in grouped[r['pick_id']]:
            raise ValueError(f"Duplicate view: {r['pick_id']} {r['view']}")
        grouped[r['pick_id']][r['view']] = r
    result = []
    for pick, vr in sorted(grouped.items()):
        first = next(iter(vr.values()))
        for field in ('label', 'category', 'pose', 'background'):
            if len({r[field] for r in vr.values()}) != 1:
                raise ValueError(f'Inconsistent {field}: {pick}')
        if first['label'] in {'unlabeled', 'unknown', '', None}:
            label = None
        else:
            label = 'good' if first['label'] == 'good' else 'defect'
        ratios, tapes, errors, sources = [], [], [], []
        for v in views:
            r = vr.get(v)
            if not r or r['status'] != 'ok':
                errors.append(f'{v}: {r.get("detail", r["status"]) if r else "missing"}')
                continue
            s, t = r['score'], r['threshold']
            if s is None or t is None or not math.isfinite(s) or not math.isfinite(t) or s < 0 or t <= 0:
                errors.append(f'{v}: invalid score/threshold')
                continue
            ratios.append(s / t)
            sources.append(r.get('source_image'))
            tapes.append(None if r.get('tape') is None else r['tape'] > (0.01 if v == 'top' else 0.04))
        ratio = max(ratios) if not errors and ratios else None
        # Baseline = original bundle anomaly thresholds OR recorded tape fractions.
        # Missing tape cannot be treated as a negative: baseline is explicitly unassessable.
        baseline = True if errors or any(x >= 1 for x in ratios) or any(t is True for t in tapes) else (
            None if any(t is None for t in tapes) else False)
        result.append({'pick_id': pick, **identities[pick], 'label': label, 'defect_label': first['label'],
                       'category': first['category'], 'group': '|'.join(first[f] for f in ('category', 'pose', 'background')),
                       'ratio': ratio, 'baseline_reject': baseline, 'errors': errors, 'images': sources})
    return result


def metrics(items, key):
    labeled = [r for r in items if r['label'] is not None]
    assessed = [r for r in labeled if r[key] is not None]
    good = [r for r in assessed if r['label'] == 'good']
    defect = [r for r in assessed if r['label'] == 'defect']
    fr = sum(r[key] for r in good)
    misses = sum(not r[key] for r in defect)
    return {'items': len(items), 'independent_specimens': len({r['specimen_id'] for r in items}),
            'unknown_labels': len(items) - len(labeled), 'unassessable': len(labeled) - len(assessed),
            'good': len(good), 'good_rejected': fr, 'good_reject_rate': fr / len(good) if good else None,
            'defects': len(defect), 'defects_missed': misses,
            'operational_defect_reject_rate': 1 - misses / len(defect) if defect else None,
            'confirmed_defect_flags': sum(r[key] and not r['errors'] and not (
                key == 'candidate_reject' and r.get('candidate_uncertain')) for r in defect),
            'invalid_items': sum(bool(r['errors']) for r in items)}


def report(scored, identities, views, alpha):
    if not views or len(set(views)) != len(views):
        raise ValueError('required views must be nonempty and unique')
    if not 0 < alpha < 1:
        raise ValueError('good-reject budget must be strictly between 0 and 1')
    items = item_records(scored, identities, views)
    calibration = defaultdict(dict)
    for r in items:
        if r['role'] != 'calibration':
            continue
        if r['label'] != 'good' or r['ratio'] is None:
            raise ValueError(f"Calibration must contain valid verified-good items: {r['pick_id']}")
        by_specimen = calibration[r['group']]
        by_specimen[r['specimen_id']] = max(by_specimen.get(r['specimen_id'], 0), r['ratio'])
    cutoffs = {g: {'cutoff': fit_cutoff(list(s.values()), alpha), 'specimens': len(s)}
               for g, s in calibration.items()}
    evaluation = [r for r in items if r['role'] in {'development', 'audit'}]
    if not evaluation:
        raise ValueError('No explicit development or audit items to evaluate')
    for r in evaluation:
        t = cutoffs.get(r['group'], {}).get('cutoff')
        r['candidate_uncertain'] = t is None or r['ratio'] is None
        r['candidate_reject'] = True if r['candidate_uncertain'] else r['ratio'] > t
    summaries = {}
    for role in ('development', 'audit'):
        subset = [r for r in evaluation if r['role'] == role]
        if not subset:
            continue
        slices = {'all': subset}
        for r in subset:
            slices.setdefault('category:' + r['category'], []).append(r)
            slices.setdefault('label:' + str(r['defect_label']), []).append(r)
        summaries[role] = {k: {'baseline': metrics(v, 'baseline_reject'),
                                'candidate': metrics(v, 'candidate_reject'),
                                'uncertain': sum(r['candidate_uncertain'] for r in v)} for k, v in slices.items()}
    return {'schema': 1, 'source': scored['provenance'], 'required_views': views, 'good_reject_budget': alpha,
            'method': 'specimen-max good quantile; strict > cutoff; item=max required-view score/bundle-threshold',
            'cutoffs': cutoffs, 'summaries': summaries, 'items': evaluation,
            'limitations': ['Offline candidate only; no live activation.',
                            'Ground-truth category routing is an oracle diagnostic, not measured live routing quality.',
                            'Finite-sample quantile coverage requires exchangeable independent specimens and fixed model/recipe.',
                            'Repeated picks are reported, not treated as independent specimens.',
                            'Missing/insufficient calibration rejects uncertain; that is not a true detected defect.',
                            'Tape baseline uses recorded fractions (not recomputed); missing values are unassessable.',
                            'No calibration conclusion is transferable across devices, recipes or model versions.']}


def score_dataset(bundle, dataset, device):
    # Delayed import: report/tests have no OpenVINO or robot dependency.
    from vh.anomaly import AnomalyModels
    b = json.loads(bundle.read_text())
    ds = json.loads(dataset.read_text())
    if b['crop_policy'] != ds['crop_policy']:
        raise ValueError('Dataset and bundle crop policies differ; regenerate matching frozen crops')
    models = AnomalyModels(bundle, device)
    backgrounds = {s['background'] for s in ds['samples']}
    if len(backgrounds) != 1:
        raise ValueError('Score one capture background at a time')
    models.warm('auto', next(iter(backgrounds)))
    train_ids = sorted({p for e in b['models'].values() for p in e['train_pick_ids']})
    hashes = {str(bundle.name): sha(bundle)}
    for e in b['models'].values():
        xml = bundle.parent / e['xml']
        for p in (xml, xml.with_suffix('.bin')):
            hashes[str(p.relative_to(bundle.parent))] = sha(p)
    rows, log_cache = [], {}
    for s in ds['samples']:
        if s['source_run'] not in log_cache:
            run = Path(s['source_run'])
            log = run / 'decisions.jsonl'
            log_cache[s['source_run']] = {f"item_{r['item']:03d}": r for r in
                (json.loads(line) for line in log.read_text().splitlines() if line.strip())} if log.exists() else {}
        old = log_cache[s['source_run']].get(s['pick_id'].split('/')[-1], {})
        # Dataset images are ALREADY cropped. No second crop; runtime owns final resize/normalization.
        image = dataset.parent / s['image']
        result = models.score(str(image), s['part_type'], s['pose'], s['view'], s['background'])
        rows.append({'pick_id': s['pick_id'], 'label': s['label'], 'category': s['part_type'],
                     'pose': s['pose'], 'background': s['background'], 'view': s['view'],
                     'source_image': s.get('source_image', str(image)), 'image_sha256': sha(image),
                     'status': result.status, 'score': result.score, 'threshold': result.threshold,
                     'detail': result.detail, 'infer_ms': result.ms,
                     'dataset_split': s['split'],
                     'tape': old.get('scores', {}).get(s['view'], {}).get('tape')})
    return {'schema': 1, 'provenance': {'bundle_sha256': sha(bundle), 'model_files': hashes,
            'dataset_sha256': sha(dataset), 'crop_policy': b['crop_policy'], 'device': device,
            'precision': 'plugin default' if device == 'NPU' else 'f32', 'routing': 'dataset-known-category'},
            'train_pick_ids': train_ids,
            'model_calibration_pick_ids': sorted({p for e in b['models'].values() for p in e['calibration_pick_ids']}),
            'rows': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('score')
    s.add_argument('--bundle', type=Path, required=True)
    s.add_argument('--dataset', type=Path, required=True)
    s.add_argument('--device', choices=['CPU', 'GPU', 'NPU'], required=True)
    s.add_argument('--out', type=Path, required=True)
    t = sub.add_parser('specimens', help='write a blank identity/role template; never invent specimen identities')
    t.add_argument('--scores', type=Path, required=True)
    t.add_argument('--out', type=Path, required=True)
    r = sub.add_parser('report')
    r.add_argument('--scores', type=Path, required=True)
    r.add_argument('--specimens', type=Path, required=True, help='reviewed mapping pick_id -> {specimen_id, role}')
    r.add_argument('--views', nargs='+', required=True)
    r.add_argument('--max-good-reject-rate', type=float, required=True)
    r.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error(f'Refusing to overwrite {a.out}')
    try:
        if a.cmd == 'score':
            data = score_dataset(a.bundle, a.dataset, a.device)
        elif a.cmd == 'specimens':
            scored = json.loads(a.scores.read_text())
            train = set(scored['train_pick_ids'])
            picks = train | set(scored.get('model_calibration_pick_ids', [])) | {r['pick_id'] for r in scored['rows']}
            data = {p: {'specimen_id': None, 'role': 'train' if p in train else None} for p in sorted(picks)}
        else:
            data = report(json.loads(a.scores.read_text()), json.loads(a.specimens.read_text()),
                          a.views, a.max_good_reject_rate)
            data['score_file_sha256'] = sha(a.scores)
            data['specimen_file_sha256'] = sha(a.specimens)
        save_new(a.out, data)
    except (ValueError, KeyError, OSError) as e:
        p.error(str(e))
    print(f'Wrote {a.out}')
    if a.cmd == 'report':
        print(json.dumps(data['summaries'], indent=2))


if __name__ == '__main__':
    main()
