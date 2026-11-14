"""Joint speed vs collect-cycle time. MOVES THE ARM and CHANGES ITS SPEED (restored to 60 deg/s at the end).

    python speed_experiment.py --label good --type hex_bolt_short --reps 2              # 60 90 120 150 180
    python speed_experiment.py --speeds 60,120 --reps 3 --label good --type hex_bolt_short
    python speed_experiment.py --analyze logs/speed-experiment-<time>.json               # re-read, no robot

For each speed, lowest first: arm.do_command set_speed, then one `sort.py --mode collect` run of --reps picks
(sort.py now sets parts down gently by default; any unknown option is passed to sort.py). Acceleration stays at the module default:
one variable at a time. The sweep stops at the first failed run, and the speed always goes back to 60 deg/s,
also on an error or Ctrl-C.

Timing comes from each run's runs/<run>/decisions.jsonl (cycle_s, latency) and runs/<run>/dash/events.jsonl (the
dashboard's spans, so dashboard/server.py must be running): each cycle split into arm moves, gripper and the rest
(cameras, computation, network). Results: logs/speed-experiment-<time>.json.
"""

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time

from viam.components.arm import Arm

from station import connect

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SPEED = 60.0          # the station's setting before the experiment (viam-ufactory-xarm default)
MAX_SPEED = 180.0             # UFACTORY 850 spec and the module's limit
MOVE_PHASES = {"hover", "aim", "descend", "lift", "view", "over", "lower", "retreat", "return", "rescan", "to"}
GRIPPER_PHASES = {"grab", "open", "place", "release", "drop"}


async def set_speed(deg_s: float):
    async with await connect() as m:
        await Arm.from_robot(m, "arm").do_command({"set_speed": float(deg_s)})
    print(f"arm speed -> {deg_s:.0f} deg/s", flush=True)


def newest_run(before: set) -> str | None:
    runs = os.path.join(HERE, "runs")
    new = [d for d in os.listdir(runs) if d.endswith("_collect") and d not in before]
    return os.path.join(runs, sorted(new)[-1]) if new else None


def analyze_run(run_dir: str) -> dict:
    """Per item: cycle s, latency ms, and the cycle split into moves / gripper / other (s)."""
    decisions = [json.loads(l) for l in open(os.path.join(run_dir, "decisions.jsonl"))]
    spans = []
    ev_path = os.path.join(run_dir, "dash", "events.jsonl")
    if os.path.exists(ev_path):
        spans = [e for e in map(json.loads, open(ev_path)) if e.get("k") == "span"]
    items = []
    for d in decisions:
        mine = [s for s in spans if s.get("item") == d["item"]]
        move = sum(s["ms"] for s in mine if (s.get("phase") or "").lower() in MOVE_PHASES) / 1000
        grip = sum(s["ms"] for s in mine if (s.get("phase") or "").lower() in GRIPPER_PHASES) / 1000
        cycle = d.get("cycle_s")
        items.append({"item": d["item"], "decision": d["decision"], "reason": d.get("reason"), "cycle_s": cycle,
                      "latency_ms": d.get("latency_ms"), "move_s": round(move, 2), "gripper_s": round(grip, 2),
                      "other_s": round(cycle - move - grip, 2) if cycle and mine else None,
                      "views": sorted((d.get("scores") or {}).keys())})
    return {"run": os.path.basename(run_dir), "items": items}


def summary(results: list):
    print(f"\n{'speed':>6} {'cycles':>6} {'cycle s (mean)':>15} {'moves s':>8} {'gripper s':>9} {'other s':>8} {'latency ms':>10}")
    for r in results:
        ok = [i for i in r["items"] if i["cycle_s"]]
        if not ok:
            print(f"{r['speed']:6.0f} {0:6d}   (no completed cycles: {r.get('error')})")
            continue
        mean = lambda k: statistics.mean(i[k] for i in ok if i[k] is not None) if any(i[k] is not None for i in ok) else float("nan")
        print(f"{r['speed']:6.0f} {len(ok):6d} {mean('cycle_s'):15.1f} {mean('move_s'):8.1f} {mean('gripper_s'):9.1f} "
              f"{mean('other_s'):8.1f} {mean('latency_ms'):10.0f}")


def main(args):
    if args.analyze:
        summary(json.load(open(args.analyze))["results"])
        return
    speeds = sorted(float(s) for s in args.speeds.split(","))
    if max(speeds) > MAX_SPEED:
        raise SystemExit(f"{max(speeds)} deg/s is over the arm's limit of {MAX_SPEED}")
    out = os.path.join(HERE, "logs", f"speed-experiment-{time.strftime('%H%M%S')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    record = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "args": vars(args), "results": []}
    try:
        for speed in speeds:
            asyncio.run(set_speed(speed))
            before = set(os.listdir(os.path.join(HERE, "runs")))
            cmd = [sys.executable, os.path.join(HERE, "sort.py"), "--mode", "collect",
                   "--reps", str(args.reps), "--label", args.label, "--type", args.type, *args.sort_args]
            print(f"\n=== {speed:.0f} deg/s: {' '.join(cmd[1:])}", flush=True)
            proc = subprocess.run(cmd, cwd=HERE)
            run_dir = newest_run(before)
            res = {"speed": speed, "returncode": proc.returncode, "items": []}
            if run_dir:
                res.update(analyze_run(run_dir))
            if proc.returncode != 0:
                res["error"] = f"sort.py exited with {proc.returncode}"
            record["results"].append(res)
            json.dump(record, open(out, "w"), indent=1)
            done = [i for i in res["items"] if i["cycle_s"]]
            if proc.returncode != 0 or len(done) < args.reps or any(i["decision"] in ("none", "dropped") for i in done):
                print(f"stopping the sweep at {speed:.0f} deg/s: {res.get('error') or 'a cycle did not complete cleanly'}")
                break
    finally:
        asyncio.run(set_speed(DEFAULT_SPEED))
        json.dump(record, open(out, "w"), indent=1)
        summary(record["results"])
        print("results:", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speeds", default="60,90,120,150,180", help="joint speeds to try, deg/s (run lowest first)")
    p.add_argument("--reps", type=int, default=2, help="collect cycles per speed")
    p.add_argument("--label", default="good")
    p.add_argument("--type", default="unknown")
    p.add_argument("--analyze", help="print the summary of an earlier results file (no robot)")
    a, extra = p.parse_known_args()
    a.sort_args = extra          # anything else goes to sort.py unchanged, e.g. --background cardboard --assume-lying
    main(a)
