"""Multi-part sort: several parts on the pad at once, picked one at a time. Runs the station's LIVE sort.py unchanged
(/opt/viam/sorter-ali/current, same flags) and patches only how a part is chosen:

  watch     of all parts in the zone, go for the largest one with no other part within --min-gap-mm (centre to
            centre); none clear: the most isolated one. The choice sticks while that part stays put (the live
            stability check needs the same part frame to frame). Parts the live loop chose to leave stay left.
  close-up  the live look() merges every blob within 60 mm of the target into one part (fix for a shiny bolt head
            splitting off its shank). Here only blobs ON the target's long axis are merged; a neighbouring part
            is dropped, so the grasp point and the anomaly crop belong to one part.

Named sort.py on purpose: every "pgrep -f 'python3.12 -u sort.py'" guard (station_run.py, ops/console.py,
teammates' tools) sees this run, so nothing starts a second loop and STOP finds it.

    cd /opt/viam/sorter-ali/incoming/multi && /opt/viam/sorter-ali/.venv/bin/python3.12 -u sort.py \\
        --mode sort --type auto ... [--min-gap-mm 70]

Not covered: the oblique looks and the jaws don't plan around neighbours (keep ~8-10 cm between parts), and the
judge-log latency of part 2+ includes the time it waited on the pad.
"""
import asyncio
import importlib.util
import math
import os
import signal
import sys

LIVE = os.environ.get("SORTER_LIVE", "/opt/viam/sorter-ali/current")
AXIS_MM = 8.0       # a blob this close to the target's long axis is a piece of it (head fragment), else a neighbour
NEAR_MM = 60.0      # the live look() radius
STICK_MM = 10.0     # previous choice still within this: keep it


def take_arg(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = float(sys.argv[i + 1])
        del sys.argv[i:i + 2]
        return v
    return default


MIN_GAP_MM = take_arg("--min-gap-mm", 70.0)


def choose(items, ignore, prev):
    """Watch-pose detections [(x, y, px, yaw, bbox)] -> [target] + the ignored ones (so the live loop's own ignore
    filter leaves just the target, and an all-ignored zone still doesn't read as empty)."""
    left = [it for it in items if any(math.dist(it[:2], q) <= 25 for q in ignore)]
    live = [it for it in items if it not in left]
    if not live:
        return left, None

    def gap(it):
        return min((math.dist(it[:2], o[:2]) for o in items if o is not it), default=math.inf)
    if prev is not None:
        stay = min(live, key=lambda it: math.dist(it[:2], prev))
        if math.dist(stay[:2], prev) < STICK_MM:
            return [stay] + left, stay
    clear = [it for it in live if gap(it) >= MIN_GAP_MM]
    pick = max(clear, key=lambda it: it[2]) if clear else max(live, key=gap)
    return [pick] + left, pick


def own_part(blobs, target):
    """Close-up detections with ends -> the target part's blobs only: the one nearest the target, plus blobs on its
    long axis within NEAR_MM (pieces of the same part)."""
    near = [b for b in blobs if math.dist(b[:2], target) < NEAR_MM]
    if not near:
        return blobs
    anchor = min(near, key=lambda b: math.dist(b[:2], target))
    ax, ay = math.cos(math.radians(anchor[3])), math.sin(math.radians(anchor[3]))
    keep = [b for b in near if b is anchor or abs((b[0] - anchor[0]) * ay - (b[1] - anchor[1]) * ax) < AXIS_MM]
    return keep + [b for b in blobs if b not in near]      # far blobs: the live filter drops them anyway


def patch(S):
    """Wrap the live module's detect / Sorter.watch / Sorter.look. Refuse before any motion if they're not there."""
    for name in ("detect",):
        if not callable(getattr(S, name, None)):
            raise SystemExit(f"multi: live sort.py has no {name}(); this wrapper needs updating")
    for name in ("watch", "look"):
        if not callable(getattr(S.Sorter, name, None)):
            raise SystemExit(f"multi: live Sorter has no {name}(); this wrapper needs updating")
    st = {"sorter": None, "prev": None, "target": None}
    live_detect, live_watch, live_look = S.detect, S.Sorter.watch, S.Sorter.look

    def detect(rgb, view, region, ends=False):
        out = live_detect(rgb, view, region, ends)
        if view is not None and region is not None and st["sorter"] is not None:          # the watch loop
            out, pick = choose(out, getattr(st["sorter"], "ignore_xy", []), st["prev"])
            if pick is not None and (st["prev"] is None or math.dist(pick[:2], st["prev"]) >= STICK_MM):
                print(f"  multi: target ({pick[0]:.0f}, {pick[1]:.0f}) of {len(out)} in view", flush=True)
            st["prev"] = pick[:2] if pick is not None else None
        elif view is not None and region is None and ends and st["target"] is not None:   # the close-up look
            out = own_part(out, st["target"])
        return out

    async def watch(self, *a, **k):
        st["sorter"], st["prev"] = self, None
        try:
            return await live_watch(self, *a, **k)
        finally:
            st["sorter"] = None

    async def look(self, item, *a, **k):
        st["target"] = tuple(item[:2])
        try:
            return await live_look(self, item, *a, **k)
        finally:
            st["target"] = None

    S.detect, S.Sorter.watch, S.Sorter.look = detect, watch, look


def main():
    os.chdir(LIVE)                     # live sort.py resolves models/, runs/, config/ from here
    sys.path[0] = LIVE                 # and imports pipeline, screws, vh from here (never this sort.py)
    spec = importlib.util.spec_from_file_location("livesort", os.path.join(LIVE, "sort.py"))
    S = importlib.util.module_from_spec(spec)
    sys.modules["livesort"] = S
    spec.loader.exec_module(S)
    patch(S)
    print(f"multi: live sort.py from {os.path.realpath(LIVE)}, min gap {MIN_GAP_MM:.0f} mm", flush=True)
    if hasattr(S, "_sigterm"):
        signal.signal(signal.SIGTERM, S._sigterm)
    asyncio.run(S.main())


if __name__ == "__main__":
    main()
