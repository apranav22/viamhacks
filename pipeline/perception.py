"""Find the one item on the table, measure it, decide how to grasp it. Pure numpy/scipy, a few ms per frame.

- `segment`: not-white-table pixels (saturation or darkness), minus anything already in the empty-table
  reference frame (laptops, fixtures), minus fixed masks (the gripper finger).
- `watch`: from the watch pose, is there an item, and is a hand still in view?
- `Placement`: the item has been in the same place for STABLE_FRAMES frames -> "placed".
- `measure`: from the hover pose, color + depth -> world center, top height, long-axis yaw, length, width.
- `classify` + `grasp_for`: a shape class (not a fastener name) and its grasp recipe.
"""

import io
import math
import struct
from dataclasses import asdict, dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage

from . import config as C

try:                                    # optional: 10x faster morphology; scipy gives the same result without it
    import cv2
    _K = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
except ImportError:
    cv2 = None


# --- decoding ---------------------------------------------------------------------------------

def decode_color(jpeg_bytes, scale=1):
    """JPEG -> RGB uint8. scale=2 decodes at half resolution inside the JPEG decoder (DCT scaling), ~3x cheaper."""
    im = Image.open(io.BytesIO(jpeg_bytes))
    im.draft("RGB", (im.size[0] // scale, im.size[1] // scale))
    im = im.convert("RGB")
    if scale > 1 and im.size[0] != 640 // scale:
        im = im.resize((im.size[0] // scale, im.size[1] // scale))
    return np.asarray(im)


def decode_depth(raw):
    """Viam raw depth (image/vnd.viam.dep): b'DEPTHMAP' + uint64 BE width, height + uint16 BE mm."""
    if raw[:8] != b"DEPTHMAP":
        raise ValueError("not a viam depth map")
    w, h = struct.unpack(">QQ", raw[8:24])
    return np.frombuffer(raw[24:24 + 2 * w * h], dtype=">u2").reshape(h, w).astype(np.float32)


# --- segmentation ------------------------------------------------------------------------------

def segment(rgb, ref=None, masks=(), scale=1):
    """Foreground mask at the resolution of `rgb` (pass scale=2 for a half-resolution image;
    `masks` stay in full-resolution pixels)."""
    f = rgb.astype(np.float32) * (1.0 / 255.0)
    mx, mn = f.max(2), f.min(2)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    fg = (sat > C.SAT_MIN) | (mx < np.median(mx[::4, ::4]) - C.DARK_DELTA)
    if ref is not None:
        fg &= np.abs(f - ref).max(2) > C.REF_DIFF
    for x0, y0, x1, y1 in masks:
        fg[y0 // scale:(y1 + scale - 1) // scale, x0 // scale:(x1 + scale - 1) // scale] = False
    if cv2 is not None:
        u8 = cv2.morphologyEx(fg.view(np.uint8), cv2.MORPH_OPEN, _K)
        return cv2.morphologyEx(u8, cv2.MORPH_CLOSE, _K, iterations=2).view(bool)
    fg = ndimage.binary_opening(fg, iterations=1)
    return ndimage.binary_closing(fg, iterations=2)


@dataclass
class Blob:
    area: int
    bbox: list            # [x0, y0, x1, y1] px
    centroid: list        # [u, v] px
    axis: list            # unit major axis in px [du, dv]
    sigma: list           # std dev along major, minor (px)
    touches_border: bool
    ys: np.ndarray = field(repr=False, default=None)
    xs: np.ndarray = field(repr=False, default=None)

    def overlay(self):
        """What the dashboard draws: bbox, centroid, major axis segment (no pixels, no image encoding)."""
        u, v = self.centroid
        du, dv = self.axis
        L = 2.0 * self.sigma[0]
        return {"bbox": self.bbox, "c": [round(u, 1), round(v, 1)],
                "axis": [round(u - du * L, 1), round(v - dv * L, 1), round(u + du * L, 1), round(v + dv * L, 1)],
                "area": self.area, "border": self.touches_border}


def blobs(fg, scale=1):
    """Connected components, reported in full-resolution pixels whatever the mask's scale."""
    lab, n = ndimage.label(fg)
    h, w = fg.shape
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = np.nonzero(lab[sl] == i)
        if len(xs) * scale * scale < 20:
            continue
        ys = (ys + sl[0].start) * scale + scale // 2
        xs = (xs + sl[1].start) * scale + scale // 2
        u, v = float(xs.mean()), float(ys.mean())
        cov = np.cov(np.stack([xs - u, ys - v])) if len(xs) > 2 else np.eye(2)
        ev, evec = np.linalg.eigh(cov)
        out.append(Blob(area=int(len(xs)) * scale * scale, bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                        centroid=[u, v], axis=[float(evec[0, 1]), float(evec[1, 1])],
                        sigma=[float(math.sqrt(max(ev[1], 0))), float(math.sqrt(max(ev[0], 0)))],
                        touches_border=sl[0].start == 0 or sl[1].start == 0 or sl[0].stop >= h or sl[1].stop >= w,
                        ys=ys, xs=xs))
    return sorted(out, key=lambda b: -b.area)


@dataclass
class WatchResult:
    item: Blob = None
    hand: bool = False
    n_blobs: int = 0


WATCH_SCALE = 2   # the watch loop runs at half resolution (~2 mm/px at home): enough to notice an item


def watch(rgb, ref=None, masks=None, scale=WATCH_SCALE):
    fg = segment(rgb, ref, C.MASK_RECTS if masks is None else masks, scale)
    bs = blobs(fg, scale)
    hand = any(b.touches_border and b.area >= C.HAND_PX for b in bs)
    items = [b for b in bs if not b.touches_border and C.MIN_ITEM_PX_WATCH <= b.area <= C.MAX_ITEM_PX_WATCH]
    return WatchResult(item=items[0] if items else None, hand=hand, n_blobs=len(bs))


class Placement:
    """'Placed' = an item, no hand, centroid steady for STABLE_FRAMES frames. Tracks when it first appeared."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.t_appeared = None
        self.history = []

    def update(self, t, res: WatchResult):
        if res.item is None and not res.hand:
            self.reset()
            return False
        if self.t_appeared is None:
            self.t_appeared = t          # first frame where an item (or the hand bringing it) showed up
        if res.item is None or res.hand:
            self.history = []
            return False
        self.history.append(res.item.centroid)
        self.history = self.history[-C.STABLE_FRAMES:]
        if len(self.history) < C.STABLE_FRAMES:
            return False
        c = np.array(self.history)
        return float(np.linalg.norm(c - c[-1], axis=1).max()) <= C.STABLE_PX


# --- measurement at the hover pose ---------------------------------------------------------------

@dataclass
class Measurement:
    x: float
    y: float
    top_z: float
    height: float
    yaw_long: float         # world heading of the long axis, degrees in [-90, 90)
    length: float
    width: float
    depth_frac: float       # fraction of item pixels with valid depth
    mm_per_px: float


def _yaw180(a):
    return (a + 90.0) % 180.0 - 90.0


def measure(blob: Blob, depth, intr, T, table_z=None):
    table_z = C.TABLE_Z if table_z is None else table_z
    us, vs = blob.xs.astype(np.float32), blob.ys.astype(np.float32)
    rays = intr.rays(us, vs)
    d = depth[blob.ys, blob.xs] if depth is not None else np.zeros(len(us), np.float32)
    ok = d > 0
    if ok.sum() >= 15:
        pts = T.point(rays[ok] * d[ok, None])
    else:                                    # no depth: intersect with the table plane
        pts = T.ray_to_plane(rays, table_z)
    top = float(np.percentile(pts[:, 2], 95))
    height = max(top - table_z, 0.0)
    upper = pts[pts[:, 2] >= table_z + 0.5 * height] if height > 3 else pts
    upper = upper if len(upper) >= 10 else pts
    xy = pts[:, :2] - pts[:, :2].mean(0)
    ev, evec = np.linalg.eigh(np.cov(xy.T))
    major, minor = evec[:, 1], evec[:, 0]
    pa, pb = xy @ major, xy @ minor
    length = float(np.percentile(pa, 98) - np.percentile(pa, 2))
    width = float(np.percentile(pb, 98) - np.percentile(pb, 2))
    yaw = _yaw180(math.degrees(math.atan2(major[1], major[0])))
    mm_per_px = length / max(4 * blob.sigma[0], 1e-6)
    return Measurement(x=float(np.median(upper[:, 0])), y=float(np.median(upper[:, 1])), top_z=top, height=height,
                       yaw_long=yaw, length=length, width=width, depth_frac=float(ok.mean()), mm_per_px=mm_per_px)


def plane_xy(blob: Blob, intr, T, table_z=None):
    """Watch-pose estimate: the blob centroid's ray hits the table plane."""
    p = T.ray_to_plane(intr.rays(*blob.centroid), C.TABLE_Z if table_z is None else table_z)
    return float(p[0]), float(p[1])


# --- shape class and grasp recipe -------------------------------------------------------------

SHAPES = {
    "upright": "standing bolt: grip the shank ~15 mm below its top",
    "lying_long": "lying bolt/screw: jaws across the shank at the center",
    "thin_screw": "thin screw lying: jaws across, fingertips near the table, slow",
    "nut_flat": "nut lying flat: jaws across the flats at half height",
    "nut_edge": "nut on its edge: jaws across its faces",
    "flat_thin": "washer-like: too flat for a two-finger top grasp",
    "unknown": "odd shape: generic grasp across the narrow side; suspicious",
}


def classify(m: Measurement):
    aspect = m.length / max(m.width, 1e-6)
    if m.height >= 25 and m.length < 35:
        return "upright"
    if m.height <= 3.5:
        return "flat_thin"
    if aspect >= 2.0:
        return "thin_screw" if m.height <= 7 else "lying_long"
    if aspect < 1.4 and m.height <= 14:
        return "nut_flat"
    if aspect >= 1.4 and 12 <= m.height <= 24:
        return "nut_edge"
    return "unknown"


@dataclass
class Grasp:
    shape: str
    x: float
    y: float
    tip_z: float            # fingertip height in the world
    jaw_heading: float      # world heading the jaws close along (degrees)
    expected_width: float   # mm between the jaws when holding
    ok: bool = True
    reason: str = ""

    def to_dict(self):
        return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def grasp_for(m: Measurement, shape=None, table_z=None):
    table_z = C.TABLE_Z if table_z is None else table_z
    shape = shape or classify(m)
    floor = table_z + C.MIN_TIP_CLEARANCE
    across = m.yaw_long + 90.0                        # jaws close across the long axis
    if shape == "upright":
        g = Grasp(shape, m.x, m.y, max(m.top_z - 15.0, floor), across, m.width)
    elif shape == "flat_thin":
        g = Grasp(shape, m.x, m.y, floor, across, m.width, ok=False, reason="too flat for a top-down two-finger grasp")
    elif shape == "nut_flat":
        g = Grasp(shape, m.x, m.y, max(table_z + m.height / 2, floor), across, m.width)
    else:                                             # lying_long, thin_screw, nut_edge, unknown
        g = Grasp(shape, m.x, m.y, max(m.top_z - m.height / 2, floor), across, m.width)
    if g.ok and g.expected_width > 75:
        g.ok, g.reason = False, f"too wide for the jaws ({g.expected_width:.0f} mm)"
    lo_x, hi_x = C.WORKSPACE["x"]
    lo_y, hi_y = C.WORKSPACE["y"]
    if g.ok and not (lo_x <= g.x <= hi_x and lo_y <= g.y <= hi_y):
        g.ok, g.reason = False, f"outside the workspace ({g.x:.0f}, {g.y:.0f})"
    return g
