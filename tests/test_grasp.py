"""Grasp outcomes and retry strategy, checked against finger positions seen on the station.

    python tests/test_grasp.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grasp import EMPTY, GOOD, SLIPPED, WRONG, Strategy, classify, first_strategy, next_strategy  # noqa: E402

G = {"empty_below_pos": 30, "slip_pos": 40, "min_table_clearance_mm": 2, "clearance_floor_mm": 1.0,
     "finger_speed": 2000, "finger_speed_slow": 600, "rescan_after": 3}


def test_classify_station_cases():
    # 13:01:10: an 85 mm bolt clamped end to end, fingers at 795 -> 791
    assert classify(795, 791, 10, G)[0] == WRONG
    # 12:51:57: fingers jammed on the table at 438, shut to -5 once lifted
    assert classify(438, -5, 13, G)[0] == EMPTY
    # 13:00:04: came down on top of the bolt at 717, kept closing to 83 during the lift
    assert classify(717, 83, 10, G)[0] == SLIPPED
    # Ali's checkpoint test: a 16.8 mm socket screw head held at 168
    assert classify(170, 168, 16, G)[0] == GOOD
    # thin stainless screw, 4 mm: ~40 is a good grip, not empty
    assert classify(42, 41, 4, G)[0] == GOOD
    # no width measured: anything not empty and not slipping is good
    assert classify(300, 298, None, G)[0] == GOOD
    assert classify(None, None, 10, G)[0] == GOOD  # dry run


def test_strategy_escalation():
    s = first_strategy(G)
    assert s == Strategy(0.0, 2, 2000, False)
    s = next_strategy(s, WRONG, 1, G)
    assert s.extra_deg == 90 and s.clearance_mm == 2 and not s.rescan
    s = next_strategy(s, EMPTY, 2, G)
    assert s.extra_deg == 90 and s.clearance_mm == 1 and s.speed == 600 and not s.rescan
    s = next_strategy(s, SLIPPED, 3, G)
    assert s.clearance_mm == 1.0 and s.rescan       # never below the floor; rescan after 3 failures
    s = next_strategy(s, EMPTY, 4, G)
    assert s.clearance_mm == 1.0 and not s.rescan
    assert next_strategy(Strategy(90, 2, 2000), WRONG, 1, G).extra_deg == 0  # 90 + 90 wraps to 0


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok    {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failed else 0)
