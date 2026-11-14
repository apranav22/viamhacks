"""Replay threshold policies on saved held-out scores (exp_backbone_eval report.json). Usage: python tools/threshold_replay.py exp/<run>/report.json

Good picks: score already held out (bank from other runs). Their threshold comes from OTHER runs' good scores only
(leave-one-run-out on the threshold too; one-run groups: leave-one-pick-out). Defects: threshold from all good scores.
"""
import json, sys
from collections import defaultdict
import numpy as np

MIN_BANK = 10
rep = json.load(open(sys.argv[1]))["backbones"]
POL = {"max x1.03 (now)": lambda g: max(g) * 1.03, "max": max,
       "p95": lambda g: float(np.percentile(g, 95)), "p90": lambda g: float(np.percentile(g, 90)),
       "median+3MAD": lambda g: float(np.median(g) + 3 * 1.4826 * np.median(np.abs(np.array(g) - np.median(g)))),
       "median+2MAD": lambda g: float(np.median(g) + 2 * 1.4826 * np.median(np.abs(np.array(g) - np.median(g))))}
for bb, r in rep.items():
    groups = defaultdict(list)
    for pid, v in r["picks"].items():
        t = v.get("top")
        if t:
            groups[json.dumps(t["threshold"], sort_keys=True)].append((pid.split("/")[0], pid, t["label"], t["top1"]))
    print(f"\n{bb}")
    for name, f in POL.items():
        tp = fn = fr = tn = 0
        for picks in groups.values():
            good = [p for p in picks if p[2] == "good"]
            runs = {p[0] for p in good}
            for run, pid, lab, s in good:
                ref = [q[3] for q in good if (q[0] != run if len(runs) > 1 else q[1] != pid)]
                if not ref:
                    continue
                if len(ref) < MIN_BANK:  # folds whose model saw fewer good picks are not deployment-like
                    continue
                if s >= f(ref):
                    fr += 1
                else:
                    tn += 1
            allg = [q[3] for q in good]
            for run, pid, lab, s in picks:
                if lab == "good" or not allg:
                    continue
                if s >= f(allg):
                    tp += 1
                else:
                    fn += 1
        print(f"  {name:16s} defects caught {tp}/{tp + fn}   good rejected {fr}/{fr + tn}")
