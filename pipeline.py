"""Track 3 MVP: scan -> find item (depth) -> classify (anomaly) -> decide -> log -> pick -> place.

    python pipeline.py              # dry run: perceive, decide and log once; the arm does not move
    python pipeline.py --loop       # dry run, repeatedly
    python pipeline.py --live --step  # move the arm, waiting for Enter before every motion
    python pipeline.py --live       # move the arm without pausing

The judge log is logs/decisions.csv (item, decision, confidence, timestamp); logs/events.jsonl
has the full record per item, including the latency from first sighting to first arm motion.
"""

import argparse
import asyncio
import io
import csv
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.components.gripper import Gripper
from viam.proto.common import (GeometriesInFrame, Geometry, Pose, PoseInFrame,
                               RectangularPrism, Vector3, WorldState)
from viam.proto.component.arm import JointPositions
from viam.services.motion import Motion
from viam.services.vision import Vision

from station import connect

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
POSES_PATH = os.path.join(HERE, "config", "poses.json")

ITEM_MIN_HEIGHT_MM = 6     # depth points this far above the table count as an item
ITEM_MAX_HEIGHT_MM = 80    # taller blobs are not items (laptops, bins, people)
ITEM_MIN_PIXELS = 150      # smaller blobs are depth noise
ITEM_MAX_PIXELS = 12000    # larger blobs are not items at the scan pose's scale
COLOR_DIFF = 70            # summed RGB distance from the local background that counts as an item,
                           # for parts too flat to show in depth (washers, nuts, thin screws)
BACKGROUND_SIGMA_PX = 25   # blur for the local background; must be wider than an item


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def box(label, cx, cy, cz, dx, dy, dz) -> Geometry:
    return Geometry(center=Pose(x=cx, y=cy, z=cz, o_z=1),
                    box=RectangularPrism(dims_mm=Vector3(x=dx, y=dy, z=dz)), label=label)


def world_state(table_z: float) -> WorldState:
    """The workcell obstacles from the armfarm-workcell-obstacles fragment, which is disabled on
    this station, with the table top moved to the height measured from depth."""
    table_top = table_z - 5  # let fingertips get close to the surface
    return WorldState(obstacles=[GeometriesInFrame(reference_frame="world", geometries=[
        box("table", 0, 0, table_top - 100, 3000, 3000, 200),
        box("wall-front", 740, 0, 300, 100, 3000, 1600),
        box("wall-side", 0, -500, 300, 3000, 100, 1600),
        box("ceiling", 0, 0, 1050, 3000, 3000, 100),
    ])])


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


async def cam_to_world(machine) -> tuple:
    """Rotation and translation taking camera-frame points (mm) to world, read from the frame
    system by transforming the camera origin and its unit axes."""
    pts = []
    for v in ((0, 0, 0), (100, 0, 0), (0, 100, 0), (0, 0, 100)):
        r = await machine.transform_pose(
            PoseInFrame(reference_frame="cam", pose=Pose(x=v[0], y=v[1], z=v[2], o_z=1)), "world")
        pts.append(np.array([r.pose.x, r.pose.y, r.pose.z]))
    t = pts[0]
    rot = np.stack([(p - t) / 100 for p in pts[1:]], axis=1)
    return rot, t


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
    return Scan(color=img, table_z=table_z, items=items)


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


def decide(score: float | None, cfg: dict) -> tuple:
    """(destination, confidence in that destination)."""
    if score is None:
        return "unknown", 0.0
    if score >= cfg["hold_high"]:
        return "reject", score
    if score < cfg["hold_low"]:
        return "box", 1 - score
    return "hold", 1 - abs(score - (cfg["hold_low"] + cfg["hold_high"]) / 2) * 2


class Logger:
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.csv_path = os.path.join(LOG_DIR, "decisions.csv")
        new = not os.path.exists(self.csv_path)
        self.csv = open(self.csv_path, "a", newline="")
        self.writer = csv.writer(self.csv)
        if new:
            self.writer.writerow(["item", "decision", "confidence", "timestamp"])
            self.csv.flush()
        self.events = open(os.path.join(LOG_DIR, "events.jsonl"), "a")

    def decision(self, n, decision, confidence, ts):
        self.writer.writerow([n, decision, f"{confidence:.3f}", ts])
        self.csv.flush()

    def event(self, **kw):
        self.events.write(json.dumps(kw) + "\n")
        self.events.flush()


def save_debug_image(scan: Scan, n: int, decision: str, score):
    img = scan.color.copy()
    d = ImageDraw.Draw(img)
    for i, it in enumerate(scan.items):
        d.rectangle(it.bbox, outline="lime" if i == 0 else "yellow", width=2)
        d.text((it.bbox[0], max(0, it.bbox[1] - 12)), f"({it.x:.0f},{it.y:.0f},{it.top_z:.0f})", fill="lime")
    d.text((5, 5), f"item {n}: {decision} score={score} table_z={scan.table_z:.1f}", fill="red")
    path = os.path.join(LOG_DIR, f"item-{n:03d}.jpg")
    img.save(path)
    return path


class Mover:
    def __init__(self, machine, live: bool, step: bool, table_z: float):
        self.machine = machine
        self.motion = Motion.from_robot(machine, "builtin")
        self.arm = Arm.from_robot(machine, "arm")
        self.gripper = Gripper.from_robot(machine, "gripper")
        self.live, self.step = live, step
        self.ws = world_state(table_z)
        self.first_motion_at = None

    def _gate(self, what: str) -> bool:
        if not self.live:
            print(f"  [dry run] would {what}")
            return False
        if self.step:
            input(f"  Enter to {what} (Ctrl-C aborts) ")
        if self.first_motion_at is None:
            self.first_motion_at = now_iso()
        print(f"  {what}")
        return True

    async def joints(self, deg, what):
        if self._gate(what):
            await self.arm.move_to_joint_positions(JointPositions(values=deg))

    async def to(self, x, y, z, theta, what):
        if self._gate(f"{what} -> ({x:.0f}, {y:.0f}, {z:.0f}) theta={theta:.0f}"):
            await self.motion.move("gripper", PoseInFrame(
                reference_frame="world", pose=Pose(x=x, y=y, z=z, o_z=-1, theta=theta)),
                world_state=self.ws)

    async def straight(self, x, y, z, what):
        """Move the gripper TCP in a straight line to (x, y, z), keeping its orientation, by moving the
        arm directly: no planner and no obstacle check. For the last few cm near the table, where the
        planner refuses every pose because the gripper's `claws` geometry reaches 50 mm past the TCP.
        The arm base is the world frame, so a TCP translation is the same flange translation."""
        if self._gate(f"{what} (straight) -> ({x:.0f}, {y:.0f}, {z:.0f})"):
            tcp = await tcp_pose(self.machine)
            p = await self.arm.get_end_position()
            await self.arm.move_to_position(Pose(
                x=p.x + x - tcp.x, y=p.y + y - tcp.y, z=p.z + z - tcp.z,
                o_x=p.o_x, o_y=p.o_y, o_z=p.o_z, theta=p.theta))

    async def open(self):
        if self._gate("open gripper"):
            await self.gripper.open()

    async def grab(self):
        if self._gate("close gripper"):
            return await self.gripper.grab()
        return None


async def tcp_pose(machine) -> Pose:
    """The gripper TCP (arm + 150 mm) in the world frame."""
    return (await machine.transform_pose(PoseInFrame(reference_frame="gripper", pose=Pose(o_z=1)), "world")).pose


async def gripper_theta(machine) -> float:
    return (await tcp_pose(machine)).theta


def grasp_height(item: Item, table_z: float, g: dict) -> float:
    """TCP height for the grasp: fingertips halfway up the item, never closer to the table than the
    clearance. tcp_to_tip_mm is how far the real fingertips reach past the 150 mm gripper TCP."""
    tips_z = max((item.top_z + table_z) / 2, table_z + g["min_table_clearance_mm"])
    return tips_z + g["tcp_to_tip_mm"]


async def handle_item(machine, mover: Mover, item: Item, dest_name: str, poses: dict, table_z: float,
                      base_theta: float):
    g = poses["grasp"]
    dest = poses["destinations"].get(dest_name)
    if dest is None:
        print(f"  destination {dest_name!r} not recorded yet: run python record_pose.py {dest_name}")
        if mover.live:
            raise SystemExit(1)
        dest = {"x": 0, "y": 0, "z": 0}
    theta = base_theta + (item.yaw_deg + g["jaw_offset_deg"] if g["use_yaw"] else 0)
    grasp_z = grasp_height(item, table_z, g)
    above = item.top_z + g["approach_height_mm"]

    await mover.open()
    await mover.to(item.x, item.y, above, theta, "approach")
    await mover.straight(item.x, item.y, grasp_z, "descend")
    held = await mover.grab()
    await mover.straight(item.x, item.y, above, "lift")
    await mover.to(dest["x"], dest["y"], dest["z"] + g["approach_height_mm"], base_theta, f"over {dest_name}")
    await mover.straight(dest["x"], dest["y"], dest["z"], f"lower into {dest_name}")
    await mover.open()
    await mover.straight(dest["x"], dest["y"], dest["z"] + g["approach_height_mm"], "retreat")
    await mover.joints(poses["scan_joints_deg"], "return to scan pose")
    return held


async def main(args):
    with open(POSES_PATH) as f:
        poses = json.load(f)
    if args.live:
        missing = [k for k, v in poses["destinations"].items() if v is None]
        if missing:
            raise SystemExit(f"record these destinations before --live: {missing}")
    log = Logger()
    n = sum(1 for _ in open(log.csv_path)) - 1

    async with await connect() as machine:
        cam = Camera.from_robot(machine, "cam")
        try:
            anomaly = Vision.from_robot(machine, "anomaly")
        except Exception:
            anomaly = None
            print("no 'anomaly' vision service on the machine yet; decisions will be 'unknown'")
            if args.live:
                raise SystemExit("the anomaly service is required for --live")

        mover = Mover(machine, args.live, args.step, table_z=0.0)
        await mover.joints(poses["scan_joints_deg"], "go to scan pose")
        base_theta = await gripper_theta(machine)

        while True:
            s = await scan(machine, cam, poses["pick_region"])
            if not s.items:
                if not args.loop:
                    print(f"no item in the pick region (table_z={s.table_z:.1f} mm)")
                    save_debug_image(s, n + 1, "none", None)
                    return
                await asyncio.sleep(0.2)
                continue

            seen_at = now_iso()
            item = s.items[0]
            score, boxes = await classify(anomaly)
            dest, conf = decide(score, poses["decision"])
            n += 1
            log.decision(n, dest, conf, seen_at)
            img = save_debug_image(s, n, dest, None if score is None else round(score, 3))
            print(f"item {n}: {dest} (score={score}, conf={conf:.2f}) at ({item.x:.0f}, {item.y:.0f}), "
                  f"top {item.top_z - s.table_z:.0f} mm above table, {len(s.items)} in view -> {img}")

            mover.ws = world_state(s.table_z)
            mover.first_motion_at = None
            held = await handle_item(machine, mover, item, dest, poses, s.table_z, base_theta)
            log.event(item=n, decision=dest, confidence=conf, score=score, anomaly_boxes=boxes,
                      seen_at=seen_at, first_motion_at=mover.first_motion_at, held=held,
                      x=item.x, y=item.y, top_z=item.top_z, table_z=s.table_z, live=args.live)
            if not args.loop:
                return


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true", help="move the arm (default: dry run)")
    p.add_argument("--step", action="store_true", help="with --live, wait for Enter before each motion")
    p.add_argument("--loop", action="store_true", help="keep scanning for items")
    asyncio.run(main(p.parse_args()))
