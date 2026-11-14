"""Offline (no robot): tool-speed limits, straight-line waypoints and the upright grasp guard.
python3 -m unittest tests/test_speed_limits.py"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vh.config import CHECKPOINT as CP, POSES  # noqa: E402
from vh.kinematics import (flip, ik, line_joints, peak_chain_tcp_speed, peak_tcp_speed, safe_chain_speed,  # noqa: E402
                           safe_joint_speed, tcp, tcp_speed_profile)
from vh.motion import PROBE_TOL_MM, SENSOR_MARGIN_MM, upright_tips  # noqa: E402

G = POSES["grasp"]
FRONT = flip(CP["views"]["front"]["joints_deg"])
PICK = (249.8, 324.7)                     # item 1 of runs/20261114_110157_collect
C60_MM_S = 1200.0                         # ServoJ TCP limit: 1.2 x 1000 mm/s (UFACTORY, xArm and UF850)


def lift_joints():
    return ik(np.array([*PICK, 280.0]), seed=FRONT, jaw_heading_deg=259)[0]


class SpeedLimits(unittest.TestCase):
    def test_chain_of_one_leg_is_the_joint_move(self):
        a, b = lift_joints(), FRONT
        for limit, acc in ((900, 600), (800, 900)):
            self.assertEqual(safe_chain_speed([a, b], limit, acc, n=60), safe_joint_speed(a, b, limit, acc))
            d, k = tcp_speed_profile(a, b)
            self.assertAlmostEqual(peak_chain_tcp_speed([a, b], 100, acc, n=60), peak_tcp_speed(d, k, 100, acc), places=6)

    def test_full_speed_swing_trips_c60_and_the_limit_does_not(self):
        # 10:48 on 2026-11-14: 180 deg/s + 1145 deg/s^2 for every move -> C60 (machine logs)
        a, b = lift_joints(), FRONT
        d, k = tcp_speed_profile(a, b)
        self.assertGreater(peak_tcp_speed(d, k, 180, 1145), C60_MM_S)
        for limit, acc in ((900, 600), (800, 600), (900, 900), (800, 1145)):
            v = safe_joint_speed(a, b, limit, acc)
            self.assertLessEqual(peak_tcp_speed(d, k, v, acc), limit)
            if v < 180:
                self.assertGreater(peak_tcp_speed(d, k, v + 2, acc), limit)   # and it is the fastest such speed

    def test_straight_descend_and_lift_stay_on_the_line(self):
        hover = ik(np.array([*PICK, 128.7]), seed=FRONT, jaw_heading_deg=259)[0]
        grasp = (*PICK, 21.2)
        qs, dev = line_joints(hover, grasp)
        self.assertLessEqual(dev, 2.0)
        z = [tcp(q)[0][2] for q in [hover] + qs]
        self.assertTrue(all(b < a for a, b in zip(z, z[1:])), z)              # only ever down: never under the target
        self.assertLess(np.linalg.norm(tcp(qs[-1])[0] - grasp), 0.5)
        up, dev = line_joints(qs[-1], (*PICK, 280.0))
        self.assertLessEqual(dev, 2.0)
        for limit in (900, 800):
            v = safe_chain_speed([qs[-1]] + up, limit, 600)
            self.assertLessEqual(peak_chain_tcp_speed([qs[-1]] + up, v, 600), limit)

    def test_line_refuses_an_unreachable_target(self):
        with self.assertRaises(ValueError):
            line_joints(FRONT, (2000.0, 0.0, 200.0))


class UprightGuard(unittest.TestCase):
    g = {**G, "tip_to_sensor_mm": 70.0}

    def test_unmeasured_gap_refuses(self):
        tips, probe, why = upright_tips(60, {k: v for k, v in G.items() if k != "tip_to_sensor_mm"}, 77)
        self.assertIsNone(tips)
        self.assertIn("not measured", why)

    def test_true_height_keeps_the_halfway_rule(self):
        tips, probe, why = upright_tips(77, self.g, 77)       # the longest part, read right: half stands above the tips
        self.assertEqual((tips, probe, why), (38.5, False, None))
        self.assertLessEqual(77 - tips, 70 - SENSOR_MARGIN_MM)

    def test_under_read_probes_high_first_then_steps_down(self):
        # 15:48: one bolt read 20-22 mm and 80 mm. Measured gap 61.8 (config/poses.json), longest part ~76.9 mm.
        import sort
        L = sort.longest_part_mm("auto")
        tips, probe, why = upright_tips(21, G, L)
        self.assertTrue(probe)
        self.assertLessEqual(L - tips, G["tip_to_sensor_mm"] - SENSOR_MARGIN_MM + 1e-9)   # even 77 mm stays clear
        low, probe2, why2 = upright_tips(21, G, L, top_below=tips + PROBE_TOL_MM)          # closed on nothing up there
        self.assertEqual((low, probe2, why2), (10.5, False, None))                          # now the halfway rule
        self.assertLess(low, tips)

    def test_steps_only_go_down(self):
        tips, top = None, None
        for _ in range(4):                                      # a miss at every height
            t, probe, _ = upright_tips(70, {**G, "tip_to_sensor_mm": 30.0}, 77, top)
            if tips is not None:
                self.assertLess(t, tips)
            tips, top = t, t + PROBE_TOL_MM
            if not probe:
                break
        self.assertFalse(probe)

    def test_too_short_to_hold_is_left(self):
        tips, probe, why = upright_tips(11, self.g, 11)
        self.assertIsNone(tips)
        self.assertIn("too short", why)


if __name__ == "__main__":
    unittest.main()
