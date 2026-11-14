"""Offline (no robot): sort.py's still-frame gate, the overlapped view scoring, straight moves and the arrival check,
on a Sorter with fake arm / cameras. python3 -m unittest tests/test_sort_offline.py"""

import asyncio
import io
import math
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
    """pick() on a squat blob that the depth look reads as standing: halfway rule first; if that descent hits the
    part (fault), clear, back up, re-check it stands and descend once more at the sensor-safe height."""

    def pick(self, heights, hits=(), part_type="auto", views="classic"):
        s = sorter(FakeArm([0] * 6))
        s.args.type, s.args.assume_lying, s.args.views = part_type, False, views
        s.ignore_xy, s.state, s.rewatch = [], lambda *a, **k: None, False
        moves, straights = [], []
        item = (300.0, 300.0, 500, 0.0, (100, 100, 130, 130))
        heights = iter(heights)

        async def jmove(q, label, holding):
            moves.append(label); s.q = list(q)
            return 0.0

        async def look(it, attempt, heading):
            return it, 0.0

        async def depth(xy):
            return next(heights), np.array(xy)

        async def straight(x, y, z, label, holding):
            straights.append((label, round(z - sort.G["tcp_to_tip_mm"] - sort.TZ, 1)))   # closed-tip height
            if label in hits:
                raise sort.ArmFault(f"{label}: arm ended 3.0 deg from its target")

        async def grab():
            return 300.0

        async def lay_flat(it):
            straights.append(("lay flat", None)); s.laid_flat = True

        async def obliques(it, look_q):
            straights.append(("obliques", None))

        s.jmove, s.look, s.depth_look, s.straight, s.lay_flat = jmove, look, depth, straight, lay_flat
        s.oblique_looks = obliques
        s.look_joints = lambda it: sort.WATCH_J
        s.mv = SimpleNamespace(finger_pos=lambda: _const(800.0), grab=grab)
        with unittest.mock.patch.object(sort, "round_part", lambda it: True), \
                unittest.mock.patch.object(sort, "sound", lambda *a: None):
            ok, _, _ = asyncio.run(s.pick(item))
        return s, ok, moves, straights

    def high_tips(self, h=0.0):
        return round(max(h, sort.longest_part_mm("auto")) - (sort.G["tip_to_sensor_mm"] - 8.0), 1)

    def test_low_first_and_nothing_hit_then_laid_flat(self):
        s, ok, moves, straights = self.pick([21.0])
        self.assertFalse(ok)                                     # not inspected upright: laid flat, picked lying next
        self.assertEqual(straights, [("descend 1", 10.5), ("lift 1", straights[1][1]), ("lay flat", None)])
        self.assertNotIn(("do", {"clear_error": True}), s.arm.calls)

    def test_hit_on_the_way_down_retries_higher_once(self):
        s, ok, moves, straights = self.pick([21.0, 21.0], hits={"descend 1"})
        self.assertFalse(ok)
        self.assertEqual([lbl for lbl, _ in straights], ["descend 1", "back up 1", "descend 1.high", "lift 1", "lay flat"])
        self.assertEqual(straights[2][1], self.high_tips())
        self.assertIn(("do", {"clear_error": True}), s.arm.calls)
        self.assertIn("aim upright 1.high", moves)

    def test_second_hit_ends_the_run(self):
        with self.assertRaises(sort.ArmFault):
            self.pick([21.0, 21.0], hits={"descend 1", "descend 1.high"})

    def test_knocked_over_by_the_hit_goes_back_to_watch(self):
        s, ok, moves, straights = self.pick([21.0, 4.0], hits={"descend 1"})
        self.assertFalse(ok)
        self.assertTrue(s.rewatch)
        self.assertEqual([lbl for lbl, _ in straights], ["descend 1", "back up 1"])

    def test_coverage_standing_part_skips_the_oblique_looks(self):
        s, ok, moves, straights = self.pick([74.0], views="coverage")          # 12:13 bolt: oblique boxes assume lying
        self.assertNotIn(("obliques", None), straights)
        self.assertEqual(straights[-1], ("lay flat", None))

    def test_coverage_squat_lying_part_gets_them_after_the_depth_look(self):
        s, ok, moves, straights = self.pick([5.0], views="coverage")           # a flat nut
        self.assertTrue(ok)
        self.assertEqual([lbl for lbl, _ in straights], ["obliques", "descend 1", "lift 1"])
        self.assertEqual(moves[-2:], ["look (for obliques)", "hover 1"])

    def test_no_retry_when_low_was_already_safe(self):
        with self.assertRaises(sort.ArmFault):                   # 80 mm read: halfway keeps it clear; a fault is real
            self.pick([80.0], hits={"descend 1"})


class SquatFromTheCloseUp(unittest.TestCase):
    """detect(ends=True) also returns the blob's extent across its axis; length / width tells squat from long."""

    def ratio(self, w, h, angle=0):
        img = Image.new("RGB", (640, 480), (150, 110, 70))
        blob = Image.new("L", (w, h), 255).rotate(angle, expand=True)
        img.paste((220, 220, 225), (320 - blob.width // 2, 240 - blob.height // 2), blob)
        it = max(sort.detect(np.asarray(img), None, None, ends=True), key=lambda b: b[2])
        L = math.dist(*it[5]); W = math.dist(*it[6])
        return L / W

    def test_long_part_even_diagonal(self):
        self.assertGreater(self.ratio(80, 16), sort.SQUAT_RATIO)
        self.assertGreater(self.ratio(80, 16, angle=45), sort.SQUAT_RATIO)   # round_part's fill test was ~0.3 here

    def test_head_on_view_is_squat(self):
        self.assertLess(self.ratio(30, 24), sort.SQUAT_RATIO)


class LayFlat(unittest.TestCase):
    """lay_flat(): a tilted pose over the spot, slow descent, slow small opening, retreat along the tool axis."""

    def test_gentle_lay_down(self):
        held_q = ik(np.array([275.0, 350.0, sort.LIFT_Z]), seed=sort.VIEW_J["front"], jaw_heading_deg=90)[0]
        arm = FakeArm(held_q)
        s = sorter(arm)
        s.upright, s.state, s.grasp_z_upright = 23.0, lambda *a, **k: None, 50.0
        gcalls = []

        class Grip:
            async def do_command(self, cmd):
                gcalls.append(cmd)
                return {"gripper_speed": 2000} if "get_gripper_speed" in cmd else {}

        s.gripper = Grip()
        s.mv = SimpleNamespace(finger_pos=lambda: _const(300.0))
        straights = []
        real_straight = s.straight

        async def straight(x, y, z, label, holding, tcp_limit=None):
            straights.append((label, tcp_limit))
            await real_straight(x, y, z, label, holding, tcp_limit)

        s.straight = straight
        asyncio.run(s.lay_flat((275.0, 350.0, 0, 0.0, None)))
        self.assertTrue(s.laid_flat and s.rewatch)
        self.assertEqual([lbl for lbl, _ in straights], ["lay down", "lay retreat"])
        self.assertTrue(all(lim == sort.LAY_TCP_MM_S for _, lim in straights))
        self.assertEqual(gcalls, [{"get_gripper_speed": True}, {"set_gripper_speed": sort.LAY_OPEN_SPEED},
                                  {"set": 300.0 + sort.LAY_OPEN_BY}, {"set_gripper_speed": 2000}])
        p, z = sort.fk_tcp(arm.calls[[c[0] for c in arm.calls].index("through")][1][-1])     # end of the lay-down chain
        self.assertAlmostEqual(float(np.degrees(np.arccos(-z[2]))), sort.LAY_TILT_DEG, delta=1.0)
        end = p + z * (sort.G["tcp_to_tip_mm"] + 23.0)
        self.assertAlmostEqual(float(end[2]), sort.TZ + sort.LAY_CLEAR_MM[0], delta=1.0)  # low end just over the pad


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
