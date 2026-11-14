"""Offline (no robot): sort.py's still-frame gate, the overlapped view scoring, straight moves and the arrival check,
on a Sorter with fake arm / cameras. python3 -m unittest tests/test_sort_offline.py"""

import asyncio
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sort  # noqa: E402
from vh.anomaly import Score  # noqa: E402
from vh.kinematics import ik  # noqa: E402
from vh.telemetry import Telemetry  # noqa: E402


def jpeg(shift=0, size=(640, 360)):
    rgb = np.zeros((size[1], size[0], 3), np.uint8)
    for x in range(0, size[0], 40):                       # stripes: a shift changes many pixels
        rgb[:, (x + shift) % size[0]:(x + shift) % size[0] + 20] = 200
    buf = io.BytesIO(); Image.fromarray(rgb).save(buf, "JPEG", quality=90)
    return buf.getvalue()


class FakeArm:
    def __init__(self, q, reach=True):
        self.q, self.reach, self.calls, self.stopped = list(q), reach, [], False

    async def get_joint_positions(self):
        return SimpleNamespace(values=self.q)

    async def move_to_joint_positions(self, jp):
        self.calls.append(("move", list(jp.values)))
        if self.reach:
            self.q = list(jp.values)

    async def move_through_joint_positions(self, jps):
        self.calls.append(("through", [list(j.values) for j in jps]))
        if self.reach:
            self.q = list(jps[-1].values)

    async def do_command(self, cmd):
        self.calls.append(("do", cmd))
        return {"error info": "C60"} if "get_error" in cmd else {}

    async def stop(self):
        self.stopped = True


def sorter(arm, mode="collect"):
    s = object.__new__(sort.Sorter)
    s.args = SimpleNamespace(mode=mode, tcp_limit=900.0, tcp_limit_holding=800.0, run_accel=600.0, decide="all",
                             type="unknown", background="cardboard", label="good")
    s.arm, s.q, s.n = arm, None, 1
    s.obs = sort.load_obstacles(table_z=sort.TZ)
    s.tel = Telemetry(enabled=False)
    s.meta, s.upright, s.pose = {}, 0.0, "lying"
    s.top_image = s.top_bbox = s.top_tape = None
    s.anomaly = None
    s.mv = SimpleNamespace(finger_pos=lambda: _const(500.0))
    return s


async def _const(v):
    return v


class StillFrame(unittest.TestCase):
    def test_waits_for_two_matching_frames(self):
        frames = iter([jpeg(0), jpeg(0), jpeg(9), jpeg(17), jpeg(17), jpeg(30)])   # stale repeat, ringing, still
        s = sorter(FakeArm([0] * 6))
        got = asyncio.run(s.still_frame(lambda: _const(next(frames)), "t"))
        self.assertEqual(got, jpeg(17))

    def test_gives_up_after_the_limit(self):
        frames = iter([jpeg(i * 7) for i in range(10)])
        s = sorter(FakeArm([0] * 6))
        got = asyncio.run(s.still_frame(lambda: _const(next(frames)), "t"))
        self.assertEqual(got, jpeg(4 * 7))                                     # the fifth frame


class Inspect(unittest.TestCase):
    def run_inspect(self, s, scores_by_view=None):
        moves = []

        async def jmove(q, label, holding):
            moves.append(label)
            await asyncio.sleep(0.01)

        async def web():
            return jpeg(0, (1920, 1080))

        async def infer(image, bbox, view):
            await asyncio.sleep(0.02)
            if view == "top":
                return Score("missing", detail="no model"), bbox
            return (scores_by_view or {}).get(view, Score("missing", detail="no model")), bbox

        s.jmove, s.web_jpeg, s.infer_crop = jmove, web, infer
        s.emit_anomaly = lambda *a: None
        with tempfile.TemporaryDirectory() as d:
            s.idir = Path(d)
            out = asyncio.run(s.inspect())
        return out, moves

    def test_collect_visits_every_view_and_scores_all(self):
        (decision, _, _, scores), moves = self.run_inspect(sorter(FakeArm([0] * 6)))
        self.assertEqual(decision, "collect")
        self.assertEqual(moves, [f"view {v}" for v in sort.VIEW_ORDER])
        for v in sort.VIEW_ORDER:
            self.assertEqual(scores[v]["status"], "missing")                  # the overlapped score was merged in

    def test_top_decision_still_captures_one_checkpoint_view(self):
        s = sorter(FakeArm([0] * 6), mode="sort")
        s.top_tape = 0.5                                                      # known tape on the top face
        (decision, reason, at, scores), moves = self.run_inspect(s)
        self.assertEqual((decision, at), ("reject", "top"))
        self.assertEqual(moves, ["view front"])
        self.assertIn("front", scores)

    def test_anomaly_reject_lands_one_view_later_without_a_capture(self):
        bad = Score("ok", score=9.0, threshold=1.0)
        s = sorter(FakeArm([0] * 6), mode="sort")
        (decision, reason, at, scores), moves = self.run_inspect(s, {"front": bad})
        self.assertEqual((decision, at), ("reject", "front"))
        self.assertEqual(moves, ["view front", "view yaw-20"])
        self.assertNotIn("yaw-20", scores)


class Moves(unittest.TestCase):
    hover = ik(np.array([249.8, 324.7, 128.7]), seed=sort.VIEW_J["front"], jaw_heading_deg=259)[0]

    def test_straight_is_one_waypoint_chain_under_the_limit(self):
        arm = FakeArm(self.hover)
        s = sorter(arm)
        asyncio.run(s.straight(249.8, 324.7, 21.2, "descend 1", holding=False))
        kinds = [c[0] for c in arm.calls]
        self.assertEqual(kinds.count("through"), 1)
        self.assertNotIn("move", kinds)
        speed = next(c[1]["set_speed"] for c in arm.calls if c[0] == "do" and "set_speed" in c[1])
        self.assertLessEqual(speed, 180)

    def test_arm_short_of_target_stops_the_run(self):
        arm = FakeArm(self.hover, reach=False)
        s = sorter(arm)
        with self.assertRaises(sort.ArmFault):
            asyncio.run(s.straight(249.8, 324.7, 21.2, "descend 1", holding=False))
        self.assertTrue(arm.stopped)


if __name__ == "__main__":
    unittest.main()
