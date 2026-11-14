"""Read-only, frozen-membership model comparisons; no inference or robot access.
[codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote


class Benchmarks:
    def __init__(self, history, definitions):
        self.history = history
        self.definitions = Path(definitions)

    def index(self):
        return {'benchmarks': [dict(id=p.stem, **json.loads(p.read_text()))
                               for p in sorted(self.definitions.glob('*.json'))]}

    @staticmethod
    def verdict(score):
        if score.get('status') != 'ok' or not isinstance(score.get('anomalous'), bool):
            return 'unknown'
        return 'reject' if score['anomalous'] else 'accept'

    def compare(self, benchmark_id):
        definition = next((b for b in self.index()['benchmarks'] if b['id'] == benchmark_id), None)
        if not definition:
            raise FileNotFoundError('Benchmark unavailable')
        versions = []
        for path in sorted((self.history.root / '_analysis').glob('*.json')):
            report = json.loads(path.read_text())
            if report.get('schema') != 'dashboard-replay-v1':
                continue
            entries = {}
            for row in report.get('rows', []):
                key = (row.get('pick'), row.get('file'))
                entries.setdefault(key, []).append(row)
            rows, issues = [], []
            counts = dict(detected=0, missed=0, false_rejects=0, good_passed=0, unknown=0)
            for member in definition.get('members', []):
                candidates = entries.get((member['pick'], member['file']), [])
                if len(candidates) != 1:
                    issues.append('Missing or duplicate benchmark capture')
                    continue
                row = candidates[0]
                try:
                    source = self.history.path(member['pick'] + '/' + member['file'])
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                except (OSError, ValueError):
                    digest = None
                if not digest or digest != member['image_sha256'] or digest != row.get('image_sha256'):
                    issues.append('Capture identity mismatch')
                    continue
                # Every benchmark member must be held out of feature training and calibration.
                if row.get('split') != 'test':
                    issues.append('Benchmark overlaps training/calibration or membership is unverified')
                    continue
                truth = member['label']
                if row.get('label') != truth:
                    issues.append('Recorded labels disagree')
                    continue
                score = row.get('routed') or {}
                oracle = row.get('oracle') or {}
                outcome = self.verdict(score)
                expected = 'accept' if truth == 'good' else 'reject'
                category = ('unknown' if outcome == 'unknown' else 'false_rejects' if truth == 'good' and outcome == 'reject'
                            else 'good_passed' if truth == 'good' else 'detected' if outcome == 'reject' else 'missed')
                counts[category] += 1
                mismatch = row.get('selected_type') != row.get('type')
                if outcome == 'unknown':
                    diagnosis = 'Item type uncertain' if score.get('status') == 'unknown_type' else 'Model result unavailable'
                    explanation = 'No usable routed anomaly verdict. The live policy rejects this item as uncertain.'
                elif outcome != expected and mismatch and self.verdict(oracle) == expected:
                    diagnosis = 'Wrong item type selected'
                    explanation = 'The same crop is classified correctly when its labelled item type selects the bank.'
                elif outcome != expected and mismatch:
                    diagnosis = 'Item type and model score'
                    explanation = 'The selected type is wrong, and supplying the labelled type still does not fix the verdict.'
                elif outcome != expected:
                    diagnosis = 'Model score below threshold' if category == 'missed' else 'Model score above threshold'
                    explanation = 'Type matches the recorded label. The score crosses the decision threshold in the wrong direction; the visual cause is unverified.'
                else:
                    diagnosis, explanation = 'Matches recorded label', 'This verdict agrees with the recorded collection label.'
                rows.append(dict(pick=member['pick'], file=member['file'], label=truth, type=row.get('type'),
                                 selected_type=row.get('selected_type'), category=category, bbox=row.get('bbox'),
                                 image='/api/history/image?path=' + quote(member['pick'] + '/' + member['file'], safe=''),
                                 diagnosis=diagnosis, explanation=explanation, score=score, oracle=oracle))
            bundle = report.get('bundle', '')
            # codex_curated_20261114_003525 is the model the day started with: every later step is compared to it.
            baseline = 'codex_curated_' in bundle
            label = ('Morning baseline: PatchCore' if baseline else
                     'Previous version' if 'each_cardboard_v4' in bundle else report.get('label', path.stem))
            ready = not issues and len(rows) == len(definition.get('members', [])) and bool(rows)
            good = sum(m['label'] == 'good' for m in definition.get('members', []))
            defective = len(definition.get('members', [])) - good
            tp, fp = counts['detected'], counts['false_rejects']
            family = report.get('model_family') or ('efficientad-s' if 'effad' in bundle else 'patchcore')
            versions.append(dict(id=path.stem, label=label, source_label=report.get('label'), bundle=bundle,
                                 baseline=baseline, family=family, type_clf=bool(report.get('type_clf')),
                                 train_picks=report.get('train_picks'), agent=report.get('agent'),
                                 completed=report.get('completed', 0), device=report.get('device'),
                                 ready=ready, issues=sorted(set(issues)), rows=rows if ready else [],
                                 counts=counts if ready else None, good=good, defective=defective,
                                 precision=tp/(tp+fp) if ready and tp+fp else None,
                                 recall=tp/defective if ready and defective else None))
        # Oldest first: the baseline, then each step in the order it was evaluated.
        versions.sort(key=lambda v: (not v['baseline'], v['completed']))
        return dict(benchmark=definition, versions=versions)


# [claude-code/claude-opus-5-5 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/model-compare · 2026-11-14]
# Model x picture matrix for the Models tab: every variant (bundle x routing) on every saved top-camera picture, with
# that picture's role for that model. Built from eval-matrix-v1 reports (tools/eval_matrix.py) plus benchmark-only
# dashboard-replay-v1 reports for bundles with no matrix report. Image identity is re-checked against the saved file.
SPLIT_CODE = {'train': 't', 'calibration': 'c', 'test': 'h', 'unseen': 'u', 'excluded': 'x'}
ROUTING = {'size': 'size routing', 'clf': 'type classifier'}
# Short display names by bundle folder; anything else uses the report's own label.
NAMES = {'codex_curated_20261114_003525': 'PatchCore curated (morning)', 'each_cardboard_v3': 'PatchCore v3 (Fri)',
         'each_cardboard_v4': 'PatchCore v4 (Fri night)', 'any_cardboard_v2': 'PatchCore pooled (one model, all types)',
         'each_cardboard_cvp95_v1': 'PatchCore cv-p95 thresholds', 'effad_top_v1': 'EfficientAD-S v1 (Aayush)',
         'effad_top_v2': 'EfficientAD-S v2 (+ Sat picks)'}


def _bundle_name(path):
    import re
    m = re.search(r'models[\\/]+([^\\/]+)[\\/]+[^\\/]+$', str(path or ''))
    return m.group(1) if m else str(path)


def _verdict(score):
    if not score or score.get('status') != 'ok' or not isinstance(score.get('anomalous'), bool):
        return '?'
    return 'r' if score['anomalous'] else 'a'


def _ratio(score):
    try:
        return round(score['score'] / score['threshold'], 3) if score.get('status') == 'ok' and score['threshold'] > 0 else None
    except (KeyError, TypeError):
        return None


class Matrix:
    _digests = {}

    def __init__(self, history, definitions):
        self.history = history
        self.benchmarks = Benchmarks(history, definitions)

    def digest(self, relative):
        try:
            path = self.history.path(relative)
            key = (str(path), path.stat().st_mtime_ns)
        except (OSError, ValueError, FileNotFoundError):
            return None
        if key not in self._digests:
            self._digests[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return self._digests[key]

    def build(self):
        folder = self.history.root / '_analysis'
        reports = []
        for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
            try:
                report = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(report, dict) and report.get('schema') == 'eval-matrix-v1':
                reports.append((path, report))
        picks, index, mismatched = [], {}, set()

        def pick_index(row):
            key = row['pick'] + '/' + row['file']
            if key not in index:
                if self.digest(key) != row.get('image_sha256'):
                    mismatched.add(key)
                    return None
                index[key] = len(picks)
                picks.append(dict(pick=row['pick'], file=row['file'], type=row.get('type'), label=row.get('label'),
                                  bench=bool(row.get('bench')), bbox=row.get('bbox'),
                                  image='/api/history/image?path=' + quote(key, safe='')))
            return index[key]

        models = []
        for path, report in reports:
            rows = [(pick_index(r), r) for r in report.get('rows', [])]
            covered = {i for i, _ in rows if i is not None}
            for routing in report.get('routings', ['size']):
                cells = {}
                for i, r in rows:
                    if i is None:
                        continue
                    s = r.get(routing) or {}
                    cells[i] = [SPLIT_CODE.get(r.get('split'), 'x'), _verdict(s), _ratio(s), s.get('type')]
                models.append(dict(id=f'{path.stem}:{routing}', bundle=_bundle_name(report.get('bundle')),
                                   name=NAMES.get(_bundle_name(report.get('bundle')), report.get('label', path.stem)), routing=ROUTING.get(routing, routing),
                                   family='EfficientAD-S' if report.get('model_family') == 'efficientad-s' else 'PatchCore',
                                   pooled=bool(report.get('pooled')), train_picks=report.get('train_picks'),
                                   completed=report.get('completed', 0), scope='all', cells=cells, n=len(covered)))
        # Benchmark-only results for bundles that have no full matrix (e.g. a bundle whose manifest is not on this host).
        have = {m['bundle'] for m in models}
        for bench in self.benchmarks.index()['benchmarks']:
            for v in self.benchmarks.compare(bench['id'])['versions']:
                if not v['ready'] or _bundle_name(v['bundle']) in have:
                    continue
                cells = {}
                for r in v['rows']:
                    i = index.get(r['pick'] + '/' + r['file'])
                    if i is not None:
                        cells[i] = ['h', _verdict(r['score']), _ratio(r['score']), r.get('selected_type')]
                models.append(dict(id=f'{v["id"]}:bench', bundle=_bundle_name(v['bundle']),
                                   name=NAMES.get(_bundle_name(v['bundle']), (v.get('source_label') or v['label']).split(' (')[0]), routing='type classifier' if 'type classifier' in (v.get('source_label') or '') else 'size routing',
                                   family='EfficientAD-S' if v.get('family') == 'efficientad-s' else 'PatchCore',
                                   pooled=False, train_picks=None, completed=v.get('completed', 0), scope='benchmark',
                                   cells=cells, n=len(cells)))
        for m in models:
            m['baseline'] = 'codex_curated' in m['bundle'] and m['routing'] == 'size routing'
            m['cells'] = [m['cells'].get(i) for i in range(len(picks))]
        models.sort(key=lambda m: m['completed'])
        return dict(picks=picks, models=models, mismatched=sorted(mismatched),
                    runs=len({p['pick'].split('/')[0] for p in picks}))
