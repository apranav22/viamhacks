"""Read-only evidence for Claude's supervision loop; never trains, activates or commands hardware.

python monitor_quality.py --root /opt/viam/sorter-ali --watch
Writes quality/latest.json atomically and emits changed quality reports to stdout. A consuming Claude
session must actually read these reports and take action; this program is not an LLM orchestrator.
Metrics use recorded held-out labels, NOT teacher guesses. Unknown labels and incomplete picks are excluded.
"""
import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

from data_explorer import activity

VIEWS = {'lying': ['top', 'front', 'yaw-20', 'yaw+35', 'pitch-25'],
         'upright': ['top', 'end', 'side0', 'side+120', 'side-120']}


def truth(label):
    if label == 'good':
        return 'good'
    if label in {'tape', 'marker', 'other', 'defective', 'bad'} or str(label).startswith('other:'):
        return 'defective'
    return None


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def measures(counts):
    tp, tn, fp, fn = (counts.get(k, 0) for k in ('TP', 'TN', 'FP', 'FN'))
    def ratio(n, d):
        return n / d if d else None
    return dict(n=tp+tn+fp+fn, accuracy=ratio(tp+tn, tp+tn+fp+fn),
                precision=ratio(tp, tp+fp), recall=ratio(tp, tp+fn), specificity=ratio(tn, tn+fp))


def bundle_report(path):
    """Aggregate saved test scores with the same all-required-views acceptance rule as sort.py.

    These are anomaly-only offline results, not tape-fused live sorting outcomes. Training/calibration
    overlap is excluded across the entire bundle. Repeated physical items remain an explicit limitation.
    """
    raw = path.read_bytes()
    bundle = json.loads(raw)
    entries = list(bundle.get('models', {}).values())
    contaminated = {p for e in entries for k in ('train_pick_ids', 'calibration_pick_ids') for p in e.get(k, [])}
    picks = defaultdict(list)
    for e in entries:
        for row in e.get('test_results', []):
            if row.get('pick_id'):
                picks[row['pick_id']].append((e, row))
    counts = {k: 0 for k in ('TP', 'TN', 'FP', 'FN')}
    excluded, results = Counter(), []
    for pick, rows in sorted(picks.items()):
        labels = {truth(r.get('label')) for _, r in rows}
        poses = {e.get('pose') for e, _ in rows}
        reason = None
        if pick in contaminated:
            reason = 'train/calibration overlap'
        elif None in labels or len(labels) != 1:
            reason = 'unknown/conflicting reference label'
        elif len(poses) != 1 or next(iter(poses)) not in VIEWS:
            reason = 'unknown/conflicting pose'
        required = VIEWS.get(next(iter(poses)), []) if len(poses) == 1 else []
        by_view = defaultdict(list)
        for e, r in rows:
            by_view[e.get('view')].append((e, r))
        if not reason and any(len(by_view[v]) != 1 for v in required):
            reason = 'missing/duplicate required views'
        scores = {}
        if not reason:
            for view in required:
                e, r = by_view[view][0]
                score, threshold = r.get('score'), e.get('threshold')
                if (not isinstance(score, (int, float)) or not isinstance(threshold, (int, float))
                        or not math.isfinite(score) or not math.isfinite(threshold) or threshold <= 0):
                    reason = 'invalid score/threshold'
                    break
                scores[view] = dict(score=score, threshold=threshold, ratio=score/threshold)
        if reason:
            excluded[reason] += 1
            results.append(dict(pick_id=pick, excluded=reason))
            continue
        actual = next(iter(labels))
        prediction = 'reject' if any(s['ratio'] >= 1 for s in scores.values()) else 'good'
        cell = ('TP' if prediction == 'reject' else 'FN') if actual == 'defective' else ('FP' if prediction == 'reject' else 'TN')
        counts[cell] += 1
        results.append(dict(pick_id=pick, actual=actual, prediction=prediction, cell=cell, scores=scores,
                            reference_label=rows[0][1].get('label')))
    return dict(name=path.parent.name, bundle_sha256=hashlib.sha256(raw).hexdigest(),
                modified=path.stat().st_mtime, counts=counts, metrics=measures(counts), picks=results,
                excluded=dict(excluded), reference='recorded dataset labels; not independently human-verified here',
                scope='offline anomaly-only whole-pick fusion; not live tape-fused sorting',
                limitations=bundle.get('limitations', []) + ['Physical-item independence and unseen-defect holdout not verified.'])


def job_report(path):
    job = read_json(path)
    if not isinstance(job, dict):
        return dict(id=path.stem, state='invalid job metadata')
    # Use filename for neighboring files; never trust paths supplied in job metadata.
    ex, log = path.with_suffix('.exit'), path.with_suffix('.log')
    try:
        code = ex.read_text().strip()
    except OSError:
        code = None
    try:
        os.kill(int(job.get('pid')), 0)
        alive = True
    except (OSError, TypeError, ValueError):
        alive = False
    try:
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 32768))
            tail = stream.read().decode(errors='replace').splitlines()[-35:]
    except OSError:
        tail = []
    markers = [('DEVICE ', 'device benchmark'), ('BUNDLE ', 'bundle exported'),
               ('EXPORTED ', 'group exported'), ('FEATURES executed', 'coreset / export'), ('FIT ', 'fitting group')]
    stage = next((stage for line in reversed(tail) for marker, stage in markers if line.startswith(marker)), 'not instrumented')
    state = ('completed' if code == '0' else 'failed') if code is not None else 'running' if alive else 'lost'
    return dict(id=path.stem, label=job.get('label'), state=state, exit=code,
                started=job.get('started'), stage=stage, log=tail,
                log_updated=log.stat().st_mtime if log.exists() else None,
                progress=None, progress_note='No invented percentage; stage inferred from logged markers.')


def snapshot(root):
    root = Path(root)
    models, alerts = [], []
    for path in sorted((root/'models').glob('*/bundle.json')):
        try:
            model = bundle_report(path)
            models.append(model)
            c = model['counts']
            if c['FN'] or c['FP']:
                alerts.append(dict(kind='model_errors', model=model['name'], false_negatives=c['FN'], false_positives=c['FP']))
            if not model['metrics']['n']:
                alerts.append(dict(kind='no_evaluable_picks', model=model['name']))
            elif not c['TP'] + c['FN']:
                alerts.append(dict(kind='no_defect_test', model=model['name']))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            alerts.append(dict(kind='invalid_bundle', model=path.parent.name, error=str(e)[:160]))
    jobs = [job_report(p) for p in sorted((root/'jobs').glob('*.json'), reverse=True)[:12]]
    for job in jobs:
        if job['state'] in {'failed', 'lost', 'invalid job metadata'}:
            alerts.append(dict(kind='job_failure', job=job['id'], state=job['state']))
    if not models:
        alerts.append(dict(kind='no_model_evidence'))
    try:
        active = (root/'models'/'ACTIVE').read_text().strip()
    except OSError:
        active = None
    return dict(schema=1, checked=time.time(), host=os.uname().nodename, activity=activity(),
                active_bundle=active, models=models, jobs=jobs, alerts=alerts,
                supervision=dict(consumer='unverified', automatic_retraining=False, automatic_activation=False,
                    note='Claude must consume reports, diagnose failures and track interventions. This monitor does not wake Claude.'),
                caveats=['Counts are per pick, not per view; models must not be pooled into a single accuracy.',
                         'Recorded dataset labels are distinct from independent human-confirmed evaluation.',
                         'A passing job is not proof of model quality. No ground truth means no verified accuracy.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=float, default=15)
    args = parser.parse_args()
    if args.interval < 2:
        parser.error('--interval must be at least two seconds')
    output = args.root/'quality'
    output.mkdir(parents=True, exist_ok=True)
    previous = None
    while True:
        report = snapshot(args.root)
        temporary = output/f'.latest.{os.getpid()}.tmp'
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False))
        os.replace(temporary, output/'latest.json')
        signal = dict(models=[dict(name=m['name'], hash=m['bundle_sha256'], counts=m['counts']) for m in report['models']],
                      jobs=report['jobs'], alerts=report['alerts'], activity=report['activity'])
        fingerprint = hashlib.sha256(json.dumps(signal, sort_keys=True).encode()).hexdigest()
        if fingerprint != previous or not args.watch:
            print(json.dumps(dict(checked=report['checked'], report=str(output/'latest.json'),
                                  models=signal['models'], alerts=report['alerts'], consumer='unverified')), flush=True)
            previous = fingerprint
        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
