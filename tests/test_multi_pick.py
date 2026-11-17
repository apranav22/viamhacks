"""vh/multi_pick.py selection logic (sort.py --multi). From Pranav's tests/test_multi_pick.py (42c3a13)."""
import unittest

from vh import multi_pick as M


def it(x, y, px=500, yaw=0.0):
    return (x, y, px, yaw, (0, 0, 1, 1))


class Choose(unittest.TestCase):
    def test_largest_clear_part_wins_over_larger_crowded_pair(self):
        a, b, lone = it(300, 0, 900), it(330, 0, 800), it(300, 150, 400)
        self.assertEqual(M.choose([a, b, lone]), lone)

    def test_largest_among_clear_parts(self):
        small, big = it(300, 0, 300), it(300, 200, 700)
        self.assertEqual(M.choose([small, big]), big)

    def test_all_crowded_takes_most_isolated(self):
        a, b, c = it(0, 0), it(20, 0), it(60, 0)
        self.assertEqual(M.choose([a, b, c]), c)

    def test_choice_sticks_while_part_stays(self):
        small, big = it(300, 0, 300), it(300, 200, 700)
        self.assertEqual(M.choose([small, big], prev=(302, 1)), small)

    def test_ignored_parts_never_chosen_but_count_as_neighbours(self):
        left = it(300, 0)
        self.assertIsNone(M.choose([left], ignore=[(301, 0)]))
        lone = it(300, 200)
        self.assertEqual(M.choose([left, lone], ignore=[(301, 0)]), lone)
        near_left, far = it(300, 40, 900), it(300, 300, 200)     # near_left is crowded by the left part
        self.assertEqual(M.choose([left, near_left, far], ignore=[(301, 0)]), far)

    def test_empty(self):
        self.assertIsNone(M.choose([]))

    def test_min_gap(self):
        a, b = it(0, 0, 900), it(50, 0, 100)
        self.assertEqual(M.choose([a, b], min_gap_mm=40), a)


class OwnPart(unittest.TestCase):
    def test_head_fragment_on_axis_merged_neighbour_dropped(self):
        shank = (300, 0, 800, 0.0, (0, 0, 1, 1), ((285, 0), (315, 0)))
        head = (325, 2, 200, 0.0, (0, 0, 1, 1), ((322, 2), (328, 2)))          # on the axis
        neighbour = (300, 40, 600, 0.0, (0, 0, 1, 1), ((290, 40), (310, 40)))  # beside it
        self.assertEqual(M.own_part([shank, head, neighbour], (301, 0)), [shank, head])

    def test_rotated_axis(self):
        shank = (0, 0, 800, 90.0, (0, 0, 1, 1), ((0, -15), (0, 15)))
        head = (1, 25, 200, 90.0, (0, 0, 1, 1), ((1, 22), (1, 28)))
        side = (30, 0, 600, 90.0, (0, 0, 1, 1), ((30, -10), (30, 10)))
        self.assertEqual(M.own_part([shank, head, side], (0, 0)), [shank, head])

    def test_far_blobs_dropped(self):
        far = (500, 500, 800, 0.0, (0, 0, 1, 1), ((490, 500), (510, 500)))
        self.assertEqual(M.own_part([far], (0, 0)), [])


if __name__ == "__main__":
    unittest.main()
