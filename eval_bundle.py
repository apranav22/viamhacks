"""Score saved picks with a bundle, exactly as the live loop would (same crop policy, OpenVINO, chosen device).
No robot connection.

    python eval_bundle.py --bundle models/each_cardboard_v3/bundle.json --runs runs/A runs/B [--type auto] [--margin 1.03]

--margin rescales every threshold to margin * (calibration good max) (= threshold / bundle margin * margin).
Prints per pick: label, part type, top score / threshold, verdict; then counts per label.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from vh.anomaly import AnomalyModels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--runs", nargs="+", required=True, type=Path)
    ap.add_argument("--type", default="auto")
    ap.add_argument("--views", nargs="+", default=["top"])
    ap.add_argument("--margin", type=float, default=None)
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--held-out-goods", action="store_true", help="good picks: only the bundle's test picks")
    a = ap.parse_args()
    am = AnomalyModels(a.bundle, a.device)
    am.warm(a.type, "cardboard")
    if a.margin:
        for key, (entry, *rest) in am.models.items():
            entry["threshold"] = entry["threshold"] / entry.get("margin", 1.0) * a.margin
    counts = defaultdict(lambda: [0, 0])
    man = json.loads(a.bundle.read_text())
    test_ids = {p for e in man["models"].values() for p in e["test_pick_ids"]}
    for run in a.runs:
        for line in (run / "decisions.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r.get("decision") != "collect":
                continue
            d = run / f"item_{r['item']:03d}"
            m = json.loads((d / "meta.json").read_text())
            if a.held_out_goods and m.get("label") == "good" and f"{run.name}/item_{r['item']:03d}" not in test_ids:
                continue
            for view in a.views:
                if view == "top":
                    t = (m.get("top") or {}).get("top_1") or {}
                    img, bbox = d / "top_1.jpg", t.get("bbox")
                else:
                    v = (m.get("views") or {}).get(view)
                    img, bbox = d / f"web_{view}.jpg", v and v["crop_box"]
                if not bbox:
                    continue
                try:
                    crop, _ = am.crop(str(img), bbox, view)
                except ValueError as e:
                    print(f"{run.name}/{r['item']:03d} {view}: crop failed {e}")
                    continue
                s = am.score(crop, a.type, "lying", view, "cardboard")
                f = s.fields()
                lab = m.get("label")
                bad = bool(f["anomalous"])
                counts[(lab, view)][0] += bad
                counts[(lab, view)][1] += 1
                print(f"{run.name}/{r['item']:03d} {view:8} {lab:7} {m.get('type'):17} "
                      f"{f['score'] and round(f['score'], 2)} / {f['threshold'] and round(f['threshold'], 2)} "
                      f"{'REJECT' if bad else 'pass  '} {f['detail'] or ''}")
    print("\nflagged anomalous per label/view:")
    for (lab, view), (n_bad, n) in sorted(counts.items()):
        print(f"  {lab:7} {view:8} {n_bad}/{n}")


if __name__ == "__main__":
    main()
