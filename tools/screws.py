"""Live tracking of the screws (and other fasteners) on the table. Read-only: never moves the arm.

    python -m tools.screws                        # wrist cam from where the arm is (best at the survey pose): world mm
    python -m tools.screws --seconds 30 --save-every 5
    python -m tools.screws --cam overview-cam     # static cam, uncalibrated: pixels only

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

from vh.config import LOG_DIR, POSES_PATH
from vh.motion import cam_to_world
from vh.scan import scan
from station import connect
from vh.tracking import MultiTracker
from vh.detection import WristView, detect

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
            view = WristView((await cam.get_properties()).intrinsic_parameters, rot, t, poses["grasp"]["table_z"])
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
