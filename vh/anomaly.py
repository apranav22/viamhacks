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

CROP_POLICY = "part-top-v2"          # new bundles: top view = part_crop (rotated, masked); webcam = context_crop
CROP_POLICIES = {"square-context-v1", "part-top-v2"}


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


def part_crop(image, bbox, out=320, pad_px=14, grey=(128, 128, 128)):
    """Top view v2: the part only, rotated to a canonical pose, background set to grey, square and padded.

    Foreground = pixels far in colour from the local background (median of the region's border), largest component.
    Long axis horizontal; the wider end (head) on the LEFT; part scaled to fill `out` minus padding. Tape, marks and
    any other colour change on the part stay in the foreground, so they fill far more of the model input than in the
    square context crop, and the part's angle, position and the cardboard texture no longer vary between picks.
    Returns (crop, info). Raises ValueError when no plausible part is found.
    """
    from scipy import ndimage
    img = rgb_image(image)
    w, h = img.size
    x0, y0, x1, y1 = map(int, bbox)
    m = int(0.25 * max(x1 - x0, y1 - y0)) + 10
    X0, Y0, X1, Y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
    a = np.asarray(img.crop((X0, Y0, X1, Y1)), dtype=np.float32)
    border = np.concatenate([a[:4].reshape(-1, 3), a[-4:].reshape(-1, 3), a[:, :4].reshape(-1, 3), a[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    # Foreground = not cardboard-coloured. Cardboard (lit or in shadow) keeps its orange chromaticity (r-b)/sum ~0.15;
    # zinc, stainless and blue tape sit at <= ~0.03. A brightness difference alone also picked up the LED's light/dark
    # gradient across the pad (whole patches of cardboard in the mask).
    chroma = (a[..., 0] - a[..., 2]) / np.maximum(a.sum(-1), 1)
    bch = np.concatenate([chroma[:4].ravel(), chroma[-4:].ravel(), chroma[:, :4].ravel(), chroma[:, -4:].ravel()])
    bg_chroma = max(float(np.percentile(bch, 75)), 0.08)    # cardboard part of the border (it may include white table)
    # ...and different from the smooth local background (the LED leaves pale, low-chroma cardboard patches that are
    # smooth; the part is not). Background = heavy blur at quarter resolution.
    sig = max(8.0, 0.35 * max(x1 - x0, y1 - y0)) / 4
    small = ndimage.gaussian_filter(a[::4, ::4], sigma=(sig, sig, 0))
    blur = np.repeat(np.repeat(small, 4, 0), 4, 1)[:a.shape[0], :a.shape[1]]
    local = ndimage.binary_dilation(np.abs(a - blur).sum(-1) > 45, iterations=4)
    fg = (chroma < 0.3 * bg_chroma) & local
    fg = ndimage.binary_closing(ndimage.binary_opening(fg, iterations=1), iterations=3)
    lab, n = ndimage.label(fg)
    if n == 0:
        raise ValueError("part_crop: no foreground")
    # the component that overlaps the detector's bbox most (white table / seams at the region edge are not the part)
    inside = np.zeros_like(fg)
    inside[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
    overlap = ndimage.sum(inside, lab, range(1, n + 1))
    fg = ndimage.binary_fill_holes(lab == (1 + int(np.argmax(overlap))))
    ys, xs = np.nonzero(fg)
    if len(xs) < 200:
        raise ValueError("part_crop: part too small")
    cx, cy = xs.mean(), ys.mean()
    evals, evecs = np.linalg.eigh(np.cov(np.stack([xs - cx, ys - cy])))
    ax = evecs[:, np.argmax(evals)]
    ang = math.degrees(math.atan2(ax[1], ax[0]))
    # rotate image + mask so the long axis is horizontal (PIL rotates counter-clockwise for positive angles)
    pil = Image.fromarray(a.astype(np.uint8))
    mk = Image.fromarray((fg * 255).astype(np.uint8))
    rot = pil.rotate(ang, resample=Image.Resampling.BILINEAR, center=(cx, cy), expand=False, fillcolor=tuple(int(v) for v in bg))
    rmk = np.asarray(mk.rotate(ang, resample=Image.Resampling.NEAREST, center=(cx, cy), expand=False)) > 127
    ys, xs = np.nonzero(rmk)
    if len(xs) == 0:
        raise ValueError("part_crop: mask lost in rotation")
    bx0, bx1, by0, by1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    r = np.asarray(rot, dtype=np.uint8).copy()
    r[~ndimage.binary_dilation(rmk, iterations=2)] = grey
    r = r[by0:by1, bx0:bx1]
    msk = rmk[by0:by1, bx0:bx1]
    widths = msk.sum(0)
    third = max(1, len(widths) // 3)
    flipped = widths[-third:].mean() > widths[:third].mean()
    if flipped:                                   # head (wider end) to the left
        r, msk = r[:, ::-1], msk[:, ::-1]
    ph, pw = r.shape[:2]
    scale = (out - 2 * pad_px) / max(ph, pw)
    part = Image.fromarray(np.ascontiguousarray(r)).resize((max(1, round(pw * scale)), max(1, round(ph * scale))),
                                                           Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (out, out), grey)
    canvas.paste(part, ((out - part.width) // 2, (out - part.height) // 2))
    info = {"angle_deg": round(ang, 1), "flipped": bool(flipped), "part_px": int(fg.sum()),
            "length_px": int(bx1 - bx0), "width_px": int(by1 - by0), "scale": round(scale, 4),
            "region": [X0, Y0, X1, Y1]}
    return canvas, info


def model_crop(image, bbox, view, policy=CROP_POLICY):
    """The ONE crop function for training and live inference. Returns (crop, box_for_display)."""
    if policy == "part-top-v2" and view == "top":
        crop, info = part_crop(image, bbox)
        return crop, list(info["region"])
    return context_crop(image, bbox)


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
    # type auto: a part whose size is this far (robust units, config/part_sizes.json) from every known type is
    # UNKNOWN -> no model -> rejected as uncertain. In-type distances of good picks: median ~1.5, p95 ~4.
    UNKNOWN_SIZE_DIST = 6.0

    def __init__(self, bundle, device="CPU", sizes=None, type_clf=None):
        self.path = Path(bundle)
        self.sizes = {k: v for k, v in (json.loads(Path(sizes).read_text()) if sizes else {}).items()
                      if not k.startswith("_")}
        self.last_size, self.last_type, self.last_how = None, None, None
        self.manifest = json.loads(self.path.read_text())
        self.policy = self.manifest.get("crop_policy")
        if self.manifest.get("schema") != 1 or self.policy not in CROP_POLICIES:
            raise ValueError("Unsupported anomaly bundle/crop policy")
        if device.upper() not in {"CPU", "GPU", "NPU"}:
            raise ValueError("Select one explicit inference device")
        import openvino as ov
        self.core = ov.Core()
        self.device = device.upper()
        self.models = {}
        # type auto: ResNet-18 type classifier (vh/type_clf.py) picks the type; the size gate below still decides UNKNOWN.
        self.type_clf = None
        if type_clf:
            from vh.type_clf import TypeClassifier
            self.type_clf = TypeClassifier(type_clf, self.device, self.core)

    def warm(self, part_type, background):
        """Load only the requested type/background; a missing view remains explicitly unavailable."""
        self.part_type = part_type
        for key, entry in self.manifest["models"].items():
            # part_type "auto": every per-type bank; score() keeps the type whose normal bank fits best
            if (part_type != "auto" and entry["part_type"] != part_type) or entry["background"] != background:
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

    def crop(self, image, bbox, view, mm_per_px=None):
        """Model crop; for the top view with mm_per_px also measures the part (length, width, sqrt area in mm)."""
        if view == "top" and self.policy == "part-top-v2":
            crop, info = part_crop(image, bbox)
            self.last_size = ([info["length_px"] * mm_per_px, info["width_px"] * mm_per_px,
                               info["part_px"] ** 0.5 * mm_per_px] if mm_per_px else None)
            return crop, list(info["region"])
        return model_crop(image, bbox, view, self.policy)

    def size_type(self):
        """(type, distance) of the known type nearest to the last measured top-view size, or (None, inf)."""
        loaded = {e["part_type"] for e, *_ in self.models.values()}
        best = (None, float("inf"))
        for ty, s in self.sizes.items():
            if ty not in loaded or not self.last_size:
                continue
            d = math.sqrt(sum(((x - m) / sp) ** 2 for x, m, sp in zip(self.last_size, s["median"], s["spread"])))
            if d < best[1]:
                best = (ty, d)
        return best

    def score(self, image, part_type, pose, view, background):
        if part_type == "auto" and self.sizes and (view != "top" or self.last_size):
            # Type from the measured size at the top view (fixed 190 mm look: mm are repeatable); webcam views reuse it.
            if view == "top":
                ty, dist = self.size_type()
                self.last_type = ty if dist <= self.UNKNOWN_SIZE_DIST else None
                if self.last_type is None:
                    return Score("unknown_type", detail=f"size {[round(v, 1) for v in self.last_size]} mm matches no known "
                                                        f"type (nearest {ty}, distance {dist:.1f})")
                self.last_how = "by size"
                if self.type_clf is not None:
                    loaded = {e["part_type"] for e, *_ in self.models.values()} & set(self.type_clf.classes)
                    try:
                        cty, p = self.type_clf.predict(rgb_image(image), allowed=loaded)
                        self.last_type, self.last_how = cty, f"by classifier p={p:.2f}, size nearest {ty}"
                    except Exception as e:      # classifier failure: keep the size type, say so in the log
                        self.last_how = f"by size; classifier {type(e).__name__}: {e}"
            if self.last_type is None:
                return Score("unknown_type", detail="no part type from the top view")
            r = self.score(image, self.last_type, pose, view, background)
            r.detail = f"type {self.last_type} ({self.last_how})"
            return r
        if part_type == "auto":
            # Unknown part type: score against every type's normal bank, keep the lowest score/threshold. A part that
            # matches no type's normal appearance (defect, or a type never collected) stays above threshold -> reject.
            best = None
            for key, (entry, *_ ) in self.models.items():
                if (entry["pose"], entry["view"], entry["background"]) != (pose, view, background):
                    continue
                r = self.score(image, entry["part_type"], pose, view, background)
                if r.status == "ok" and (best is None or r.score / r.threshold < best.score / best.threshold):
                    best = r
                    best.detail = f"best type {entry['part_type']}"
            return best or Score("missing", detail=f"No calibrated model for auto|{pose}|{view}|{background}")
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
