"""Full-coverage capture poses (2026-11-14 plan): two oblique wrist-cam looks at the part on the pad (each sees about a
third of its circumference past the top), then webcam presentations of the held part that keep the gripper, RealSense
and cable OUT of the background: tilted +-60 deg about the part's long axis, and end-on with the tool pointing down.

Geometry (live frame system, 2026-11-14 10:15): the wrist camera looks along the flange z, its origin at flange
(67.5, -23.1, 17.5) mm. A part held across the jaws lies along the flange x (closing direction = flange y).
Evidence: runs/webcam_bg_20261114_101828 (empty gripper, sheet.jpg), runs/20261114_102114_collect (held hex bolt).
"""
import json
import math
from pathlib import Path

import numpy as np

from vh.kinematics import JOINT_LIMITS, TCP_MM, body_points, frames, flip

ROOT = Path(__file__).resolve().parent.parent
CAM_IN_FLANGE = np.array([67.5, -23.1, 17.5])
OBLIQUE_DEG = 45                 # tilt of the wrist camera about the part's long axis, each side of vertical
OBLIQUE_LENS_MM = (260, 230, 300)  # lens-to-part standoffs, tried in order (260: 116/128 pick-zone samples clear)
WEB_TILT_DEG = 60                # webcam: tool tilted this far about the part axis from pointing at the lens
WEB_ORDER = ["under", "end_a", "end_b"]   # 2026-11-14 10:50 (Ali): straight to the underside after the lift, then both
#   ends. "under" = the classic front pose (tool at the lens): the gripper face is behind the part, but it is rigid with
#   the tool, so an empty-gripper reference (sort.py --refs) removes it. tilt+-60 showed the side, not the underside.
PART_PAST_TCP_MM = 12            # held part centre, along the tool axis past the TCP


def _lsq(res, seed):
    from scipy.optimize import least_squares
    q = least_squares(lambda v: res(v, 0.02), seed, method="lm").x
    return least_squares(lambda v: res(v, 0.0), q, method="lm", xtol=1e-9).x


def _ok(q):
    return all(lo <= v <= hi for v, (lo, hi) in zip(q, JOINT_LIMITS))


def _clearance(q, obstacles, holding=False):
    worst = 1e9
    for _, (c, d) in obstacles:
        c, h = np.array(c, float), np.array(d, float) / 2
        for p, r in body_points(q, holding):
            qq = np.abs(p - c) - h
            worst = min(worst, np.linalg.norm(np.maximum(qq, 0)) + min(qq.max(), 0) - r)
    return worst


def oblique_candidates(x, y, yaw_deg, phi_deg, surface_z, seed, obstacles, part_r=5.0):
    """Joint vectors putting the wrist lens on a ray tilted phi about the part's long axis, aimed at its centre, for
    each standoff in OBLIQUE_LENS_MM (best first). Claws spread along the part (flange y || axis) to stay off the
    table. Static clearance >= 10 mm only; the caller path-checks the move."""
    A = np.array([math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg)), 0.0])
    n = np.array([-A[1], A[0], 0.0])
    part = np.array([x, y, surface_z + part_r])
    ray = math.cos(math.radians(phi_deg)) * np.array([0, 0, 1.0]) + math.sin(math.radians(phi_deg)) * n
    out = []
    for d in OBLIQUE_LENS_MM:
        cam = part + d * ray
        best = None
        for s in (1, -1):
            def res(q, reg):
                F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]
                r = list((t + R @ CAM_IN_FLANGE - cam) / 5.0) + list((R[:, 2] + ray) * 50) + list(np.cross(R[:, 1], s * A) * 50)
                return r + list((np.asarray(q) - seed) * reg)
            q = _lsq(res, np.array(seed, float))
            F = frames(q)[-1]
            if np.linalg.norm(F[:3, 3] + F[:3, :3] @ CAM_IN_FLANGE - cam) > 2 or F[:3, 2] @ -ray < math.cos(math.radians(1)):
                continue
            q = [round(float(v), 2) for v in q]
            if not _ok(q):
                continue
            cl = _clearance(q, obstacles)
            if cl >= 10 and (best is None or cl > best[0]):
                best = (cl, q)
        if best:
            out.append((d, best[1]))
    return out


def webcam_views(front_joints_deg, path=None):
    """{name: joints} for WEB_ORDER, part centre where today's 'front' view holds it. j6 chained to the nearest turn
    so consecutive views don't spin the wrist a full revolution."""
    cp = json.load(open(path or ROOT / "config" / "checkpoint.json"))["webcam"]
    C = np.array(cp["optical_axis_world"], float); C /= np.linalg.norm(C)
    front = np.array(flip(front_joints_deg), float)
    F = frames(front)[-1]
    centre = F[:3, 3] + F[:3, 2] * (TCP_MM + PART_PAST_TCP_MM)
    up = np.array([0, 0, 1.0]); toward = -C
    A = up - (up @ C) * C; A /= np.linalg.norm(A)
    n = np.cross(A, toward)

    def solve(axis, xdir):
        axis = axis / np.linalg.norm(axis)
        def res(q, reg):
            Fq = frames(q)[-1]; R, t = Fq[:3, :3], Fq[:3, 3]
            pc = t + R @ np.array([0, 0, TCP_MM + PART_PAST_TCP_MM])
            return list((pc - centre) / 5) + list((R[:, 2] - axis) * 50) + list((R[:, 0] - xdir) * 50) + list((np.asarray(q) - front) * reg)
        return [float(v) for v in _lsq(res, front)]

    t = math.radians(WEB_TILT_DEG)
    raw = {"under": [float(v) for v in front],
           "tilt+60": solve(math.cos(t) * toward + math.sin(t) * n, A),
           "tilt-60": solve(math.cos(t) * toward - math.sin(t) * n, A),
           "end_a": solve(-up, toward), "end_b": solve(-up, -toward)}
    out, prev = {}, front[5]
    for name in WEB_ORDER:
        q = raw[name]
        q[5] = min((q[5] + 360 * k for k in range(-3, 4) if -355 <= q[5] + 360 * k <= 355), key=lambda c: abs(c - prev))
        prev = q[5]
        out[name] = [round(v, 2) for v in q]
    return out


def oblique_crop(rgb, k, rot, t, ends_xy, z, pad_mm=8.0, half_h_mm=13.0):
    """Tight crop of the part in an oblique wrist image, rotated so its long axis is horizontal.
    ends_xy: the part's two end points (world mm) from the top look; z: height of its axis (surface + radius).
    The crop is the part plus pad_mm along the axis and +-half_h_mm across it: inside the pad, so the background is
    cardboard wherever the part was picked (the table edge / clutter only reaches the frame edges).
    Returns (crop RGB array, axis-aligned box [x0, y0, x1, y1] in the source image)."""
    from PIL import Image
    E = np.array([[e[0], e[1], z] for e in ends_xy], float)
    C = (E - t) @ rot                                    # world -> camera (rot: camera -> world)
    uv = np.c_[k.focal_x_px * C[:, 0] / C[:, 2] + k.center_x_px, k.focal_y_px * C[:, 1] / C[:, 2] + k.center_y_px]
    mm_px = float(C[:, 2].mean()) / k.focal_x_px
    # Snap to the part's own blob near the projection: the extrinsics put it 10-15 mm off along the axis at some
    # oblique poses (runs/20261114_103009_collect item 2, -45). Projection stays the fallback.
    try:
        from screws import detect
        c0 = uv.mean(0)
        blobs = [b for b in detect(rgb, None, None, ends=True) if math.hypot(b[0] - c0[0], b[1] - c0[1]) < 40 / mm_px]
        if blobs:
            b = max(blobs, key=lambda b: b[2])
            got = np.array(b[5], float)
            if 0.6 < np.hypot(*(got[1] - got[0])) / max(1.0, np.hypot(*(uv[1] - uv[0]))) < 1.6:
                uv = got
    except Exception:
        pass
    d = uv[1] - uv[0]
    length = float(np.hypot(*d)) + 2 * pad_mm / mm_px
    height = 2 * half_h_mm / mm_px
    centre = uv.mean(0)
    ang = math.degrees(math.atan2(d[1], d[0]))
    r = int(math.ceil(math.hypot(length, height) / 2)) + 2
    x0, y0 = int(centre[0]) - r, int(centre[1]) - r
    H, W = rgb.shape[:2]
    big = np.zeros((2 * r, 2 * r, 3), np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + 2 * r), min(H, y0 + 2 * r)
    if sx1 <= sx0 or sy1 <= sy0:
        return None, None
    big[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    im = Image.fromarray(big).rotate(ang, resample=Image.BILINEAR, center=(centre[0] - x0, centre[1] - y0))
    cx, cy = centre[0] - x0, centre[1] - y0
    im = im.crop((int(cx - length / 2), int(cy - height / 2), int(cx + length / 2), int(cy + height / 2)))
    return np.asarray(im), [sx0, sy0, sx1, sy1]
