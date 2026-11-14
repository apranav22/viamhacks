"""Local-contrast part detection shared by the live sorter and dashboard preview."""
import math

import numpy as np
from scipy import ndimage

# Pixel constants below were tuned on the 640x480 wrist stream at the watch pose (~0.77 mm/px on the table).
# detect() scales lengths by REF_MM_PER_PX / (this frame's mm/px) and areas by its square, so they hold at any
# resolution AND height: at the 220 mm look pose (0.24 mm/px) parts are ~3x bigger in pixels, and an unscaled
# background blur absorbed the zinc threads (17:25 smoke run: only the bolt head detected). Without a view (no
# pose known) only the resolution is scaled (frame height / 480).
CALIB_HEIGHT_PX = 480
REF_MM_PER_PX = 0.77
COLOR_DIFF = 70           # summed RGB distance from the local background that counts as a part
BACKGROUND_SIGMA_PX = 25  # wider than a part at the survey scale
MIN_PIXELS, MAX_PIXELS = 40, 12000
PART_Z_ABOVE_TABLE = 4    # rays are cut at about half a fastener's height
EDGE_MARGIN_PX = 4        # opening/closing shave the border, so "touches the edge" needs a margin


class WristView:
    """Pixel -> world on the table plane for the wrist cam at a fixed arm pose."""

    def __init__(self, k, rot, t, table_z):
        self.k, self.rot, self.t, self.table_z = k, rot, t, table_z

    def to_world(self, u, v, z=None) -> tuple:
        z = self.table_z + PART_Z_ABOVE_TABLE if z is None else z
        d = self.rot @ np.array([(u - self.k.center_x_px) / self.k.focal_x_px,
                                 (v - self.k.center_y_px) / self.k.focal_y_px, 1.0])
        s = (z - self.t[2]) / d[2]
        return float(self.t[0] + s * d[0]), float(self.t[1] + s * d[1])


def detect(rgb, view: WristView | None, region: dict | None) -> list:
    """Parts on the white table: [(x, y, pixels, yaw_deg, bbox)]. World mm with a view, else pixels."""
    f = rgb.astype(np.float32)
    if view is not None:
        s = REF_MM_PER_PX / ((view.t[2] - view.table_z) / view.k.focal_x_px)
    else:
        s = rgb.shape[0] / CALIB_HEIGHT_PX
    sigma = BACKGROUND_SIGMA_PX * s / 4
    # the background is smooth, so blur at quarter resolution and scale back up (~10x faster)
    small = ndimage.gaussian_filter(f[::4, ::4], sigma=(sigma, sigma, 0))
    background = np.repeat(np.repeat(small, 4, axis=0), 4, axis=1)[:f.shape[0], :f.shape[1]]
    mask = ndimage.binary_opening(np.abs(f - background).sum(axis=-1) > COLOR_DIFF, iterations=1)
    mask = ndimage.binary_closing(mask, iterations=2)  # shiny parts break into pieces
    labels, n = ndimage.label(mask)
    h, w = mask.shape
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        ys, xs = np.nonzero(labels[sl] == i)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        if not MIN_PIXELS * s * s <= len(xs) <= MAX_PIXELS * s * s:
            continue
        m = round(EDGE_MARGIN_PX * s)
        if xs.min() < m or ys.min() < m or xs.max() >= w - m or ys.max() >= h - m:
            continue  # cut by the frame edge: the gripper finger (always at the bottom), hands, clutter.
                      # Not by darkness: a dark stainless screw (gray 54) is as dark as the finger (53)
        u, v = float(xs.mean()), float(ys.mean())
        evals, evecs = np.linalg.eigh(np.cov(np.stack([xs, ys])))
        a = evecs[:, np.argmax(evals)]
        if view is None:
            x, y = u, v
            yaw = math.degrees(math.atan2(a[1], a[0]))
        else:
            x, y = view.to_world(u, v)
            x2, y2 = view.to_world(u + 10 * a[0], v + 10 * a[1])
            yaw = math.degrees(math.atan2(y2 - y, x2 - x))
            if region and not (region["x_min"] < x < region["x_max"] and region["y_min"] < y < region["y_max"]):
                continue
        out.append((x, y, len(xs), yaw, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))))
    return out
