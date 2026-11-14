"""Write a dashboard Models-tab report (schema dashboard-replay-v1) for one bundle on a frozen benchmark.

    python tools/dashboard_replay.py --bundle models/X/bundle.json --label "PatchCore p95 thresholds" \
        --out runs/_analysis/x-top-replay.json [--type-clf models/type_clf_v1/type_clf.json] [--device CPU] [--runs runs]

Scores every benchmark member's top capture exactly as the live loop does (vh.anomaly.AnomalyModels: part-top-v2 crop,
size gate, type routing, OpenVINO on the chosen device). `routed` = automatic type; `oracle` = labelled type.
Read-only on runs/ and models/; writes only --out. No robot connection.
"""
import argparse
import hashlib
import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vh.anomaly import AnomalyModels  # noqa: E402

SURFACE_Z = {"cardboard": 6.5, "white": -1.3}      # as part_sizes.py


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--benchmark", type=Path, default=ROOT / "config" / "benchmarks" / "development-v1.json")
    ap.add_argument("--runs", type=Path, default=ROOT / "runs")
    ap.add_argument("--sizes", type=Path, default=ROOT / "config" / "part_sizes.json")
    ap.add_argument("--type-clf", default=None)
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--background", default="cardboard")
    ap.add_argument("--agent", default="claude-code/claude-fable-5-2")
    ap.add_argument("--operator", default="aayus (git: aayus@sticker)")
    ap.add_argument("--branch", default="aayush/integration")
    a = ap.parse_args()
    if a.out.exists():
        ap.error("--out exists; reports are never overwritten")
    kw = {"type_clf": a.type_clf} if a.type_clf else {}
    am = AnomalyModels(a.bundle, a.device, sizes=a.sizes, **kw)
    am.warm("auto", a.background)
    man = json.loads(a.bundle.read_text())
    split = {}
    for e in man["models"].values():
        if e["view"] != "top":
            continue
        for name in ("train", "calibration", "test"):
            for p in e.get(f"{name}_pick_ids", []):
                split[(e["part_type"], p)] = name
    rows, errors = [], []
    for mem in json.loads(a.benchmark.read_text())["members"]:
        d = a.runs / mem["pick"]
        try:
            meta = json.loads((d / "meta.json").read_text())
            top = meta["top"][Path(mem["file"]).stem]
            fx = (meta.get("camera") or {}).get("fx")
            mmpx = (top["cam_t"][2] - SURFACE_Z[a.background]) / fx if fx else None
            digest = hashlib.sha256((d / mem["file"]).read_bytes()).hexdigest()
            crop, _ = am.crop(str(d / mem["file"]), top["bbox"], "top", mmpx)
            pose = meta.get("pose") or "lying"
            routed = am.score(crop, "auto", pose, "top", a.background).fields()
            selected = am.last_type
            oracle = am.score(crop, meta["type"], pose, "top", a.background).fields()
        except Exception as e:  # noqa: BLE001  one bad capture must not hide the rest
            errors.append({"pick": mem["pick"], "error": f"{type(e).__name__}: {e}"})
            continue
        rows.append({"pick": mem["pick"], "file": mem["file"], "type": meta["type"], "label": meta.get("label"),
                     # defects are never used for fitting or thresholds; good picks follow the bundle's split
                     "split": "test" if meta.get("label") != "good" else split.get((meta["type"], mem["pick"]), "unknown"),
                     "bbox": top["bbox"], "image_sha256": digest, "routed": routed, "oracle": oracle,
                     "selected_type": selected, "size": am.last_size})
    report = {"schema": "dashboard-replay-v1", "label": a.label, "bundle": str(a.bundle),
              "bundle_sha256": hashlib.sha256(a.bundle.read_bytes()).hexdigest(), "crop_policy": man.get("crop_policy"),
              "device": a.device, "type_clf": a.type_clf, "agent": a.agent,
              "operator": a.operator, "host": socket.gethostname(), "branch": a.branch,
              "model_family": man.get("model_family", "patchcore"),
              "train_picks": len({p for e in man["models"].values() if e["view"] == "top" for p in e.get("train_pick_ids", [])}),
              "limitations": ["Development picks, repeated specimens; top-view anomaly only, no tape rule."],
              "rows": rows, "errors": errors, "completed": time.time()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report))
    ok = [r for r in rows if r["split"] == "test"]
    f = lambda rs, lab: sum(bool(r["routed"].get("anomalous")) for r in rs if (r["label"] == "good") == lab)
    print(json.dumps({"rows": len(rows), "errors": len(errors), "held_out": len(ok),
                      "good_rejected": f(ok, True), "good": sum(r["label"] == "good" for r in ok),
                      "defects_flagged": f(ok, False), "defects": sum(r["label"] != "good" for r in ok),
                      "unknown_type": sum(r["routed"]["status"] == "unknown_type" for r in ok),
                      "not_test_split": len(rows) - len(ok)}))


if __name__ == "__main__":
    main()
