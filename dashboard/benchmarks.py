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
