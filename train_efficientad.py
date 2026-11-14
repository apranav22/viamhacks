"""Train EfficientAD-S per (type, pose, view, background) on curated good picks; export to OpenVINO as a drop-in bundle.

    IMAGENETTE_DIR=<imagenette2-160/train> python train_efficientad.py --runs runs/*_collect --type each \
        --background cardboard --views top --out models/effad_top_v1

Same dataset, splits and bundle.json schema as train_anomaly.py, and the exported model has the same contract
(input [1,3,S,S] RGB in 0..1; outputs pred_score, anomaly_map), so vh.anomaly.AnomalyModels / sort.py load it unchanged.
Why: 2026-11-14 bake-off (exp/trainable_top): EfficientAD-S caught 21/28 defects vs 10/28 for ResNet-18 PatchCore.
Threshold = max calibration good score * margin (provisional small-data rule, as train_anomaly). Needs a CUDA/CPU torch
env with anomalib 2.7 (training only). No robot connection, no upload.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from vh.anomaly import CROP_POLICY
from vh.anomaly_data import build_dataset, groups


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", nargs="+", required=True, type=Path)
    p.add_argument("--type", required=True)
    p.add_argument("--background", required=True, choices=["white", "cardboard"])
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--views", nargs="*", default=["top"])
    p.add_argument("--size", default=256, type=int)
    p.add_argument("--steps", default=1000, type=int)
    p.add_argument("--margin", default=1.15, type=float)
    p.add_argument("--device", default="cuda")
    p.add_argument("--holdout", type=Path, action="append", default=[],
                   help="benchmark json(s): their member picks are forced into the test split (never train/calibration)")
    a = p.parse_args()
    if a.out.exists():
        p.error("Choose a new output folder; existing bundles are never overwritten")
    import openvino as ov
    import torch
    from trainable_backends import EfficientAD

    a.out.mkdir(parents=True)
    dataset = build_dataset(a.runs, a.out / "dataset", a.type, a.background)
    # Adding runs reshuffles the hash split per type, which could move a frozen benchmark pick into train/calibration.
    # Force every benchmark member back into test so later comparisons on that benchmark stay held out.
    held = {m["pick"] for h in a.holdout for m in json.loads(h.read_text())["members"]}
    moved = sorted({s["pick_id"] for s in dataset["samples"] if s["pick_id"] in held and s["split"] != "test"})
    for s in dataset["samples"]:
        if s["pick_id"] in held:
            s["split"] = "test"
    dataset["holdout"] = {"benchmarks": [str(h) for h in a.holdout], "forced_to_test": moved}
    (a.out / "dataset" / "dataset.json").write_text(json.dumps(dataset, indent=2))
    print(f"holdout: {len(held)} benchmark picks; {len(moved)} moved from train/calibration to test", flush=True)
    ds = a.out / "dataset"
    bundle = {"schema": 1, "crop_policy": CROP_POLICY, "models": {}, "skipped": [], "model_family": "efficientad-s",
              "holdout": dataset["holdout"], "runs": [str(r) for r in a.runs],
              "limitations": dataset["limitations"] + ["Prototype threshold; physical item and defect holdouts still required."]}
    backend = EfficientAD(a.device, steps=a.steps, size=a.size)
    n = 0
    for key, samples in sorted(groups(dataset).items()):
        if a.views and samples[0]["view"] not in a.views:
            continue
        train = [s for s in samples if s["split"] == "train" and s["label"] == "good"]
        cal = [s for s in samples if s["split"] == "calibration" and s["label"] == "good"]
        test = [s for s in samples if s["split"] == "test"]
        if len(train) < 3 or not cal or not test:
            bundle["skipped"].append({"group": key, "reason": f"need >=3 train, >=1 cal, >=1 test; got {len(train)}, {len(cal)}, {len(test)}"})
            print(f"SKIP {key}", flush=True)
            continue
        torch.manual_seed(17); np.random.seed(17)
        import random; random.seed(17)
        t0 = time.time()
        model = backend.fit([Image.open(ds / s["image"]).convert("RGB") for s in train]).cpu().eval()

        class Export(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.m = model

            def forward(self, image):
                r = self.m(image)
                return r.pred_score, r.anomaly_map

        wrapper = Export().eval()
        converted = ov.convert_model(wrapper, example_input=torch.zeros(1, 3, a.size, a.size))
        converted.reshape({converted.input(0): [1, 3, a.size, a.size]})
        converted.outputs[0].get_tensor().set_names({"pred_score"})
        converted.outputs[1].get_tensor().set_names({"anomaly_map"})
        mdir = a.out / f"model_{n:02d}"
        mdir.mkdir()
        ov.save_model(converted, mdir / "model.xml", compress_to_fp16=False)
        req = ov.Core().compile_model(converted, "CPU", {"INFERENCE_PRECISION_HINT": "f32", "PERFORMANCE_HINT": "LATENCY"}).create_infer_request()

        def score(s):
            im = Image.open(ds / s["image"]).convert("RGB").resize((a.size, a.size), Image.Resampling.BILINEAR)
            x = np.ascontiguousarray(np.asarray(im, dtype=np.float32).transpose(2, 0, 1)[None] / 255)
            t = time.perf_counter()
            out = req.infer({0: x})
            ms = (time.perf_counter() - t) * 1000
            v = float(next(val for o, val in out.items() if "pred_score" in o.get_names()).reshape(-1)[0])
            with torch.no_grad():
                ref = float(wrapper(torch.from_numpy(x))[0].reshape(-1)[0])
            if not np.isfinite(v) or abs(v - ref) > max(0.01, 0.02 * abs(ref)):
                raise ValueError(f"OpenVINO/Torch score mismatch: {v} vs {ref}")
            return v, ms

        cal_scores = [score(s)[0] for s in cal]
        threshold = max(max(cal_scores) * a.margin, 1e-6)
        results = [{"pick_id": s["pick_id"], "label": s["label"], "score": (r := score(s))[0],
                    "anomalous": r[0] >= threshold, "infer_ms": round(r[1], 2)} for s in test]
        first = samples[0]
        entry = {k: first[k] for k in ("part_type", "pose", "view", "background")}
        entry.update(threshold=threshold, image_size=[a.size, a.size], xml=f"model_{n:02d}/model.xml",
                     train_pick_ids=sorted({s["pick_id"] for s in train}), calibration_pick_ids=sorted({s["pick_id"] for s in cal}),
                     test_pick_ids=sorted({s["pick_id"] for s in test}), calibration="prototype-good-max-margin",
                     margin=a.margin, backbone="efficientad-s", steps=a.steps, fit_seconds=round(time.time() - t0),
                     test_results=results)
        bundle["models"][key] = entry
        (a.out / "bundle.json").write_text(json.dumps(bundle, indent=2))
        g = [r for r in results if r["label"] == "good"]; d = [r for r in results if r["label"] != "good"]
        print(f"EXPORTED {key}: thr {threshold:.4f} caught {sum(r['anomalous'] for r in d)}/{len(d)} "
              f"good rejected {sum(r['anomalous'] for r in g)}/{len(g)} cpu {np.median([r['infer_ms'] for r in results]):.1f} ms "
              f"({entry['fit_seconds']} s)", flush=True)
        n += 1
    if not bundle["models"]:
        raise SystemExit("No models exported")
    print("BUNDLE", a.out / "bundle.json", flush=True)


if __name__ == "__main__":
    main()
