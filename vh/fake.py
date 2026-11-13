"""An offline stand-in for the station: runs the real perception/geometry/state machine/telemetry code
against synthesized frames built from a real watch-pose image. Never connects to anything.

Sequence per cycle: empty table (reference) -> a hand enters with the item -> the item alone.
"""

import asyncio
import io
import time

import numpy as np
from PIL import Image
from scipy import ndimage

from . import config as C
from . import perception as P
from .geometry import Intrinsics, Transform, ov_to_R
from .station import Station

HOME_CAM_T = Transform(ov_to_R(0, 0, -1, -90.0), np.array([368.0, 23.0, 636.0]))   # measured at home
INTR = Intrinsics(605.497, 604.881, 337.550, 247.421, 640, 480)


def _jpeg(a):
    b = io.BytesIO()
    Image.fromarray(a.astype(np.uint8)).save(b, "JPEG", quality=88)
    return b.getvalue()


def _depth_bytes(d):
    h, w = d.shape
    return b"DEPTHMAP" + np.array([w, h], ">u8").tobytes() + d.astype(">u2").tobytes()


class FakeStation(Station):
    def __init__(self, tel, image):
        super().__init__(tel, dry_run=True)
        self.image = image
        self.i = 0

    async def connect(self):
        base = P.decode_color(open(self.image, "rb").read()).astype(np.float32)
        fg = ndimage.binary_dilation(P.segment(base.astype(np.uint8), None, C.MASK_RECTS), iterations=3)
        w = (~fg).astype(np.float32)
        bg = np.stack([ndimage.gaussian_filter(base[..., c] * w, 25) / np.maximum(ndimage.gaussian_filter(w, 25), 1e-3)
                       for c in range(3)], -1)
        bg = np.where(fg[..., None], bg, base)
        items = [b for b in P.blobs(P.segment(base.astype(np.uint8), None, C.MASK_RECTS))
                 if not b.touches_border and 500 <= b.area <= 2500]
        item = items[0]
        mask = np.zeros(fg.shape, bool)
        mask[item.ys, item.xs] = True
        mask = ndimage.binary_dilation(mask, iterations=2)
        with_item = np.where(mask[..., None], base, bg)
        hand = with_item.copy()
        hand[150:330, 470:640] = [150, 95, 75]          # a "hand" reaching in from the right edge
        self.frames = {"empty": _jpeg(bg), "hand": _jpeg(hand), "item": _jpeg(with_item)}
        depth = np.full(fg.shape, 640.0, np.float32)
        depth[mask] = 628.0                              # a 12 mm tall part
        self.depth = _depth_bytes(depth)
        self.intr, self.home_deg = INTR, [0.0, 22.6, -50.7, 0.0, -74.0, 0.0]
        self.tel.emit("connected", ms=0, dry_run=True, intrinsics=INTR.__dict__, home_deg=self.home_deg, fake=True)
        return self

    async def close(self):
        pass

    async def frame(self, depth=False):
        await asyncio.sleep(0.03)                        # ~a local camera call on the station
        t = time.time()
        self.i += 1
        name = "empty" if self.i <= 3 else "hand" if self.i <= 8 else "item"
        return self.frames[name], (self.depth if depth else None), t

    async def cam_transform(self, refresh=False):
        self.cam_pose = type("P", (), {"theta": -90.0})()
        return HOME_CAM_T

    async def gripper_pose(self):
        return None, type("P", (), {"theta": 0.0})()

    async def at_home(self, tol=1.5):
        return True

    async def home(self):
        await super().home()
        self.i = 0                                       # the next cycle starts with an empty table

    async def stop(self):
        self.tel.emit("stopped")
