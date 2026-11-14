"""Offline (no robot): sort.py's still-frame gate, the overlapped view scoring, straight moves and the arrival check,
on a Sorter with fake arm / cameras. python3 -m unittest tests/test_sort_offline.py"""

import asyncio
import io
import sys
import tempfile
import unittest
import unittest.mock
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


class UprightPick(unittest.TestCase):
    """pick() on a squat blob that the depth look reads as standing: the guard decides; an ambiguous reading is
    grasped high first (safe for the longest part) and stepped down only after that grasp closed on nothing."""

    def pick(self, heights, grabs, part_type="auto"):
        s = sorter(FakeArm([0] * 6))
        s.args.type, s.args.assume_lying, s.args.views = part_type, False, "classic"
        s.ignore_xy, s.state, s.rewatch = [], lambda *a, **k: None, False
        moves, straights = [], []
        item = (300.0, 300.0, 500, 0.0, (100, 100, 130, 130))
        heights, grabs = iter(heights), iter(grabs)

        async def jmove(q, label, holding):
            moves.append(label); s.q = list(q)
            return 0.0

        async def look(it, attempt, heading):
            return it, 0.0

        async def depth(xy):
            return next(heights), np.array(xy)

        async def straight(x, y, z, label, holding):
            straights.append((label, round(z - sort.G["tcp_to_tip_mm"] - sort.TZ, 1)))   # closed-tip height

        async def grab():
            return next(grabs)

        async def release():
            return 800.0

        s.jmove, s.look, s.depth_look, s.straight, s.release = jmove, look, depth, straight, release
        s.look_joints = lambda it: sort.WATCH_J
        s.mv = SimpleNamespace(finger_pos=lambda: _const(800.0), grab=grab)
        with unittest.mock.patch.object(sort, "round_part", lambda it: True), \
                unittest.mock.patch.object(sort, "sound", lambda *a: None):
            ok, _, _ = asyncio.run(s.pick(item))
        return s, ok, moves, straights

    def safe_tips(self):
        return round(sort.longest_part_mm("auto") - (sort.G["tip_to_sensor_mm"] - 8.0), 1)

    def test_under_read_probes_high_then_grasps_lower(self):
        s, ok, moves, straights = self.pick([21.0, 21.0], [0.0, 300.0])     # the 15:48 bolt's reading; first grab: air
        self.assertTrue(ok)
        self.assertEqual([lbl for lbl, _ in straights], ["descend 1", "probe up 1", "descend 1.1", "lift 1"])
        self.assertEqual(straights[0][1], self.safe_tips())                  # high first: safe for the longest part
        self.assertEqual(straights[2][1], 10.5)                              # then Pranav's halfway rule
        self.assertIn("aim upright 1.1", moves)

    def test_probe_that_holds_lifts_from_up_there(self):
        s, ok, moves, straights = self.pick([40.0], [300.0])
        self.assertTrue(ok)
        self.assertEqual([lbl for lbl, _ in straights], ["descend 1", "lift 1"])
        self.assertEqual(straights[0][1], self.safe_tips())

    def test_knocked_over_by_the_probe_goes_back_to_watch(self):
        s, ok, moves, straights = self.pick([21.0, 4.0], [0.0])
        self.assertFalse(ok)
        self.assertTrue(s.rewatch)
        self.assertIn("not standing", s.skip_reason)
        self.assertEqual([lbl for lbl, _ in straights], ["descend 1", "probe up 1"])

    def test_tall_reading_goes_straight_to_the_halfway_grasp(self):
        s, ok, moves, straights = self.pick([80.0], [300.0])
        self.assertTrue(ok)
        self.assertEqual(straights, [("descend 1", 40.0), ("lift 1", straights[1][1])])


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
