"""catalog.py: runs from two clocks sort by real time, excluded and failed picks stay out of the usable counts,
and a pick shows the bundles that list it. Offline, temp folders only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog  # noqa: E402


def make_run(runs, name, offset, rows, meta):
    d = runs / name
    d.mkdir(parents=True)
    with open(d / "decisions.jsonl", "w") as f:
        for n, decision in rows:
            (d / f"item_{n:03d}").mkdir()
            (d / f"item_{n:03d}" / "top_1.jpg").write_bytes(b"x")
            (d / f"item_{n:03d}" / "meta.json").write_text(json.dumps(dict(meta, item=n)))
            row = {"item": n, "decision": decision, "reason": "good" if decision == "collect" else "could not grasp",
                   "t_seen": f"2026-11-13T17:00:0{n}.000{offset}"}
            if decision == "collect":
                row.update(label=meta["label"], type=meta["type"])
            f.write(json.dumps(row) + "\n")
    return d


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name) / "runs"
        meta = {"label": "good", "type": "hex_nut", "background": "cardboard",
                "camera": {"width_px": 1280, "height_px": 720}}
        make_run(self.runs, "20261113_173000_collect", "-07:00", [(1, "collect"), (2, "collect"), (3, "none")], meta)
        make_run(self.runs, "20261113_180000_collect", "-05:00", [(1, "collect")], meta)
        (self.runs / "20261113_173000_collect" / "exclude.json").write_text('{"item_002": "bad crop"}')
        bundle = self.runs / "_shared" / "models" / "m1"
        bundle.mkdir(parents=True)
        (bundle / "bundle.json").write_text(json.dumps({"crop_policy": "p", "models": {"hex_nut|lying|top|cardboard": {
            "margin": 1.03, "train_pick_ids": ["20261113_180000_collect/item_001"], "calibration_pick_ids": [],
            "test_pick_ids": []}}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan(self):
        cat = catalog.scan(self.runs)
        names = [r["name"] for r in cat["runs"]]
        # the station run is named 17:30 on a clock 2 h behind: it happened at 19:30 EST, after the laptop's 18:00
        self.assertEqual(names, ["20261113_180000_collect", "20261113_173000_collect"])
        station = cat["runs"][1]
        self.assertEqual((station["host"], station["est"], station["mst"]), ("station", "19:30", "17:30"))
        self.assertEqual((station["attempts"], station["captured"], station["usable"]), (3, 2, 1))
        self.assertEqual(cat["summary"]["cells"]["current"], {"hex_nut|good": 2})
        self.assertEqual(cat["runs"][0]["items"][0]["used_by"], {"m1": "train"})
        self.assertIn("| 19:30 | `20261113_173000_collect` | station |", catalog.markdown(cat))


if __name__ == "__main__":
    unittest.main()
