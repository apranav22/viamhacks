"""[codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
Historical evidence association and read-only media boundaries. No robot access.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from dashboard.history import History, finite_json


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'runs'
        self.item = self.root / '20261113_173234_sort' / 'item_001'
        self.item.mkdir(parents=True)
        self.history = History(self.root)

    def write(self, path, data):
        path.write_text(json.dumps(data))

    def capture(self, name):
        (self.item / name).write_bytes(b'\xff\xd8example-' + name.encode())

    def decision(self, **extra):
        row = dict(item=1, decision='reject', reason='known: tape (top face)', decided_at_view='top',
                   scores={'top': dict(status='ok', score=11, threshold=10, anomalous=True, ratio=1.1, tape=.03)})
        row.update(extra)
        self.write(self.item.parent / 'decisions.jsonl', row)

    def test_every_attempt_preserved_without_duplicating_derivative(self):
        for name in ['watch.jpg', 'top_1.jpg', 'top_2.jpg', 'web_front.jpg', 'crop_front.jpg']:
            self.capture(name)
        self.decision()
        data = self.history.item(self.item.parent.name, self.item.name)
        self.assertEqual([c['filename'] for c in data['captures']], ['watch.jpg', 'top_1.jpg', 'top_2.jpg', 'web_front.jpg'])
        self.assertTrue(data['unassigned'])
        for c in data['captures'][1:3]:
            self.assertFalse(c['score'])
            self.assertFalse(c['trigger'])
        self.assertIn('crop_front.jpg', data['captures'][3]['crop_url'])

    def test_both_detector_evidence_and_original_trigger_survive(self):
        self.capture('top_1.jpg')
        self.decision()
        c = self.history.item(self.item.parent.name, self.item.name)['captures'][0]
        self.assertTrue(c['score']['anomalous'])
        self.assertEqual(c['tape'], .03)
        self.assertEqual(c['trigger_detector'], 'tape')

    def test_missing_decision_and_empty_attempts_remain_visible(self):
        self.capture('watch.jpg')
        self.write(self.item.parent / 'decisions.jsonl', {'item': 2, 'decision': 'none', 'reason': 'missed'})
        items = self.history.run(self.item.parent.name)['items']
        self.assertEqual(len(items), 2)
        self.assertIsNone(items[0]['decision'])
        self.assertEqual(items[1]['capture_count'], 0)

    def test_verified_replay_is_separate_and_hash_mismatch_is_not_scored(self):
        self.capture('top_1.jpg')
        self.decision(decision='collect', reason='good', decided_at_view=None, scores={})
        folder = self.root / '_analysis'
        folder.mkdir()
        row = dict(pick=self.item.parent.name + '/' + self.item.name, file='top_1.jpg',
                   image_sha256=hashlib.sha256((self.item / 'top_1.jpg').read_bytes()).hexdigest(),
                   routed=dict(status='ok', anomalous=True, score=12, threshold=10))
        self.write(folder / 'replay.json', dict(schema='dashboard-replay-v1', rows=[row]))
        data = self.history.item(self.item.parent.name, self.item.name)
        self.assertEqual(data['record']['decision'], 'collect')
        self.assertFalse(data['captures'][0]['trigger'])
        self.assertTrue(data['evaluations'][0]['scores']['item_001/top_1.jpg']['input_verified'])
        (self.item / 'top_1.jpg').write_bytes(b'changed')
        data = self.history.item(self.item.parent.name, self.item.name)
        self.assertEqual(data['evaluations'][0]['scores']['item_001/top_1.jpg']['status'], 'source_mismatch')

    def test_no_arbitrary_files_or_escaped_symlinks(self):
        outside = self.root.parent / 'private.json'
        self.write(outside, {'secret': 'not-for-serving'})
        (self.item / 'escape.jpg').symlink_to(outside)
        (self.item / 'meta.json').symlink_to(outside)
        with self.assertRaises(FileNotFoundError):
            self.history.image('../private.json')
        with self.assertRaises(FileNotFoundError):
            self.history.image(str((self.item / 'escape.jpg').relative_to(self.root)))
        self.assertEqual(self.history.item(self.item.parent.name, self.item.name)['metadata'], {})
        self.assertEqual(self.history.item(self.item.parent.name, self.item.name)['captures'], [])

    def test_telemetry_images_keep_run_scoped_urls(self):
        dash = self.item.parent / 'dash'
        (dash / 'frames').mkdir(parents=True)
        (dash / 'frames' / '1.bin').write_bytes(b'\xff\xd8camera')
        self.write(dash / 'events.jsonl', {'k': 'look', 'n': 1, 'frame': {'id': 1, 'mime': 'image/jpeg'}})
        event = self.history.telemetry(self.item.parent.name)[0]
        self.assertIn(self.item.parent.name, event['frame']['url'])
        data, mime = self.history.image(f'{self.item.parent.name}/dash/frames/1.bin')
        self.assertEqual(mime, 'image/jpeg')
        self.assertEqual(data, b'\xff\xd8camera')

    def test_nonfinite_legacy_values_are_valid_json_null(self):
        self.assertEqual(finite_json({'score': float('nan'), 'nested': [float('inf')]}), {'score': None, 'nested': [None]})

    def test_frame_id_reuse_cannot_show_a_previous_runs_image(self):
        from dashboard.server import Hub
        hub = Hub(None)
        hub.event({'k': 'run', 'run': 'first'})
        hub._store_frame(1, b'old image', 'image/jpeg')
        hub.event({'k': 'run', 'run': 'second'})
        event = {'k': 'look', 'run': 'second', 'frame': {'id': 1, 'mime': 'image/jpeg'}}
        hub.event(event)
        self.assertFalse(event['frame']['ok'])
        self.assertIsNone(hub.get_frame(1))


if __name__ == '__main__':
    unittest.main()
