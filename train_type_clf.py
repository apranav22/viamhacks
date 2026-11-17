"""Train the part-type classifier used by `sort.py --type auto` (vh/type_clf.py).

    python train_type_clf.py --runs 'runs/*_collect' [--out models/type_clf_v1] [--background cardboard]

Exports ResNet-18 (ImageNet weights, classifier removed) to OpenVINO IR, computes features of every good top-view
model crop THROUGH THAT IR (so training and runtime features match), fits a standardised multinomial logistic
regression, and writes <out>/type_clf.json with the head, provenance and evaluation. Needs torch, torchvision,
scikit-learn and openvino (training environment; the station only needs openvino + numpy).
Evaluation: leave-one-pick-out, and leave-one-run-out on types seen in more than one run (picks within a run are
the same physical part), plus type accuracy on defective picks (never trained on).
"""
import argparse
import glob
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from vh.anomaly import part_crop
from vh.type_clf import SIZE, FeatureNet, head_probs


def picks(runs, background):
    out = []
    for run in sorted(map(Path, runs)):
        if not (run / "decisions.jsonl").exists():
            continue
        ex = json.loads((run / "exclude.json").read_text()) if (run / "exclude.json").exists() else {}
        for line in (run / "decisions.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            name = f"item_{r['item']:03d}"
            if r.get("decision") != "collect" or name in ex or not (run / name / "meta.json").exists():
                continue
            m = json.loads((run / name / "meta.json").read_text())
            t = (m.get("top") or {}).get("top_1") or {}
            if m.get("background", "white") != background or not t.get("bbox") or not m.get("type"):
                continue
            try:
                crop, _ = part_crop(run / name / "top_1.jpg", t["bbox"])
            except (ValueError, OSError):
                continue
            out.append(dict(run=run.name, item=name, type=m["type"], label=m.get("label"), crop=crop.convert("RGB")))
    return out


def fit(X, y):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(max_iter=5000, C=1.0, class_weight="balanced").fit(sc.transform(X), y)
    return {"classes": [str(c) for c in lr.classes_], "scaler_mean": sc.mean_.tolist(), "scaler_scale": sc.scale_.tolist(),
            "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist()}


def predict(head, X):
    return [max((p := head_probs(x, head)), key=p.get) for x in X]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=Path("models/type_clf_v1"))
    ap.add_argument("--background", default="cardboard")
    a = ap.parse_args()
    runs = sorted({d for pat in a.runs for d in (glob.glob(pat) or [pat])})
    a.out.mkdir(parents=True, exist_ok=True)

    import openvino as ov
    import torch
    import torchvision
    net = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.IMAGENET1K_V1).eval()
    net.fc = torch.nn.Identity()
    xml = a.out / "resnet18_avgpool.xml"
    ov.save_model(ov.convert_model(net, example_input=torch.zeros(1, 3, SIZE, SIZE)), str(xml), compress_to_fp16=False)

    data = picks(runs, a.background)
    good = [d for d in data if d["label"] == "good"]
    bad = [d for d in data if d["label"] not in (None, "good", "unknown")]
    fnet = FeatureNet(xml, "CPU")
    Xg = np.array([fnet(d["crop"]) for d in good])
    Xb = np.array([fnet(d["crop"]) for d in bad]) if bad else np.zeros((0, Xg.shape[1]))
    y = np.array([d["type"] for d in good])
    rn = np.array([d["run"] for d in good])
    idx = np.arange(len(good))

    lopo = sum(predict(fit(Xg[idx != i], y[idx != i]), Xg[i:i + 1])[0] == y[i] for i in idx)
    multi = {t for t in set(y) if len(set(rn[y == t])) > 1}
    ok = n = 0
    conf = Counter()
    for r in sorted(set(rn)):
        test = idx[(rn == r) & np.isin(y, list(multi))]
        if not len(test):
            continue
        head = fit(Xg[rn != r], y[rn != r])
        for j, p in zip(test, predict(head, Xg[test])):
            n += 1
            ok += p == y[j]
            if p != y[j]:
                conf[f"{y[j]} -> {p}"] += 1

    head = fit(Xg, y)
    known = set(head["classes"])
    bad_known = [i for i, d in enumerate(bad) if d["type"] in known]
    bad_ok = sum(predict(head, Xb[i:i + 1])[0] == bad[i]["type"] for i in bad_known)
    ev = {"good_picks": len(good), "leave_one_pick_out": f"{lopo}/{len(good)}",
          "leave_one_run_out": f"{ok}/{n}", "leave_one_run_out_types": sorted(multi),
          "leave_one_run_out_errors": dict(conf.most_common()),
          "defect_picks_type_correct": f"{bad_ok}/{len(bad_known)}",
          "per_type": {t: {"picks": int((y == t).sum()), "runs": len(set(rn[y == t]))} for t in sorted(known)}}
    out = {"schema": 1, "feature_xml": xml.name, "feature": "torchvision resnet18 IMAGENET1K_V1 avgpool, L2-normalised",
           "input": f"part_crop (part-top-v2) -> RGB {SIZE}x{SIZE} bilinear, ImageNet mean/std",
           "background": a.background, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "runs": [Path(r).name for r in runs], "sha256": {xml.name: sha(xml), xml.with_suffix(".bin").name: sha(xml.with_suffix(".bin"))},
           "eval": ev, **head}
    (a.out / "type_clf.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(ev, indent=1))
    print(f"wrote {a.out / 'type_clf.json'}")


if __name__ == "__main__":
    main()
