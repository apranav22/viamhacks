"""Per-type, pose and view OpenVINO anomaly inference. No robot or training-framework imports.

Contract: RGB float32 [1,3,H,W] in [0,1] -> raw pred_score + anomaly_map. ImageNet
normalization, frozen backbone and PatchCore nearest-neighbour search are IN the IR.
Thresholds come from disjoint good calibration picks. Missing/nonfinite outputs never mean good.
"""
import io
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

CROP_POLICY = "square-context-v1"


def rgb_image(image):
    if isinstance(image, bytes):
        image = Image.open(io.BytesIO(image))
    elif isinstance(image, (str, Path)):
        image = Image.open(image)
    elif isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    return image.convert("RGB")


def context_crop(image, bbox, margin=0.15):
    """Square context crop; shift inside frame instead of clipping the part at an edge.

    Same operation for training and live inference. No rotation, segmentation or background
    subtraction is claimed here: this first baseline deliberately retains the local background.
    """
    image = rgb_image(image)
    w, h = image.size
    x0, y0, x1, y1 = map(float, bbox)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError(f"Invalid bbox {bbox} for {image.size}")
    side = min(min(w, h), max(8, math.ceil(max(x1 - x0, y1 - y0) * (1 + 2 * margin))))
    left = min(max(0, round((x0 + x1 - side) / 2)), w - side)
    top = min(max(0, round((y0 + y1 - side) / 2)), h - side)
    box = [left, top, left + side, top + side]
    if x0 < left or x1 > left + side or y0 < top or y1 > top + side:
        raise ValueError("Part does not fit the square crop; do not silently truncate")
    return image.crop(box), box


def group_key(part_type, pose, view, background):
    return "|".join((part_type, pose, view, background))


def reject_reason(results, required_views):
    """Conservative fusion. None means all REQUIRED views passed; otherwise a reject reason."""
    for view in required_views:
        r = results.get(view)
        if not r or r.get("status") != "ok":
            return f"uncertain: {view} model/result unavailable"
        if r.get("anomalous"):
            return f"anomaly: {view} score {r['score']:.3f} >= {r['threshold']:.3f}"
    return None


@dataclass
class Score:
    status: str
    score: float | None = None
    threshold: float | None = None
    ms: float = 0.0
    anomaly_map: np.ndarray | None = None
    detail: str | None = None

    def fields(self):
        return {"status": self.status, "score": self.score, "threshold": self.threshold,
                "anomalous": self.score >= self.threshold if self.status == "ok" else None,
                "ratio": self.score / self.threshold if self.status == "ok" else None,
                "infer_ms": round(self.ms, 2), "detail": self.detail}

    def heatmap_bytes(self):
        """64x64 byte map, fixed scale: 128 ~= threshold, 255 ~= 2x threshold (NOT per-frame min/max)."""
        if self.status != "ok" or self.anomaly_map is None:
            return None
        a = Image.fromarray(self.anomaly_map.astype(np.float32)).resize((64, 64), Image.Resampling.BILINEAR)
        return np.rint(np.clip(np.asarray(a) / (2 * self.threshold), 0, 1) * 255).astype(np.uint8).tobytes()


class AnomalyModels:
    """One shared Core, one compiled model/request per selected group. Compile/warm BEFORE motion.

    Explicit CPU/GPU/NPU only; no silent device fallback. A request is owned by this serial loop,
    not shared concurrently. This object never captures camera images or controls motion.
    """
    def __init__(self, bundle, device="CPU"):
        self.path = Path(bundle)
        self.manifest = json.loads(self.path.read_text())
        if self.manifest.get("schema") != 1 or self.manifest.get("crop_policy") != CROP_POLICY:
            raise ValueError("Unsupported anomaly bundle/crop policy")
        if device.upper() not in {"CPU", "GPU", "NPU"}:
            raise ValueError("Select one explicit inference device")
        import openvino as ov
        self.core = ov.Core()
        self.device = device.upper()
        self.models = {}

    def warm(self, part_type, background):
        """Load only the requested type/background; a missing view remains explicitly unavailable."""
        for key, entry in self.manifest["models"].items():
            if entry["part_type"] != part_type or entry["background"] != background:
                continue
            if not math.isfinite(entry["threshold"]) or entry["threshold"] <= 0:
                raise ValueError(f"Invalid threshold for {key}")
            model = self.core.read_model(self.path.parent / entry["xml"])
            if not model.input(0).get_partial_shape().is_static:
                if "image_size" not in entry:
                    raise ValueError(f"Dynamic model without declared image size: {key}")
                h, w = entry["image_size"]
                model.reshape({model.input(0): [1, 3, h, w]})
            compiled = self.core.compile_model(model, self.device, {"PERFORMANCE_HINT": "LATENCY",
                **({"INFERENCE_PRECISION_HINT": "f32"} if self.device != "NPU" else {})})
            shape = tuple(compiled.input(0).shape)
            if len(shape) != 4 or shape[:2] != (1, 3):
                raise ValueError(f"Invalid model input for {key}: {shape}")
            # Compilers may add numeric aliases; any_name need not select our semantic name.
            outputs = {name: o for o in compiled.outputs for name in o.get_names()}
            if not {"pred_score", "anomaly_map"} <= outputs.keys():
                raise ValueError(f"Missing model outputs for {key}")
            request = compiled.create_infer_request()
            for _ in range(2):
                request.infer({0: np.zeros(shape, np.float32)})
            self.models[key] = (entry, compiled, request, shape, outputs)
        return list(self.models)

    def score(self, image, part_type, pose, view, background):
        key = group_key(part_type, pose, view, background)
        loaded = self.models.get(key)
        if loaded is None:
            return Score("missing", detail=f"No calibrated model: {key}")
        entry, compiled, request, shape, outputs = loaded
        t0 = time.perf_counter()
        try:
            image = rgb_image(image).resize((shape[3], shape[2]), Image.Resampling.BILINEAR)
            x = np.ascontiguousarray(np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255)
            request.infer({0: x})
            score = float(request.get_tensor(outputs["pred_score"]).data.reshape(-1)[0])
            amap = request.get_tensor(outputs["anomaly_map"]).data.squeeze().copy()
            ms = (time.perf_counter() - t0) * 1000
            if not math.isfinite(score) or amap.ndim != 2 or amap.size == 0 or not np.isfinite(amap).all():
                return Score("invalid", ms=ms, detail="Nonfinite score/map, empty map or invalid map shape")
            return Score("ok", score, entry["threshold"], ms, amap)
        except Exception as e:
            return Score("error", ms=(time.perf_counter() - t0) * 1000, detail=f"{type(e).__name__}: {e}")
