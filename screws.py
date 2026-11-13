"""Live tracking of the screws (and other fasteners) on the table. Read-only: never moves the arm.

    python screws.py                        # wrist cam from where the arm is (best at the survey pose): world mm
    python screws.py --seconds 30 --save-every 5
    python screws.py --cam overview-cam     # static cam, uncalibrated: pixels only

Every fastener gets an id that stays with it across frames, also while it is pushed around, plus
position, angle, speed and still/moving. Annotated frames go to logs/screws-<time>/.

Wrist cam: color-only frames (tens of ms, vs ~1.2 s with depth). Each pixel's ray is intersected
with the table plane (measured once from depth at start), as verified to +-5 mm in CONTEXT.md. The
arm must stay where it is while this runs, since the camera pose is read once.
"""

import argparse
import asyncio
import io
import json
import math
import os
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from viam.components.arm import Arm
from viam.components.camera import Camera

from pipeline import LOG_DIR, POSES_PATH, cam_to_world, scan
from station import connect
from tracking import MultiTracker

COLOR_DIFF = 70           # summed RGB distance from the local background that counts as a part
BACKGROUND_SIGMA_PX = 25  # wider than a part at the survey scale
MIN_PIXELS, MAX_PIXELS = 40, 12000
MIN_GRAY = 60             # darker blobs are the gripper's black claws
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
    # the background is smooth, so blur at quarter resolution and scale back up (~10x faster)
    small = ndimage.gaussian_filter(f[::4, ::4], sigma=(BACKGROUND_SIGMA_PX / 4, BACKGROUND_SIGMA_PX / 4, 0))
    background = np.repeat(np.repeat(small, 4, axis=0), 4, axis=1)[:f.shape[0], :f.shape[1]]
    mask = ndimage.binary_opening(np.abs(f - background).sum(axis=-1) > COLOR_DIFF, iterations=1)
    mask = ndimage.binary_closing(mask, iterations=2)  # shiny parts break into pieces
    labels, n = ndimage.label(mask)
    gray = f @ [0.299, 0.587, 0.114]
    h, w = mask.shape
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        ys, xs = np.nonzero(labels[sl] == i)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        if not MIN_PIXELS <= len(xs) <= MAX_PIXELS:
            continue
        m = EDGE_MARGIN_PX
        if xs.min() < m or ys.min() < m or xs.max() >= w - m or ys.max() >= h - m:
            continue  # cut by the frame edge: the gripper finger (always bottom-right), hands, clutter
        if gray[ys, xs].mean() < MIN_GRAY:
            continue
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


async def color_frame(cam: Camera, wrist: bool) -> np.ndarray:
    # asking the RealSense for color only: ~9 ms instead of 100-300 ms for color + depth
    images, _ = await cam.get_images(filter_source_names=["color"]) if wrist else await cam.get_images()
    img = next(i for i in images if "depth" not in i.name)
    return np.asarray(Image.open(io.BytesIO(img.data)).convert("RGB"))


def draw(rgb, tracks: dict, world: bool, note: str) -> Image.Image:
    img = Image.fromarray(rgb)
    d = ImageDraw.Draw(img)
    unit = "mm" if world else "px"
    for tid, tr in tracks.items():
        x0, y0, x1, y1 = tr.last_det[4]
        moving = tr.speed() > 15
        color = "red" if moving else "lime"
        d.rectangle((x0 - 3, y0 - 3, x1 + 3, y1 + 3), outline=color, width=2)
        d.text((x0, max(0, y0 - 24)), f"#{tid} ({tr.x:.0f},{tr.y:.0f}){unit}", fill=color)
        d.text((x0, max(0, y0 - 12)), f"{tr.speed():.0f} {unit}/s {'moving' if moving else 'still'}", fill=color)
    d.text((5, 5), note, fill="blue")
    return img


async def main(args):
    with open(POSES_PATH) as f:
        poses = json.load(f)
    out = os.path.join(LOG_DIR, f"screws-{time.strftime('%H%M%S')}")
    os.makedirs(out, exist_ok=True)
    async with await connect() as machine:
        cam = Camera.from_robot(machine, args.cam)
        world = args.cam == "cam"
        view = None
        if world:
            joints = [round(v, 1) for v in (await Arm.from_robot(machine, "arm").get_joint_positions()).values]
            if max(abs(a - b) for a, b in zip(joints, poses["scan_joints_deg"])) > 1:
                print(f"note: arm is not at the survey pose ({joints}); tracking from here")
            s = await scan(machine, cam, poses["pick_region"])  # one depth frame for the table height
            rot, t = await cam_to_world(machine)
            view = WristView((await cam.get_properties()).intrinsic_parameters, rot, t, s.table_z)
            print(f"table z {s.table_z:.1f} mm; camera at z {t[2]:.0f}")
        mt = MultiTracker(gate=40 if world else 40, still_tol=4 if world else 3)
        unit = "mm" if world else "px"
        t_end = time.monotonic() + args.seconds
        frames, last_print, prev = 0, 0.0, {}
        log = open(os.path.join(out, "tracks.jsonl"), "w")
        while time.monotonic() < t_end:
            t0 = time.perf_counter()
            rgb = await color_frame(cam, world)
            t = time.monotonic()
            dets = detect(rgb, view, poses["pick_region"] if world else None)
            tracks = mt.update(dets, t)
            ms = (time.perf_counter() - t0) * 1000
            frames += 1
            log.write(json.dumps({"t": round(t, 3), "ms": round(ms), "tracks": {
                k: {"x": round(tr.x, 1), "y": round(tr.y, 1), "yaw": round(tr.last_det[3]), "speed": round(tr.speed()),
                    "still_s": round(tr.still_for(t), 2), "pixels": tr.last_det[2]} for k, tr in tracks.items()}}) + "\n")
            if args.save_every and frames % args.save_every == 0:
                draw(rgb, tracks, world, f"frame {frames} {ms:.0f} ms").save(os.path.join(out, f"{frames:04d}.jpg"))
            # print when the set of ids changes, something moves, or once a second
            moving = {k for k, tr in tracks.items() if tr.speed() > 15}
            if set(tracks) != set(prev) or moving or t - last_print > 1.0:
                rows = "  ".join(f"#{k}({tr.x:.0f},{tr.y:.0f}){'*' if k in moving else ''}" for k, tr in sorted(tracks.items()))
                print(f"{ms:4.0f} ms  {len(tracks)} parts [{unit}]  {rows or '-'}")
                for k in set(prev) - set(tracks):
                    print(f"       #{k} lost")
                last_print, prev = t, dict(tracks)
        draw(rgb, tracks, world, f"last frame, {frames} frames").save(os.path.join(out, "last.jpg"))
        print(f"\n{frames} frames in {args.seconds:.0f} s ({frames / args.seconds:.1f} fps). * = moving. -> {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cam", default="cam", help="cam (wrist, world mm) or overview-cam (pixels)")
    p.add_argument("--seconds", type=float, default=15)
    p.add_argument("--save-every", type=int, default=10, help="save an annotated frame every N frames (0 = only the last)")
    asyncio.run(main(p.parse_args()))
