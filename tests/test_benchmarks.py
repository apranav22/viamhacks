"""[codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from dashboard.benchmarks import Benchmarks
from dashboard.history import History


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.defs = base/'runs', base/'benchmarks'
        self.defs.mkdir()
        self.item = self.root/'run'/'item_001'
        self.item.mkdir(parents=True)
        (self.root/'_analysis').mkdir()
        self.image = self.item/'top_1.jpg'
        self.image.write_bytes(b'example')
        self.member = dict(pick='run/item_001', file='top_1.jpg', label='good',
                           image_sha256=hashlib.sha256(b'example').hexdigest())
        (self.defs/'frozen.json').write_text(json.dumps(dict(name='Frozen', members=[self.member])))
        self.row = dict(self.member, split='test', type='button_ss_long', selected_type='hex_nut',
                        routed=dict(status='ok', anomalous=True), oracle=dict(status='ok', anomalous=False))
        self.report = self.root/'_analysis'/'candidate.json'
        self.api = Benchmarks(History(self.root), self.defs)

    def compare(self, rows=None):
        self.report.write_text(json.dumps(dict(schema='dashboard-replay-v1', rows=rows or [self.row])))
        return self.api.compare('frozen')['versions'][0]

    def test_wrong_bank_false_reject_has_causal_evidence(self):
        version = self.compare()
        self.assertTrue(version['ready'])
        self.assertEqual(version['counts']['false_rejects'], 1)
        self.assertEqual(version['rows'][0]['diagnosis'], 'Wrong item type selected')

    def test_leakage_blocks_entire_comparison_instead_of_changing_denominator(self):
        self.row['split'] = 'train'
        version = self.compare()
        self.assertFalse(version['ready'])
        self.assertIsNone(version['counts'])
        self.assertEqual(version['rows'], [])

    def test_tampered_image_and_duplicate_entries_block_comparison(self):
        self.assertFalse(self.compare([self.row, self.row])['ready'])
        self.image.write_bytes(b'changed')
        self.assertFalse(self.compare()['ready'])

    def test_unknown_type_is_an_abstention_not_detected_defect(self):
        self.member['label'] = self.row['label'] = 'tape'
        (self.defs/'frozen.json').write_text(json.dumps(dict(name='Frozen', members=[self.member])))
        self.row['routed'] = dict(status='unknown_type', anomalous=None)
        version = self.compare()
        self.assertEqual(version['counts']['unknown'], 1)
        self.assertEqual(version['counts']['detected'], 0)
        self.assertEqual(version['recall'], 0)
        self.assertIsNone(version['precision'])

    def test_wrong_type_does_not_explain_miss_when_known_type_also_misses(self):
        self.member['label'] = self.row['label'] = 'tape'
        (self.defs/'frozen.json').write_text(json.dumps(dict(name='Frozen', members=[self.member])))
        self.row['routed']['anomalous'] = False
        self.assertEqual(self.compare()['rows'][0]['diagnosis'], 'Item type and model score')
