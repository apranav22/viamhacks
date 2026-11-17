"""Part type from the top-view model crop: ResNet-18 ImageNet features (OpenVINO, explicit device) + a linear head.

Trained by train_type_clf.py on good collect picks. Replaces nearest-size routing for `--type auto`: on held-out runs
it picked the right type 92% of the time vs 70% for the size rule (2026-11-14). The size gate in AnomalyModels stays
in front of it: a part whose size is far from every known type is still UNKNOWN (rejected as uncertain).
Training and runtime share preprocess() and FeatureNet, so the features match exactly.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(3, 1, 1)


def preprocess(img):
    a = np.asarray(img.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR), np.float32) / 255
    return np.ascontiguousarray(((a.transpose(2, 0, 1) - MEAN) / STD)[None])


class FeatureNet:
    """512-d L2-normalised ResNet-18 avgpool features. Explicit device, no fallback (same rule as the anomaly models)."""

    def __init__(self, xml, device="CPU", core=None):
        import openvino as ov
        device = device.upper()
        if device not in {"CPU", "GPU", "NPU"}:
            raise ValueError("Select one explicit inference device")
        core = core or ov.Core()
        cfg = {"PERFORMANCE_HINT": "LATENCY", **({"INFERENCE_PRECISION_HINT": "f32"} if device != "NPU" else {})}
        self.compiled = core.compile_model(core.read_model(str(xml)), device, cfg)
        self.request = self.compiled.create_infer_request()
        self.request.infer({0: np.zeros((1, 3, SIZE, SIZE), np.float32)})     # warm before any motion

    def __call__(self, img):
        self.request.infer({0: preprocess(img)})
        f = np.asarray(self.request.get_output_tensor(0).data, dtype=np.float64).reshape(-1)
        return f / max(float(np.linalg.norm(f)), 1e-12)


def head_probs(feat, head, allowed=None):
    """Softmax of the standardised linear head; classes outside `allowed` get probability 0."""
    z = (np.asarray(feat, dtype=np.float64) - np.asarray(head["scaler_mean"])) / np.asarray(head["scaler_scale"])
    logit = np.asarray(head["coef"]) @ z + np.asarray(head["intercept"])
    if allowed is not None:
        keep = np.array([c in allowed for c in head["classes"]])
        if not keep.any():
            raise ValueError("no allowed class in the type classifier")
        logit = np.where(keep, logit, -np.inf)
    p = np.exp(logit - logit.max())
    p /= p.sum()
    return dict(zip(head["classes"], p.tolist()))


class TypeClassifier:
    def __init__(self, path, device="CPU", core=None):
        self.path = Path(path)
        self.head = json.loads(self.path.read_text())
        if self.head.get("schema") != 1:
            raise ValueError(f"Unsupported type classifier: {self.path}")
        self.classes = list(self.head["classes"])
        self.net = FeatureNet(self.path.parent / self.head["feature_xml"], device, core)

    def predict(self, img, allowed=None):
        """(type, probability) among `allowed` types (e.g. the types with a loaded anomaly bank)."""
        p = head_probs(self.net(img), self.head, allowed)
        ty = max(p, key=p.get)
        return ty, p[ty]
