"""Offline EDA regression tests. Run: python tests/test_site_eda.py

Agent: pi/gpt-6.1-sol · operator: Ali (git Ali, GitHub unknown)
Host: Alis-MacBook-Air.local · branch: ali/pipeline
"""
import csv
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
from eda import analyze, distribution, duplicates, gallery, image_stats, item_tape_max, make_gallery, section, tape_threshold, valid_box, write_exports
from build import html as project_html


class PageStructure(HTMLParser):
    """Track disclosure ancestry without needing a browser or installed parser."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__()
        self.stack, self.nodes = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parents": list(self.stack)}
        self.nodes.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def by_id(self, id):
        return next(n for n in self.nodes if n["attrs"].get("id") == id)

    def disclosures(self, node):
        return [n for n in node["parents"] if n["tag"] == "details"]


class EdaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_dir(self, name="example_collect"):
        p = self.runs / name
        p.mkdir(exist_ok=True)
        return p

    def item(self, run, number, meta=None):
        p = run / f"item_{number:03d}"
        p.mkdir()
        if meta is not None:
            (p / "meta.json").write_text(json.dumps(meta))
        return p

    def image(self, folder, name, size=(100, 80), color="white"):
        path = folder / name
        Image.new("RGB", size, color).save(path)
        return path

    def test_attempts_are_not_completed_and_malformed_tail_is_visible(self):
        run = self.run_dir()
        item = self.item(run, 1, {"label": "good", "type": "bolt", "decision": "none"})
        self.image(item, "top_1.jpg")
        self.item(run, 2)  # empty attempt is retained
        (run / "decisions.jsonl").write_text(json.dumps({"item": 1, "decision": "none"}) + '\n{"item":')
        data = analyze(self.runs)
        self.assertEqual(len(data["picks"]), 2)
        self.assertFalse(any(p["complete"] for p in data["picks"]))
        self.assertEqual(data["picks"][0]["label"], "good")
        self.assertEqual(data["picks"][0]["label_source"], "meta")
        self.assertEqual(len(data["issues"]), 1)

    def test_join_is_run_and_item_and_log_conflicts_are_not_silenced(self):
        for name in ("a_collect", "b_collect"):
            run = self.run_dir(name)
            self.item(run, 1, {"label": "good", "type": "bolt", "pose": "lying"})
            (run / "decisions.jsonl").write_text(json.dumps({"item": 1, "decision": "collect", "t_released": "now", "label": "tape", "type": "bolt"}))
        data = analyze(self.runs)
        self.assertEqual(len(data["picks"]), 2)
        self.assertEqual(len({p["id"] for p in data["picks"]}), 2)
        for p in data["picks"]:
            self.assertTrue(p["complete"])
            self.assertEqual(p["label"], "tape")
            self.assertTrue(any("conflict" in f for f in p["flags"]))
            self.assertFalse(p["readable_multiview"])
            self.assertEqual(len(p["missing_views"]), 4)

    def test_multiview_checks_decoding_and_actual_sensor_dimensions(self):
        run = self.run_dir()
        views = ("front", "yaw-20", "yaw+35", "pitch-25")
        item = self.item(run, 1, {"pose": "lying", "label": "good", "type": "bolt", "top": {"top_1": {"bbox": [1, 1, 20, 20], "cam_t": [0, 0, 362]}},
                                  "views": {v: {"crop_box": [0, 5, 50, 60]} for v in views}})
        self.image(item, "top_1.jpg")
        for view in views:
            self.image(item, f"web_{view}.jpg")
            self.image(item, f"crop_{view}.jpg", (50, 55))
        (run / "decisions.jsonl").write_text(json.dumps({"item": 1, "decision": "collect", "t_released": "now"}))
        data = analyze(self.runs)
        self.assertTrue(data["picks"][0]["readable_multiview"])
        crops = [im for im in data["images"] if im["kind"] == "crop"]
        self.assertTrue(all(im["sensor_edge"] for im in crops))
        (item / "crop_front.jpg").write_bytes(b"broken")
        data = analyze(self.runs)
        self.assertFalse(data["picks"][0]["readable_multiview"])
        self.assertEqual(data["picks"][0]["missing_views"], ["front"])

    def test_duplicates_are_not_raw_crop_double_counting_or_same_pick(self):
        base = {"kind": "crop", "view": "front", "type": "bolt", "label": "good", "readable": True, "sha256": "abc", "dhash": "00"}
        ims = [{**base, "pick": "a", "path": "a.jpg"}, {**base, "pick": "b", "path": "b.jpg"},
               {**base, "pick": "a", "path": "raw.jpg", "kind": "web"}]
        pairs = duplicates(ims)
        self.assertEqual(len(pairs["exact_pairs"]), 1)
        self.assertEqual(pairs["near_pairs"], [])
        ims[1]["sha256"] = "other"
        self.assertEqual(duplicates(ims)["near_pairs"][0]["distance"], 0)

    def test_stats_and_valid_boxes(self):
        folder = self.item(self.run_dir(), 1)
        stats = image_stats(self.image(folder, "watch.jpg", color="black"))
        self.assertEqual(stats["focus"], 0)
        self.assertEqual(stats["dark_pct"], 100)
        self.assertTrue(valid_box([0, 0, 100, 80], 100, 80))
        for box in (None, [10, 10, 5, 20], [-1, 0, 10, 10], [0, 0, 101, 80]):
            self.assertFalse(valid_box(box, 100, 80))
        self.assertEqual(distribution([None, 10, 20])["p95"], 19.5)
        self.assertIsNone(distribution([])["p50"])

    def test_threshold_is_read_without_executing_robot_code(self):
        source = self.root / "sort.py"
        source.write_text('raise RuntimeError("must not execute")\nTAPE_FRAC = 0.02\n')
        self.assertEqual(tape_threshold(source), .02)
        source.write_text('TAPE_FRAC = float("0.02")\n')
        self.assertIsNone(tape_threshold(source))
        self.assertEqual(item_tape_max({"top_tape": 0, "scores": {"front": {"tape": .0071}}}), .0071)
        self.assertIsNone(item_tape_max({}))

    def test_scope_exports_gallery_and_safety_flag(self):
        self.item(self.run_dir("fake_dry"), 1)  # excluded
        run = self.run_dir("20261113_154405_collect")
        item = self.item(run, 1, {"label": "good", "type": "bolt"})
        self.image(item, "top_1.jpg")
        d = analyze(self.runs)
        self.assertEqual(len(d["picks"]), 1)
        self.assertTrue(any("safety review" in f for f in d["picks"][0]["flags"]))
        output = self.root / "site"
        output.mkdir()
        (output / "img").mkdir()
        d["gallery"] = make_gallery(d, self.root, output / "img")
        self.assertEqual(len(d["gallery"]), 1)
        self.assertTrue((output / d["gallery"][0]["src"]).exists())
        write_exports(d, output / "data")
        export = json.loads((output / "data" / "eda.json").read_text())
        self.assertEqual(len(export["images"]), 1)
        with (output / "data" / "eda_picks.csv").open() as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_render_uses_snapshot_and_escapes_operator_labels(self):
        run = self.run_dir()
        self.item(run, 1, {"type": "<unsafe>", "label": "good"})
        d = analyze(self.runs)
        output = self.root / "site"
        write_exports(d, output / "data")
        with patch("eda.HERE", output):
            html = section()
        self.assertIn('&lt;unsafe&gt;', html)
        self.assertNotIn('<unsafe>', html)
        self.assertIn('id="eda-ledger"', html)
        self.assertIn('data/eda_picks.csv', html)
        self.assertIn('Snapshot ', html)


class CompactPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        runs = self.root / "runs"
        runs.mkdir()
        write_exports(analyze(runs), self.root / "data")
        self.snapshot = patch("eda.HERE", self.root)
        self.snapshot.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.snapshot.stop)

    def test_reference_links_are_preserved_inside_disclosures(self):
        page = PageStructure(project_html())
        ids = [n["attrs"]["id"] for n in page.nodes if "id" in n["attrs"]]
        self.assertEqual(len(ids), len(set(ids)), "deep links must be unique")
        for id in ("states", "route", "recovery", "scoring", "asym", "cases", "coverage", "decide", "recon", "evals", "station", "open"):
            parents = page.disclosures(page.by_id(id))
            self.assertTrue(parents, id)
            self.assertTrue(all("open" not in p["attrs"] for p in parents), id)
        for node in page.nodes:
            href = node["attrs"].get("href", "")
            if href.startswith("#"):
                self.assertIn(href[1:], ids)

    def test_progress_is_dated_and_collapsed_not_presented_as_live(self):
        page = PageStructure(project_html())
        progress = page.by_id("progress")
        estimates = [n for n in page.nodes if "big2" in n["attrs"].get("class", "").split()]
        self.assertTrue(estimates)
        self.assertTrue(all(progress in n["parents"] and page.disclosures(n) for n in estimates))
        self.assertIn("Historical estimates, not live completion or model results", project_html())

    def test_gallery_keeps_all_groups_but_opens_one_released_example(self):
        groups = [{"type": "<bolt>", "label": "good", "complete": complete,
                   "src": f"img/example_{i}.jpg", "picks": [f"run/item_{i}"]}
                  for i, complete in enumerate((False, True, True))]
        rendered = gallery(groups)
        page = PageStructure(rendered)
        details = [n for n in page.nodes if n["tag"] == "details" and n["attrs"].get("class") == "eda-gallery"]
        self.assertEqual(len(details), 3)
        self.assertEqual(sum("open" in n["attrs"] for n in details), 1)
        images = [n for n in page.nodes if n["tag"] == "img"]
        self.assertEqual(images[0]["attrs"]["src"], "img/example_1.jpg")
        self.assertIn("&lt;bolt&gt;", rendered)
        self.assertIn("No image examples", gallery([]))

    def test_overview_is_visible_and_audit_is_folded_for_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            runs = output / "runs"
            runs.mkdir()
            data = analyze(runs)
            write_exports(data, output / "data")
            with patch("eda.HERE", output):
                rendered = section()
        page = PageStructure(rendered)
        for id in ("eda", "eda-next", "eda-coverage", "eda-gallery"):
            self.assertFalse(page.disclosures(page.by_id(id)), id)
        self.assertTrue(page.disclosures(page.by_id("eda-ledger")))
        for id in ("eda-inventory", "eda-integrity", "eda-quality", "eda-performance", "eda-tape", "eda-duplicates", "eda-background", "eda-priorities", "eda-method"):
            self.assertEqual(page.by_id(id)["tag"], "details")
            self.assertNotIn("open", page.by_id(id)["attrs"])
        self.assertLess(rendered.index('id="eda-gallery"'), rendered.index('id="eda-inventory"'))
        self.assertIn("No image examples", rendered)

    def test_missing_snapshot_still_renders_project_reference(self):
        with tempfile.TemporaryDirectory() as root, patch("eda.HERE", Path(root)):
            rendered = project_html()
        self.assertIn("to generate the snapshot", rendered)
        self.assertIn('id="cases"', rendered)
        self.assertIn('id="progress"', rendered)


if __name__ == "__main__":
    unittest.main()
