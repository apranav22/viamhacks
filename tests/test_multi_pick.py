"""ops/multi/sort.py selection logic (no robot, no live sort.py)."""
import importlib.util
import sys
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("multi_sort", Path(__file__).resolve().parents[1] / "ops/multi/sort.py")
M = importlib.util.module_from_spec(spec)
argv, sys.argv = sys.argv, ["sort.py"]
spec.loader.exec_module(M)
sys.argv = argv


def it(x, y, px=500, yaw=0.0):
    return (x, y, px, yaw, (0, 0, 1, 1))


class Choose(unittest.TestCase):
    def test_largest_clear_part_wins_over_larger_crowded_pair(self):
        a, b, lone = it(300, 0, 900), it(330, 0, 800), it(300, 150, 400)
        out, pick = M.choose([a, b, lone], [], None)
        self.assertEqual(pick, lone)
        self.assertEqual(out, [lone])

    def test_largest_among_clear_parts(self):
        small, big = it(300, 0, 300), it(300, 200, 700)
        self.assertEqual(M.choose([small, big], [], None)[1], big)

    def test_all_crowded_takes_most_isolated(self):
        a, b, c = it(0, 0), it(20, 0), it(60, 0)
        self.assertEqual(M.choose([a, b, c], [], None)[1], c)

    def test_choice_sticks_while_part_stays(self):
        small, big = it(300, 0, 300), it(300, 200, 700)
        self.assertEqual(M.choose([small, big], [], (302, 1))[1], small)

    def test_ignored_parts_kept_so_zone_not_empty(self):
        left = it(300, 0)
        out, pick = M.choose([left], [(301, 0)], None)
        self.assertIsNone(pick)
        self.assertEqual(out, [left])
        lone = it(300, 200)
        out, pick = M.choose([left, lone], [(301, 0)], None)
        self.assertEqual((out, pick), ([lone, left], lone))


class OwnPart(unittest.TestCase):
    def test_head_fragment_on_axis_merged_neighbour_dropped(self):
        shank = (300, 0, 800, 0.0, (0, 0, 1, 1), ((285, 0), (315, 0)))
        head = (325, 2, 200, 0.0, (0, 0, 1, 1), ((322, 2), (328, 2)))      # on the axis
        neighbour = (300, 40, 600, 0.0, (0, 0, 1, 1), ((290, 40), (310, 40)))  # beside it
        out = M.own_part([shank, head, neighbour], (301, 0))
        self.assertIn(shank, out)
        self.assertIn(head, out)
        self.assertNotIn(neighbour, out)

    def test_rotated_axis(self):
        shank = (0, 0, 800, 90.0, (0, 0, 1, 1), ((0, -15), (0, 15)))
        head = (1, 25, 200, 90.0, (0, 0, 1, 1), ((1, 22), (1, 28)))
        side = (30, 0, 600, 90.0, (0, 0, 1, 1), ((30, -10), (30, 10)))
        out = M.own_part([shank, head, side], (0, 0))
        self.assertEqual(out, [shank, head])


if __name__ == "__main__":
    unittest.main()
