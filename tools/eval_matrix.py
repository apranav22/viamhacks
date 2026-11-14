"""Score one anomaly bundle on EVERY top-camera pick of the given runs, tagging each pick with its role for this bundle.

    python tools/eval_matrix.py --bundle models/X/bundle.json --label "PatchCore v4" --runs runs/*_collect \
        --type-clf models/type_clf_v1/type_clf.json --out runs/_analysis/matrix-X.json

Per pick (same collection filter and crop as training: vh.anomaly_data.collect_samples, AnomalyModels.crop):
  split   train | calibration | test (held out, same runs) | unseen (run never given to this bundle)
  size    verdict with automatic size routing (the live default)
  clf     verdict with the ResNet-18 type classifier (size gate still decides "unknown")
  oracle  verdict with the recorded part type (isolates routing errors from model errors)
Each distinct (crop, type) is inferred once. Read-only on runs/ and models/; writes only --out. No robot connection.
[claude-code/claude-opus-5-5 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/model-compare · 2026-11-14]
"""
import argparse
import hashlib
import json
import socket
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vh.anomaly import AnomalyModels, rgb_image  # noqa: E402
from vh.anomaly_data import collect_samples  # noqa: E402

SURFACE_Z = {"cardboard": 6.5, "white": -1.3}      # as part_sizes.py / dashboard_replay.py


def compact(score):
    f = score.fields()
    return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in f.items() if k in ("status", "score", "threshold", "anomalous")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", required=True, nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--type-clf", default=None)
    ap.add_argument("--sizes", type=Path, default=ROOT / "config" / "part_sizes.json")
    ap.add_argument("--benchmark", type=Path, default=ROOT / "config" / "benchmarks" / "development-v1.json")
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--background", default="cardboard")
    ap.add_argument("--agent", default="unknown/unknown")
    ap.add_argument("--operator", default="unknown")
    ap.add_argument("--branch", default="unknown")
    a = ap.parse_args()
    if a.out.exists():
        ap.error("--out exists; reports are never overwritten")
    man = json.loads(a.bundle.read_text())
    tops = [e for e in man["models"].values() if e["view"] == "top" and e["background"] == a.background]
    types = {e["part_type"] for e in tops}
    pooled = types == {"any"}
    split = {}
    for e in tops:
        for name in ("train", "calibration", "test"):
            for p in e.get(f"{name}_pick_ids", []):
                split[(e["part_type"], p)] = name
    # Runs this bundle was built from: its dataset manifest (all trainers write one) or the recorded run list.
    ds = a.bundle.parent / "dataset" / "dataset.json"
    seen_runs = set()
    if ds.exists():
        d = json.loads(ds.read_text())
        seen_runs = {Path(s["source_run"]).name for s in d.get("samples", [])}
        seen_runs |= {s["pick"].split("/")[0] for s in d.get("skipped", []) if "pick" in s}
    seen_runs |= {Path(r).name for r in man.get("runs", [])}
    seen_runs |= {p.split("/")[0] for (_, p) in split}
    bench = {(m["pick"], m["file"]) for m in json.loads(a.benchmark.read_text())["members"]}

    am = AnomalyModels(a.bundle, a.device, sizes=a.sizes, **({"type_clf": a.type_clf} if a.type_clf and not pooled else {}))
    am.warm("auto", a.background)
    records, _ = collect_samples([r for r in a.runs if (r / "decisions.jsonl").exists()], "each", a.background)
    records = [r for r in records if r["view"] == "top"]
    # Only the current wrist-camera format (1280x720 since 2026-11-13 17:05); older frames are not comparable.
    keep, old = [], 0
    for r in records:
        with Image.open(r["image"]) as im:
            current = im.size == (1280, 720)
        if current:
            keep.append(r)
        else:
            old += 1
    rows, errors = [], []
    t0 = time.time()
    for i, r in enumerate(keep):
        img = Path(r["image"])
        pick, file = r["pick_id"], img.name
        try:
            meta = json.loads((img.parent / "meta.json").read_text())
            top = meta["top"][img.stem]
            fx = (meta.get("camera") or {}).get("fx")
            mmpx = (top["cam_t"][2] - SURFACE_Z[a.background]) / fx if fx else None
            crop, _ = am.crop(str(img), top["bbox"], "top", mmpx)
            cache = {}

            def score(ty):
                if ty not in cache:
                    cache[ty] = compact(am.score(crop, ty, r["pose"], "top", a.background))
                return dict(cache[ty], type=ty)
            known = "any" if pooled else r["part_type"]
            oracle = score(known)
            if pooled:
                size = clf = dict(oracle)
            else:
                ty, dist = am.size_type()
                size_ty = ty if ty and dist <= am.UNKNOWN_SIZE_DIST else None
                size = score(size_ty) if size_ty else {"status": "unknown_type", "type": None}
                clf = size
                if size_ty and am.type_clf is not None:
                    allowed = types & set(am.type_clf.classes)
                    cty, _ = am.type_clf.predict(rgb_image(crop), allowed=allowed)
                    clf = score(cty)
            run = pick.split("/")[0]
            role = split.get((known, pick)) or ("test" if r["label"] != "good" and run in seen_runs else
                                                 "excluded" if run in seen_runs else "unseen")
            rows.append({"pick": pick, "file": file, "type": r["part_type"], "label": r["label"], "split": role,
                         "bench": (pick, file) in bench, "bbox": top["bbox"],
                         "image_sha256": hashlib.sha256(img.read_bytes()).hexdigest(),
                         "size": size, "oracle": oracle, **({"clf": clf} if am.type_clf is not None else {})})
        except Exception as e:  # noqa: BLE001  one bad capture must not hide the rest
            errors.append({"pick": pick, "error": f"{type(e).__name__}: {e}"})
        if i % 50 == 0:
            print(f"{i}/{len(keep)} {time.time() - t0:.0f}s", flush=True)
    report = {"schema": "eval-matrix-v1", "label": a.label, "bundle": str(a.bundle),
              "bundle_sha256": hashlib.sha256(a.bundle.read_bytes()).hexdigest(), "crop_policy": man.get("crop_policy"),
              "model_family": man.get("model_family", "patchcore"), "pooled": pooled, "types": sorted(types),
              "routings": ["size"] + (["clf"] if am.type_clf is not None else []), "type_clf": a.type_clf,
              "train_picks": len({p for (_, p), s in split.items() if s == "train"}),
              "seen_runs": sorted(seen_runs), "device": a.device, "background": a.background,
              "agent": a.agent, "operator": a.operator, "host": socket.gethostname(), "branch": a.branch,
              "skipped_old_camera": old, "rows": rows, "errors": errors, "completed": time.time()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report))
    from collections import Counter
    print(json.dumps({"rows": len(rows), "errors": len(errors), "old_camera": old,
                      "splits": Counter(r["split"] for r in rows), "seconds": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
