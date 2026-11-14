"""Still-frame report for one run: did every capture wait for a still frame, what did it cost, and are the pictures
sharper than a run taken without the wait. Offline: reads runs/<id>/timeline.jsonl and the saved JPEGs.

    python -m tools.still_report                       # newest run vs runs/20261114_110157_collect (no still wait)
    python -m tools.still_report runs/<id> --baseline runs/<other>

Sharpness is the variance of the Laplacian of the grey image (higher = sharper), on the saved part crops and top
images. Same part and views compare well; different parts or lighting do not, so read it as a relative check."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "runs" / "20261114_110157_collect"   # 11:02, --tcp-limit build, captures without the still wait
STEADY = 0.002                                          # sort.REF_STEADY_FRAC (kept in step by hand)


def sharpness(path):
    g = np.asarray(Image.open(path).convert("L"), float)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


def kind(name):
    """Image group: top look, wrist oblique, webcam view crop (the full webcam frame is mostly background)."""
    stem = Path(name).stem
    if stem.startswith("top_"):
        return "top (wrist)"
    if stem.startswith("oblique"):
        return "oblique (wrist)"
    if stem.startswith("crop_oblique"):
        return None
    if stem.startswith("crop_"):
        return f"webcam {stem[5:]}"
    return None


def sharp_by_kind(run):
    out = defaultdict(list)
    for p in sorted(run.glob("item_*/*.jpg")):
        k = kind(p.name)
        if k:
            out[k].append(sharpness(p))
    return out


def group(label):
    for prefix in ("look", "view", "ref", "depth look", "oblique"):
        if label.startswith(prefix):
            return label if prefix == "view" else prefix
    return label


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", type=Path)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    a = ap.parse_args()
    run = a.run or max((p for p in (ROOT / "runs").glob("2*") if (p / "timeline.jsonl").exists()), default=None)
    if run is None:
        raise SystemExit("no run with a timeline.jsonl under runs/ (runs from before the still-frame build have none)")
    events = [json.loads(line) for line in open(run / "timeline.jsonl")]
    still = [e for e in events if e["k"] == "still"]
    print(f"run {run.name}: {len(still)} captures")
    if not still:
        print("  no 'still' events: this run predates the still-frame gate, or captured nothing")
    rows = defaultdict(list)
    for e in still:
        rows[group(e["label"])].append(e)
    print(f"\n{'capture':16s} {'n':>3s} {'still':>6s} {'frames':>7s} {'wait ms':>14s}  first change (moving > {STEADY})")
    for g, es in sorted(rows.items()):
        frames = [e["frames"] for e in es]
        ms = [e["ms"] for e in es]
        first = [e["change"][0] for e in es if e["change"]]
        print(f"{g:16s} {len(es):3d} {sum(e['still'] for e in es):3d}/{len(es):<2d} "
              f"{statistics.mean(frames):7.1f} {statistics.mean(ms):6.0f} (max {max(ms):4.0f})  "
              f"median {statistics.median(first) if first else float('nan'):.4f}")
    bad = [e for e in still if not e["still"]]
    for e in bad:
        print(f"  NOT STILL: item {e.get('item')} {e['label']}: changes {e['change']}")
    total = sum(e["ms"] for e in still)
    items = len({e.get("item") for e in still}) or 1
    print(f"\nwaiting for still frames: {total / 1000:.1f} s in total, {total / 1000 / items:.1f} s per item")

    new = sharp_by_kind(run)
    base = sharp_by_kind(a.baseline) if a.baseline.exists() else {}
    print(f"\nsharpness (variance of Laplacian, median), {run.name} vs {a.baseline.name}:")
    for k in sorted(set(new) | set(base)):
        n, b = new.get(k, []), base.get(k, [])
        nm = statistics.median(n) if n else None
        bm = statistics.median(b) if b else None
        ratio = f"x{nm / bm:.2f}" if nm and bm else ""
        print(f"  {k:18s} new {nm and round(nm):>6} (n={len(n)})   baseline {bm and round(bm):>6} (n={len(b)})   {ratio}")


if __name__ == "__main__":
    main()
