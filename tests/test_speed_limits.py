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
from vh.motion import SENSOR_MARGIN_MM, upright_tips  # noqa: E402

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
        low, high, why = upright_tips(60, {k: v for k, v in G.items() if k != "tip_to_sensor_mm"}, 77)
        self.assertIsNone(low)
        self.assertIn("not measured", why)

    def test_low_first_is_the_halfway_rule(self):
        # 15:48: one bolt read 20-22 mm and 80 mm. Measured gap 61.8 (config/poses.json), longest part ~76.9 mm.
        import sort
        L = sort.longest_part_mm("auto")
        low, high, why = upright_tips(21, G, L)
        self.assertIsNone(why)
        self.assertEqual(low, 10.5)
        self.assertGreater(high, low)                                                    # the retry after a hit
        self.assertLessEqual(L - high, G["tip_to_sensor_mm"] - SENSOR_MARGIN_MM + 1e-9)  # keeps even 77 mm clear

    def test_no_retry_when_low_is_already_safe(self):
        low, high, why = upright_tips(77, self.g, 77)           # read right: half stands above the tips, 62 mm room
        self.assertEqual((low, high, why), (38.5, None, None))

    def test_short_parts_hold_at_least_the_minimum(self):
        low, high, why = upright_tips(16, self.g, 16)
        self.assertEqual(low, 6.0)                              # under halfway: 10 mm above the tips
        self.assertIsNone(upright_tips(11, self.g, 11)[0])      # too short to hold 10 mm of it


if __name__ == "__main__":
    unittest.main()
