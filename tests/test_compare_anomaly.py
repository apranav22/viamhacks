"""Offline calibration and comparison invariants; no robot/OpenVINO dependency."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compare_anomaly import fit_cutoff, report, save_new


def fixture():
    rows, ids = [], {}
    def add(pick, specimen, role, label, value, view='top', status='ok', tape=0):
        ids[pick] = {'specimen_id': specimen, 'role': role}
        rows.append({'pick_id': pick, 'label': label, 'category': 'bolt', 'pose': 'lying',
                     'background': 'cardboard', 'view': view, 'status': status, 'score': value,
                     'threshold': 1, 'tape': tape, 'source_image': f'{pick}/{view}.jpg'})
    for i in range(19):
        add(f'cal/{i}', f'cal-specimen-{i}', 'calibration', 'good', 0.1 + i / 100)
    add('eval/clean', 'clean', 'development', 'good', 0.2, tape=0.03)
    add('eval/tape', 'taped', 'development', 'tape', 0.4)
    add('eval/miss', 'miss', 'development', 'marker', 0.15)
    add('eval/error', 'error', 'development', 'other', None, status='invalid')
    return {'provenance': {'device': 'CPU', 'bundle_sha256': 'fixed'}, 'train_pick_ids': ['train/1'], 'rows': rows}, {
        **ids, 'train/1': {'specimen_id': 'training-specimen', 'role': 'train'}}


class ComparisonTests(unittest.TestCase):
    def test_finite_sample_requirement_and_ties(self):
        self.assertIsNone(fit_cutoff([1] * 18, .05))
        self.assertEqual(fit_cutoff([1] * 19, .05), 1)
        for bad in ([math.nan], [math.inf], [-1], []):
            with self.assertRaises(ValueError):
                fit_cutoff(bad, .05)

    def test_threshold_only_uses_good_calibration_and_counts_errors(self):
        scored, ids = fixture()
        r = report(scored, ids, ['top'], .05)
        self.assertAlmostEqual(r['cutoffs']['bolt|lying|cardboard']['cutoff'], .28)
        m = r['summaries']['development']['all']
        self.assertEqual(m['baseline']['good_rejected'], 1)  # heuristic rejects clean blue plating
        self.assertEqual(m['candidate']['good_rejected'], 0)
        self.assertEqual(m['candidate']['defects_missed'], 1)
        self.assertEqual(m['candidate']['invalid_items'], 1)
        self.assertEqual(m['uncertain'], 1)  # error reject NOT credited as an anomaly detection
        scored['rows'][19]['score'] = 1e9
        self.assertEqual(report(scored, ids, ['top'], .05)['cutoffs'], r['cutoffs'])

    def test_repeated_views_and_picks_do_not_increase_calibration_n(self):
        s, ids = fixture()
        ids['cal/18']['specimen_id'] = ids['cal/17']['specimen_id']
        r = report(s, ids, ['top'], .05)
        self.assertEqual(r['cutoffs']['bolt|lying|cardboard']['specimens'], 18)
        self.assertIsNone(r['cutoffs']['bolt|lying|cardboard']['cutoff'])
        self.assertTrue(all(i['candidate_uncertain'] for i in r['items']))

    def test_specimen_role_leakage_is_blocked_including_defect_modification(self):
        s, ids = fixture()
        ids['eval/tape']['specimen_id'] = ids['cal/0']['specimen_id']
        with self.assertRaisesRegex(ValueError, 'crosses roles'):
            report(s, ids, ['top'], .05)

    def test_training_pick_cannot_be_relabelled_calibration(self):
        s, ids = fixture()
        ids['train/1']['role'] = 'calibration'
        with self.assertRaisesRegex(ValueError, 'Training pick'):
            report(s, ids, ['top'], .05)
        del ids['train/1']
        with self.assertRaisesRegex(ValueError, 'Missing reviewed'):
            report(s, ids, ['top'], .05)

    def test_unknown_label_and_missing_tape_are_not_false_evidence(self):
        s, ids = fixture()
        s['rows'][19]['tape'] = None
        s['rows'][20]['label'] = 'unlabeled'
        r = report(s, ids, ['top'], .05)
        m = r['summaries']['development']['all']
        self.assertEqual(m['baseline']['unassessable'], 1)
        self.assertEqual(m['candidate']['unknown_labels'], 1)

    def test_multi_view_requires_every_view_and_calibrates_item_max(self):
        s, ids = fixture()
        for row in list(s['rows']):
            if row['pick_id'] == 'eval/clean':
                continue  # incomplete eval capture retained, rejects uncertain
            s['rows'].append({**row, 'view': 'front'})
        r = report(s, ids, ['top', 'front'], .05)
        clean = next(i for i in r['items'] if i['pick_id'] == 'eval/clean')
        self.assertTrue(clean['candidate_reject'])
        self.assertTrue(clean['errors'])

    def test_non_good_calibration_and_invalid_budgets_are_rejected(self):
        s, ids = fixture()
        s['rows'][0]['label'] = 'tape'
        with self.assertRaisesRegex(ValueError, 'verified-good'):
            report(s, ids, ['top'], .05)
        for a in (0, 1, -1, math.nan):
            with self.assertRaises(ValueError):
                fit_cutoff([1], a)

    def test_original_model_calibration_is_not_a_fresh_audit(self):
        s, ids = fixture()
        s['model_calibration_pick_ids'] = ['eval/clean']
        ids['eval/clean']['role'] = 'audit'
        with self.assertRaisesRegex(ValueError, 'Original model calibration'):
            report(s, ids, ['top'], .05)

    def test_uncertain_reject_is_not_counted_as_detected_anomaly(self):
        s, ids = fixture()
        r = report(s, ids, ['top'], .05)
        m = r['summaries']['development']['all']['candidate']
        self.assertEqual(m['defects'], 3)
        self.assertEqual(m['confirmed_defect_flags'], 1)  # tape only, not invalid 'other'
        self.assertAlmostEqual(m['operational_defect_reject_rate'], 2 / 3)

    def test_artifacts_are_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'report.json'
            save_new(p, {'ok': True})
            with self.assertRaises(ValueError):
                save_new(p, {'overwrite': True})
            self.assertEqual(json.loads(p.read_text()), {'ok': True})


if __name__ == '__main__':
    unittest.main()
