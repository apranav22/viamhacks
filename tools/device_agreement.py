"""Do CPU, GPU and NPU give the same anomaly scores and decisions? Run ON the station from the release folder.

    cd /opt/viam/sorter-ali/current && ../.venv/bin/python3.12 tools/device_agreement.py ../models/each_cardboard_v4 hex_bolt_partial

Scores real saved top crops (part-top-v2) of one type with that type's top model on every device; prints max/median
score difference vs CPU and how many reject decisions flip at the bundle threshold.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import openvino as ov
from PIL import Image

sys.path.insert(0, ".")
from vh.anomaly import part_crop  # noqa: E402

bundle_dir, ptype = Path(sys.argv[1]), sys.argv[2]
runs = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("../runs")
bundle = json.loads((bundle_dir / "bundle.json").read_text())
key, entry = next((k, e) for k, e in bundle["models"].items() if e["part_type"] == ptype and e["view"] == "top")
inputs = []
for meta in sorted(glob.glob(str(runs / "*_collect" / "item_*" / "meta.json"))):
    m = json.loads(Path(meta).read_text())
    t = (m.get("top") or {}).get("top_1") or {}
    if m.get("type") != ptype or m.get("background") != entry["background"] or not t.get("bbox"):
        continue
    try:
        crop, _ = part_crop(Path(meta).parent / "top_1.jpg", t["bbox"])
    except ValueError:
        continue
    h, w = entry["image_size"]
    inputs.append(np.ascontiguousarray(np.asarray(crop.convert("RGB").resize((w, h), Image.Resampling.BILINEAR),
                                                  np.float32).transpose(2, 0, 1)[None] / 255))
core = ov.Core()
model = core.read_model(str(bundle_dir / entry["xml"]))
scores = {}
for dev in core.available_devices:
    cfg = {"PERFORMANCE_HINT": "LATENCY", **({"INFERENCE_PRECISION_HINT": "f32"} if dev != "NPU" else {})}
    try:
        c = core.compile_model(model, dev, cfg)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"device": dev, "ok": False, "error": str(e)[:160]}))
        continue
    r = c.create_infer_request()
    so = next(o for o in c.outputs if "pred_score" in o.get_names())
    scores[dev] = np.array([float(r.infer({0: x})[so].reshape(-1)[0]) for x in inputs])
thr = entry["threshold"]
base = scores["CPU"]
for dev, s in scores.items():
    d = np.abs(s - base)
    print(json.dumps({"model": key, "device": dev, "n": len(s), "max_abs_diff": round(float(d.max()), 4),
                      "median_abs_diff": round(float(np.median(d)), 4), "threshold": round(thr, 4),
                      "decision_flips_vs_cpu": int(((s >= thr) != (base >= thr)).sum()),
                      "rejects": int((s >= thr).sum())}))
