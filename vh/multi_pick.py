"""Multi-part pick: several parts on the pad at once, picked one at a time (sort.py --multi).

From Pranav's ops/multi/sort.py (pranav/fast-carry 42c3a13), moved from a monkey-patch wrapper into sort.py:

  choose    of all parts in the zone, go for the largest one with no other part within min_gap_mm (centre to
            centre); none clear: the most isolated one. The choice sticks while that part stays put (the watch
            stability check needs the same part frame to frame).
  own_part  the close-up look() merges blobs within NEAR_MM of the target into one part (shiny head split off its
            shank). With several parts only blobs ON the target's long axis are merged; a neighbour is dropped, so
            the grasp point and the anomaly crop belong to one part.

Not covered: the oblique looks and the jaws don't plan around neighbours (keep ~8-10 cm between parts).
Detections are tuples (x_mm, y_mm, px, yaw_deg, bbox[, ends]).
"""
import math

MIN_GAP_MM = 70.0   # default clearance for a part to count as "clear"
AXIS_MM = 8.0       # a blob this close to the target's long axis is a piece of it (head fragment), else a neighbour
NEAR_MM = 60.0      # sort.py look() radius
STICK_MM = 10.0     # previous choice still within this: keep it


def choose(items, ignore=(), prev=None, min_gap_mm=MIN_GAP_MM):
    """Watch-pose detections -> the target, or None. Parts within 25 mm of an `ignore` point (deliberately left in
    place) are never chosen but still count as neighbours for the gap."""
    live = [it for it in items if all(math.dist(it[:2], q) > 25 for q in ignore)]
    if not live:
        return None

    def gap(it):
        return min((math.dist(it[:2], o[:2]) for o in items if o is not it), default=math.inf)
    if prev is not None:
        stay = min(live, key=lambda it: math.dist(it[:2], prev))
        if math.dist(stay[:2], prev) < STICK_MM:
            return stay
    clear = [it for it in live if gap(it) >= min_gap_mm]
    return max(clear, key=lambda it: it[2]) if clear else max(live, key=gap)


def own_part(blobs, target):
    """Close-up detections with ends -> the target part's blobs within NEAR_MM: the one nearest the target plus
    blobs on its long axis (pieces of the same part)."""
    near = [b for b in blobs if math.dist(b[:2], target) < NEAR_MM]
    if not near:
        return []
    anchor = min(near, key=lambda b: math.dist(b[:2], target))
    ax, ay = math.cos(math.radians(anchor[3])), math.sin(math.radians(anchor[3]))
    return [b for b in near if b is anchor or abs((b[0] - anchor[0]) * ay - (b[1] - anchor[1]) * ax) < AXIS_MM]
