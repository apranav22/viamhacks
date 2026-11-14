"""Read-only legacy depth scan and reference-service diagnostics.

Used by calibration tools; live sorting uses vh.detection and the recorded surface.
"""
import asyncio
import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage
from viam.components.camera import Camera
from viam.services.vision import Vision

from .motion import cam_to_world

ITEM_MIN_HEIGHT_MM = 6
ITEM_MAX_HEIGHT_MM = 80
ITEM_MIN_PIXELS = 150
ITEM_MAX_PIXELS = 12000
COLOR_DIFF = 70
BACKGROUND_SIGMA_PX = 25

@dataclass
class Item:
    x: float
    y: float
    top_z: float
    yaw_deg: float
    bbox: tuple  # pixel (x0, y0, x1, y1)
    pixels: int



@dataclass
class Scan:
    color: Image.Image
    table_z: float
    items: list



async def scan(machine, cam: Camera, region: dict) -> Scan:
    images, _ = await cam.get_images()
    color = next(i for i in images if i.name == "color")
    depth = np.asarray(next(i for i in images if i.name == "depth").bytes_to_depth_array(), dtype=float)
    k = (await cam.get_properties()).intrinsic_parameters
    rot, t = await cam_to_world(machine)

    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w), np.arange(h))
    cam_pts = np.stack([(u - k.center_x_px) * depth / k.focal_x_px,
                        (v - k.center_y_px) * depth / k.focal_y_px, depth], axis=-1)
    world = cam_pts @ rot.T + t
    valid = depth > 0
    in_region = (valid & (world[..., 0] > region["x_min"]) & (world[..., 0] < region["x_max"])
                 & (world[..., 1] > region["y_min"]) & (world[..., 1] < region["y_max"]))
    table_z = float(np.median(world[..., 2][in_region]))

    img = Image.open(io.BytesIO(color.data)).convert("RGB")
    rgb = np.asarray(img.resize((w, h)), dtype=float)
    # compare against a blurred copy, not one table colour, so lighting gradients and soft
    # shadows across the table don't count as items
    background = ndimage.gaussian_filter(rgb, sigma=(BACKGROUND_SIGMA_PX, BACKGROUND_SIGMA_PX, 0))
    by_color = np.abs(rgb - background).sum(axis=-1) > COLOR_DIFF
    mask = in_region & ((world[..., 2] > table_z + ITEM_MIN_HEIGHT_MM) | by_color)
    mask = ndimage.binary_opening(mask, iterations=2)
    labels, n = ndimage.label(mask)
    items = []
    for i in range(1, n + 1):
        blob = labels == i
        if not ITEM_MIN_PIXELS <= blob.sum() <= ITEM_MAX_PIXELS:
            continue
        p = world[blob & valid]
        if len(p) < ITEM_MIN_PIXELS / 2:
            continue
        height = np.percentile(p[:, 2], 90) - table_z
        # depth noise makes table-coloured patches a few mm "tall"; real parts differ in colour or stand clear
        if height > ITEM_MAX_HEIGHT_MM or (by_color[blob].mean() < 0.3 and height < 15):
            continue
        xy = p[:, :2] - p[:, :2].mean(axis=0)
        evals, evecs = np.linalg.eigh(np.cov(xy.T))
        long_axis = evecs[:, np.argmax(evals)]
        ys, xs = np.nonzero(blob)
        items.append(Item(x=float(p[:, 0].mean()), y=float(p[:, 1].mean()),
                          top_z=float(np.percentile(p[:, 2], 90)),
                          yaw_deg=math.degrees(math.atan2(long_axis[1], long_axis[0])),
                          bbox=(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
                          pixels=int(blob.sum())))
    items.sort(key=lambda it: -it.pixels)
    out = Scan(color=img, table_z=table_z, items=items)
    out.jpeg, out.rot, out.t, out.k = color.data, rot, t, k   # for the dashboard (vh/probe_tel.py)
    return out



async def classify(anomaly: Vision | None) -> tuple:
    """(anomaly score 0-1, number of anomaly boxes), or (None, 0) without the anomaly service."""
    if anomaly is None:
        return None, 0
    # capture_all_from_camera crashes viam-server (nil pointer) with anomalib 0.1.5, so use the
    # separate calls
    classifications, detections = await asyncio.gather(
        anomaly.get_classifications_from_camera("cam", 2),
        anomaly.get_detections_from_camera("cam"))
    c = max(classifications, key=lambda c: c.confidence)
    score = c.confidence if c.class_name == "anomalous" else 1 - c.confidence
    return score, len(detections)
