"""Measure every part type's top-view size from good collect picks -> config/part_sizes.json (used by type auto).

    python part_sizes.py --runs runs/A runs/B ... [--out config/part_sizes.json] [--check]

Size = part_crop at the fixed 190 mm look, in mm: [length, width, sqrt(area)]; per type median and robust spread
(1.4826 * MAD + 0.5). --check prints leave-one-out nearest-type accuracy and in-type distance percentiles.
"""
import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from vh.anomaly import part_crop


def measure(runs, background="cardboard"):
    rows = []
    for run in map(Path, runs):
        ex = json.loads((run / "exclude.json").read_text()) if (run / "exclude.json").exists() else {}
        for line in (run / "decisions.jsonl").read_text().splitlines():
            r = json.loads(line)
            name = f"item_{r['item']:03d}"
            if r.get("decision") != "collect" or name in ex or not (run / name / "meta.json").exists():
                continue
            m = json.loads((run / name / "meta.json").read_text())
            t = (m.get("top") or {}).get("top_1") or {}
            if m.get("label") != "good" or m.get("background", "white") != background or not t.get("bbox"):
                continue
            fx = (m.get("camera") or {}).get("fx")
            if not fx:
                continue
            mmpx = (t["cam_t"][2] - (6.5 if background == "cardboard" else -1.3)) / fx
            try:
                _, info = part_crop(run / name / "top_1.jpg", t["bbox"])
            except ValueError:
                continue
            rows.append((m["type"], np.array([info["length_px"] * mmpx, info["width_px"] * mmpx,
                                              info["part_px"] ** 0.5 * mmpx])))
    return rows


def stats(rows):
    by = defaultdict(list)
    for ty, v in rows:
        by[ty].append(v)
    out = {}
    for ty, vs in by.items():
        a = np.array(vs)
        med = np.median(a, 0)
        out[ty] = {"median": np.round(med, 2).tolist(),
                   "spread": np.round(np.median(np.abs(a - med), 0) * 1.4826 + 0.5, 2).tolist(), "n": len(vs)}
    return out


def dist(v, s):
    return math.sqrt(sum(((x - m) / sp) ** 2 for x, m, sp in zip(v, s["median"], s["spread"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", default="config/part_sizes.json")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    rows = measure(a.runs)
    st = stats(rows)
    for ty, s in sorted(st.items()):
        print(f"{ty:18} n {s['n']:3}  median L W sqrtA {s['median']}  spread {s['spread']}")
    if a.check:
        ok, own = 0, []
        conf = defaultdict(int)
        for i, (ty, v) in enumerate(rows):
            loo = stats([r for j, r in enumerate(rows) if j != i])
            d = {t: dist(v, s) for t, s in loo.items()}
            p = min(d, key=d.get)
            ok += p == ty
            own.append(d.get(ty, 99))
            if p != ty:
                conf[(ty, p)] += 1
        print(f"leave-one-out nearest type: {ok}/{len(rows)}; confusions {dict(conf)}")
        print(f"in-type distance p50 {np.percentile(own, 50):.1f} p95 {np.percentile(own, 95):.1f} max {max(own):.1f}")
    st["_comment"] = (f"Top-view size per type (mm: length, width, sqrt area) from part_crop at the 190 mm look; median and "
                      f"1.4826*MAD+0.5. part_sizes.py {time.strftime('%Y-%m-%d %H:%M')} over {len(a.runs)} runs.")
    Path(a.out).write_text(json.dumps(st, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
