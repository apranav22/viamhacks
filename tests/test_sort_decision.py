"""Demo decision rule in sort.py (offline, no robot): python -m unittest tests.test_sort_decision

The first capture that is not clean decides reject and no further captures are taken; good only when every capture
with a model came back clean; views nobody trained are evidence only.
"""
import asyncio
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sort as loop
from vh.anomaly import Score
from vh.telemetry import Telemetry

MODELED = {"top", "front", "yaw-20", "yaw+35", "pitch-25"}


class FakeModels:
    """Stands in for AnomalyModels: score per view from a dict (default clean)."""
    def __init__(self, scores, modeled=MODELED):
        self.scores, self.modeled, self.resets = scores, modeled, 0

    def crop(self, image, bbox, view, mm_per_px=None):
        return Image.new("RGB", (8, 8)), bbox

    def score(self, crop, part_type, pose, view, background):
        return self.scores.get(view, Score("ok", 1.0, 2.0) if view in self.modeled else Score("missing"))

    def modeled_views(self, pose, background):
        return set(self.modeled)

    def reset_item(self):
        self.resets += 1


def sorter(td, scores, modeled=MODELED, blocked=(), mode="sort", decide="all"):
    s = loop.Sorter.__new__(loop.Sorter)
    s.args = SimpleNamespace(mode=mode, type="auto", background="cardboard", label="good", decide=decide)
    s.upright, s.pose, s.n, s.top_tape, s.meta, s.idir = 0, "lying", 1, 0.0, {}, Path(td)
    s.anomaly = FakeModels(scores, modeled)
    s.tel = Telemetry(enabled=False)
    s.state = lambda *a, **kw: None
    s.oblique_scores, s.early = {}, None
    s.top_rec = s.top_reject = s._top_scored = None
    b = io.BytesIO()
    Image.new("RGB", (1920, 1080), "white").save(b, format="JPEG")
    s.top_image, s.top_bbox = b.getvalue(), [100, 100, 200, 200]
    s.captured, s.moves = [], []

    async def web():
        return s.top_image

    async def jaw():
        return 100

    async def move(q, label, holding=False, **kw):
        if any(label.startswith(f"view {v}") for v in blocked):
            raise loop.PathBlocked("blocked path")
        s.moves.append(label)

    orig_infer = s.infer_crop

    async def infer(image, bbox, view, pose=None):
        if view != "top":
            s.captured.append(view)
        return await orig_infer(image, bbox, view, pose)

    s.web_jpeg, s.jmove, s.infer_crop, s.mv = web, move, infer, SimpleNamespace(finger_pos=jaw)
    return s


class DemoDecisionTests(unittest.TestCase):
    def run_inspect(self, scores, **kw):
        with tempfile.TemporaryDirectory() as td:
            s = sorter(td, scores, **kw)
            out = asyncio.run(s.inspect())
            return s, out

    def test_all_clean_goes_good_after_every_view(self):
        s, (decision, reason, at, _) = self.run_inspect({})
        self.assertEqual(decision, "good")
        self.assertEqual(s.captured, loop.VIEW_ORDER)
        self.assertIn("5 modeled captures clean", reason)

    def test_top_defect_goes_straight_to_reject_without_webcam_captures(self):
        s, (decision, reason, at, _) = self.run_inspect({"top": Score("ok", 3.0, 2.0)})
        self.assertEqual((decision, at), ("reject", "top"))
        self.assertIn("anomaly: top", reason)
        self.assertEqual(s.captured, [])                       # no webcam capture
        self.assertEqual(s.moves, [f"view {loop.VIEW_ORDER[0]}"])   # only to the checkpoint over reject

    def test_failed_top_score_is_uncertain_reject_without_captures(self):
        s, (decision, reason, at, _) = self.run_inspect({"top": Score("unknown_type", detail="no match")})
        self.assertEqual(decision, "reject")
        self.assertIn("uncertain", reason)
        self.assertEqual(s.captured, [])

    def test_webcam_defect_stops_further_captures(self):
        second = loop.VIEW_ORDER[1]
        s, (decision, reason, at, _) = self.run_inspect({second: Score("ok", 2.5, 2.0)})
        self.assertEqual((decision, at), ("reject", second))
        self.assertEqual(s.captured, loop.VIEW_ORDER[:2])

    def test_unscored_modeled_view_is_not_clean(self):
        s, (decision, reason, at, _) = self.run_inspect({loop.VIEW_ORDER[0]: Score("error", detail="boom")})
        self.assertEqual(decision, "reject")
        self.assertIn("uncertain", reason)
        self.assertEqual(len(s.captured), 1)

    def test_blocked_modeled_view_is_not_clean(self):
        blocked = loop.VIEW_ORDER[2]
        s, (decision, reason, _, _) = self.run_inspect({}, blocked=(blocked,))
        self.assertEqual(decision, "reject")
        self.assertIn(f"{blocked} not captured", reason)

    def test_untrained_view_is_evidence_only(self):
        modeled = MODELED - {loop.VIEW_ORDER[3]}
        s, (decision, _, _, scores) = self.run_inspect({}, modeled=modeled)
        self.assertEqual(decision, "good")
        self.assertEqual(scores[loop.VIEW_ORDER[3]]["status"], "missing")

    def test_decide_top_ignores_webcam_anomaly(self):
        s, (decision, _, _, _) = self.run_inspect({loop.VIEW_ORDER[0]: Score("ok", 9.0, 2.0)}, decide="top")
        self.assertEqual(decision, "good")

    def test_oblique_defect_found_before_grasp_skips_webcam(self):
        with tempfile.TemporaryDirectory() as td:
            s = sorter(td, {})
            s.early = ("oblique+45", "anomaly: oblique+45 score 3.000 >= 2.000")
            decision, reason, at, _ = asyncio.run(s.inspect())
        self.assertEqual((decision, at), ("reject", "oblique+45"))
        self.assertEqual(s.captured, [])

    def test_top_scored_once_per_look_and_resets_type(self):
        with tempfile.TemporaryDirectory() as td:
            s = sorter(td, {})
            asyncio.run(s.score_top("lying"))
            asyncio.run(s.inspect())
            self.assertEqual(s.anomaly.resets, 1)              # cached: inspect() didn't re-score the same look

    def test_collect_mode_still_captures_everything(self):
        s, (decision, _, _, _) = self.run_inspect({"top": Score("ok", 3.0, 2.0)}, mode="collect")
        self.assertEqual(decision, "collect")
        self.assertEqual(s.captured, loop.VIEW_ORDER)


class ArrivedTests(unittest.TestCase):
    """jmove reads the joints back: a move that ended short (controller fault the module cleared) stops the arm."""

    def make(self, got):
        calls = []

        class Arm:
            async def get_joint_positions(self):
                return SimpleNamespace(values=got)

            async def do_command(self, cmd):
                return {"error": "C60"}

            async def stop(self):
                calls.append("stop")

        s = loop.Sorter.__new__(loop.Sorter)
        s.arm, s.tel, s.q = Arm(), SimpleNamespace(emit=lambda *a, **k: None), None
        return s, calls

    def test_reached(self):
        s, calls = self.make([0.0, 10.0, 20.0, 0.0, 0.0, 0.0])
        asyncio.run(s.arrived([0.0, 10.4, 20.0, 0.0, 0.0, 0.0], "x"))
        self.assertEqual(calls, [])

    def test_short_stops_and_raises(self):
        s, calls = self.make([0.0, 10.0, 20.0, 0.0, 0.0, 0.0])
        with self.assertRaises(loop.ArmFault):
            asyncio.run(s.arrived([0.0, 15.0, 20.0, 0.0, 0.0, 0.0], "x"))
        self.assertEqual(calls, ["stop"])
        self.assertNotIsInstance(loop.ArmFault("x"), loop.PathBlocked)   # never swallowed as "skip this view"



if __name__ == "__main__":
    unittest.main()
