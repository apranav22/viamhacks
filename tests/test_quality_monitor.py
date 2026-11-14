"""Supervision metrics tests; no robot or model runtime required."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor_quality import VIEWS, bundle_report, measures, snapshot


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root/'models'/'candidate'/'bundle.json'
        self.path.parent.mkdir(parents=True)
        self.bundle = {'models': {v: {'view': v, 'pose': 'lying', 'threshold': 10,
            'train_pick_ids': ['leaked'], 'calibration_pick_ids': [],
            'test_results': [dict(pick_id=p, label=l, score=s) for p, l, s in (
                ('tp', 'tape', 11), ('tn', 'good', 9), ('fp', 'good', 12), ('fn', 'marker', 8),
                ('unlabeled', 'unlabeled', 11), ('leaked', 'good', 9))]}
            for v in VIEWS['lying']}}

    def tearDown(self):
        self.temp.cleanup()

    def report(self):
        self.path.write_text(json.dumps(self.bundle))
        return bundle_report(self.path)

    def test_whole_pick_confusion_counts_not_views(self):
        r = self.report()
        self.assertEqual(r['counts'], dict(TP=1, TN=1, FP=1, FN=1))
        self.assertEqual(r['metrics']['n'], 4)
        self.assertEqual(r['metrics']['accuracy'], .5)
        self.assertEqual(r['excluded']['train/calibration overlap'], 1)
        self.assertEqual(r['excluded']['unknown/conflicting reference label'], 1)

    def test_missing_view_not_success(self):
        self.bundle['models']['front']['test_results'] = []
        r = self.report()
        self.assertEqual(r['metrics']['n'], 0)
        self.assertEqual(r['excluded']['missing/duplicate required views'], 4)

    def test_one_above_threshold_view_rejects(self):
        for e in self.bundle['models'].values():
            for row in e['test_results']:
                if row['pick_id'] == 'fn':
                    row['score'] = 11 if e['view'] == 'front' else 8
        self.assertEqual(self.report()['counts']['FN'], 0)
        self.assertEqual(self.report()['counts']['TP'], 2)

    def test_invalid_and_no_evidence(self):
        self.bundle['models']['front']['test_results'][0]['score'] = None
        self.assertEqual(self.report()['excluded']['invalid score/threshold'], 1)
        self.assertIsNone(measures({})['accuracy'])
        self.assertIsNone(measures({'TN': 3})['recall'])

    def test_supervisor_never_assumed_active(self):
        self.report()
        r = snapshot(self.root)
        self.assertEqual(r['supervision']['consumer'], 'unverified')
        self.assertFalse(r['supervision']['automatic_activation'])
        self.assertEqual(r['alerts'][0]['false_negatives'], 1)


if __name__ == '__main__':
    unittest.main()
