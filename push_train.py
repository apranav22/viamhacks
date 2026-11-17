"""Push finished laptop collect runs to the station and start one pooled cardboard training job there.

    python push_train.py --runs 20261113_183000_collect          # push these, then train on ALL good cardboard runs
    python push_train.py --name any_cardboard_v3 --runs ...      # explicit model name

Training job: train_dashboard API on the station (one job at a time; the dashboard refuses during a judged sort run).
Type 'any' = one bank per view over every part type (the judged run can't know the type). The trainer itself skips
picks whose background/resolution differ. Moves nothing on the robot.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "http://172.16.0.182:8770/api"
# pre-fix / wrong-recipe runs: never train on them (see docs/AGENT_LOG.md)
EXCLUDE = {"20261113_172508_collect"}
FIRST_GOOD_RECIPE = "20261113_173414_collect"     # cardboard + 1280x720 + look 190 + LED


def finished(run):
    log = (ROOT / "runs" / run / "decisions.jsonl")
    return log.exists() and any(json.loads(l).get("decision") == "collect" for l in log.read_text().splitlines() if l.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="*", default=[], help="laptop runs to push first (must be finished)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--type", default="any")
    a = ap.parse_args()
    if a.runs:
        r = subprocess.run([sys.executable, str(ROOT / "deploy_station.py"), "--runs", *a.runs], cwd=ROOT,
                           capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:], flush=True)
        if r.returncode:
            raise SystemExit("push failed; not training")
    state = json.load(urllib.request.urlopen(API + "/state", timeout=10))
    station_runs = sorted({d["run"] for d in state["data"]["runs"]} if isinstance(state.get("data"), dict) and "runs" in state["data"]
                          else [])
    # fall back to every recipe-compatible laptop run (all of them were pushed by now)
    runs = [p.name for p in sorted((ROOT / "runs").glob("*_collect"))
            if p.name >= FIRST_GOOD_RECIPE and p.name not in EXCLUDE and finished(p.name)]
    if station_runs:
        runs = [r for r in runs if r in station_runs] or runs
    name = a.name or f"{a.type}_cardboard_{time.strftime('%H%M')}"
    body = json.dumps({"action": "train", "name": name, "type": a.type, "background": "cardboard", "device": "xpu",
                       "runs": runs}).encode()
    resp = json.load(urllib.request.urlopen(urllib.request.Request(API, data=body, method="POST"), timeout=20))
    print(f"training {name} on {len(runs)} runs: {resp}", flush=True)


if __name__ == "__main__":
    main()
