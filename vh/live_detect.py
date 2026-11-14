"""Cheap detectors for the dashboard's idle preview (run in the dashboard process, never in the loop).

- wrist(): parts in the wrist frame -> boxes + world xy (ray ∩ table plane), using the same
  local-contrast detector as sort.py. Preview does not evaluate hand clearance.
- overhead(): for mapping the secondary-capture pose: the held part (saturated zinc/tape blue) in the
  overhead frame: where, how big, how sharp, how bright, how much tape-blue; plus the dark claws.
"""

import io

import numpy as np
from PIL import Image
from scipy import ndimage

from . import config as C

try:
    import cv2
except ImportError:
    cv2 = None


def wrist(jpeg, T=None, intr=None):
    # Use the SAME local-contrast part detector as sort.py, not the old white-table
    # saturation mask (which merged cardboard with the part and called it a hand).
    # Preview overlays are not a hand/safety detector. The running loop owns its hand check.
    import math
    from .detection import detect
    rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    out = []
    for u, v, area, yaw, bbox in detect(rgb, None, None):
        angle = math.radians(yaw)
        half = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 2
        dx, dy = math.cos(angle) * half, math.sin(angle) * half
        ov = {"bbox": list(bbox), "c": [u, v], "axis": [u-dx, v-dy, u+dx, v+dy], "area": area}
        if T is not None and intr is not None:
            p = T.ray_to_plane(intr.rays(u, v), C.TABLE_Z)
            if T.t[2] > p[2]:
                ov["xy"] = [round(float(p[0]), 1), round(float(p[1]), 1)]
        out.append(ov)
    return {"items": out, "hand": None, "hand_status": "not_evaluated", "detector": "vh.detection.detect"}


def _sharpness(gray):
    """Variance of the Laplacian: higher = sharper (compare frames from the same camera only)."""
    if gray.size < 100:
        return 0.0
    if cv2 is not None:
        return float(cv2.Laplacian(gray, cv2.CV_32F).var())
    return float(ndimage.laplace(gray.astype(np.float32)).var())


def overhead(jpeg):
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    full = np.asarray(im)
    h, w = full.shape[:2]
    f = full[::2, ::2].astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx, mn = f.max(2), f.min(2)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    # measured on overview-cam frames: zinc sat 0.2-0.3, b-r ~0.15; table/ceiling/arm sat <= 0.05, b-r <= 0.02;
    # skin b-r < 0. Shiny stainless/grey highlights are colorless and are missed (tape is what matters here).
    bluish = (sat > 0.15) & (b >= r + 0.08) & (b >= g - 0.05) & (mx > 0.15)
    tape = bluish & (b > g + 0.10) & (sat > 0.40)                             # deeper, more saturated than zinc
    bluish = ndimage.binary_closing(ndimage.binary_opening(bluish, iterations=1), iterations=2)
    lab, n = ndimage.label(bluish)
    gray = np.asarray(im.convert("L"))
    parts = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        area = int((lab[sl] == i).sum()) * 4
        if area < 80:
            continue
        roi = gray[sl[0].start * 2:sl[0].stop * 2, sl[1].start * 2:sl[1].stop * 2].astype(np.float32)
        if np.abs(np.diff(roi, axis=1)).mean() < 6:     # flat tinted surfaces (shadowed walls): parts have edges/threads
            continue
        parts.append({"bbox": [sl[1].start * 2, sl[0].start * 2, sl[1].stop * 2, sl[0].stop * 2], "area": area,
                      "tape": round(float(tape[sl][lab[sl] == i].mean()), 3)})
    parts.sort(key=lambda p: -p["area"])
    parts = parts[:4]
    dark = gray[::2, ::2] < 45
    dlab, _ = ndimage.label(ndimage.binary_opening(dark, iterations=1))
    claws = None
    sizes = ndimage.sum(dark, dlab, range(1, dlab.max() + 1)) if dlab.max() else []
    if len(sizes):
        k = int(np.argmax(sizes)) + 1
        if sizes[k - 1] * 4 >= 800:
            sl = ndimage.find_objects(dlab)[k - 1]
            claws = [sl[1].start * 2, sl[0].start * 2, sl[1].stop * 2, sl[0].stop * 2]
    res = {"w": w, "h": h, "bright": round(float(gray.mean()), 1), "clipped": round(float((gray > 250).mean() * 100), 2),
           "sharp_frame": round(_sharpness(gray), 1), "parts": parts, "claws": claws}
    if parts:
        x0, y0, x1, y1 = parts[0]["bbox"]
        pad = 6
        roi = gray[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad]
        res.update(part_sharp=round(_sharpness(roi), 1), part_bright=round(float(roi.mean()), 1),
                   part_px=max(x1 - x0, y1 - y0), part_center_off=[round((x0 + x1) / 2 - w / 2), round((y0 + y1) / 2 - h / 2)])
    return res
