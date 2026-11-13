"""What a grasp did, and what to change on the next try. Pure functions, no robot: tested offline in
tests/test_grasp.py.

The G2's finger position is the opening in 0.1 mm (840 open, ~0 shut on nothing; a 16.8 mm screw
head read 168). It is read after the close and again after a short lift, and compared with the
part's width as the color look measured it (the blob's extent across its long axis):

    good     stopped near the expected width and stayed there through the lift
    empty    ~0 after the lift: the part was pushed away, or the jaws were aimed off it
    wrong    stopped far wider than the part: clamped end to end (791 on a 10 mm bolt), on top of
             it, or on the table
    slipped  kept closing during the lift: the jaws had it by an edge or a corner

Each outcome changes what most likely caused it (see next_strategy), and after a few failures the
arm goes back to the survey pose to find the part again, in case it was knocked far away.
"""

from dataclasses import dataclass, replace

GOOD, EMPTY, WRONG, SLIPPED = "good", "empty", "wrong", "slipped"


def expected_pos(width_mm: float) -> float:
    return 10 * width_mm


def classify(pos_closed, pos_lifted, width_mm, g: dict) -> tuple:
    """(outcome, why) from the finger positions after closing and after the short lift."""
    if pos_closed is None or pos_lifted is None:
        return GOOD, "dry run"
    if pos_lifted < g["empty_below_pos"]:
        return EMPTY, f"fingers at {pos_lifted:.0f} after the lift: nothing held"
    if pos_closed - pos_lifted > g["slip_pos"]:
        return SLIPPED, f"closed to {pos_closed:.0f}, then {pos_lifted:.0f} after the lift"
    if width_mm:
        exp = expected_pos(width_mm)
        if pos_lifted > exp + 40 + 0.3 * exp:  # blob edges and screw heads read a bit wider
            return WRONG, f"stopped at {pos_lifted:.0f}, expected ~{exp:.0f} for a {width_mm:.1f} mm part"
        return GOOD, f"holding at {pos_lifted:.0f} (expected ~{exp:.0f})"
    return GOOD, f"holding at {pos_lifted:.0f}"


@dataclass(frozen=True)
class Strategy:
    extra_deg: float = 0.0      # jaw turn away from "across the long axis"
    clearance_mm: float = 2.0   # closed fingertips above the table at the end of the close
    speed: int = 2000           # finger closing speed (G2: 1-5000)
    rescan: bool = False        # go back to the survey pose and find the part again first


def first_strategy(g: dict) -> Strategy:
    return Strategy(0.0, g["min_table_clearance_mm"], g["finger_speed"], False)


def next_strategy(s: Strategy, outcome: str, attempt: int, g: dict) -> Strategy:
    """The strategy for attempt + 1 after `outcome` on `attempt`."""
    lower = max(g["clearance_floor_mm"], s.clearance_mm - 1.0)
    if outcome == WRONG:
        # clamped across the wrong way or on top: turn the jaws, keep the height
        s = replace(s, extra_deg=(s.extra_deg + 90) % 180)
    elif outcome in (EMPTY, SLIPPED):
        # pushed away, or only an edge: go a little lower and close slower so it isn't flicked off
        s = replace(s, clearance_mm=lower, speed=g["finger_speed_slow"])
    return replace(s, rescan=attempt % g["rescan_after"] == 0)
