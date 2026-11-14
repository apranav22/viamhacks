"""The Track 3 loop. MOVES THE ARM.

    python sort.py --mode collect --label good --type socket_m16 --reps 6     # data: pick, look, put back, repeat
    python sort.py --mode sort --items 6                                     # judged run: pick, look, decide, sort

One cycle:
  WATCH    wrist cam over the pick pad, color only (~10 ms frame on the station), until a part is placed and still
  PICK     one joint move to hover over it (FIRST MOTION: the latency clock stops here), look again, descend, grab
  LIFT     straight up to 280 mm
  INSPECT  joint moves through the webcam views at the checkpoint over the REJECT compartment
  DECIDE   after every view: a known defect (tape) or a clear anomaly -> drop now; all clean -> good
  DROP     reject: open where we are (the part falls into reject) | good: one joint move over the good compartment
  PLACE    (collect mode) put the part back on the pad at a new spot and angle
  RETURN   joint move to the watch pose

Moves between known poses are joint moves to recorded / IK-solved joint vectors (no motion planner: the planner took
4-7 s for these legs and picked wrapped joint configurations), each checked against the workcell obstacles first
(vh/kinematics.py: forward kinematics from the arm's own URDF). Descend / lift are Pranav's straight moves; grasp
height, jaw direction, held check and retries come from vh/motion.py and config/poses.json unchanged.

Every stage is sent to the dashboard as UDP telemetry (vh/telemetry.py: non-blocking, measured in microseconds).
Every decision is written to runs/<run>/decisions.jsonl with ms timestamps (the judge log).
"""

import argparse
import asyncio
import io
import json
import math
import random
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from viam.components.camera import Camera
from viam.services.generic import Generic

from viam.proto.component.arm import JointPositions
from vh.motion import Mover, cam_to_world, grasp_height, held, tcp_pose
from vh.detection import WristView, detect
from station import connect
from station_shell import execute as station_exec
from vh.kinematics import check_path, flip, frames, ik, load_obstacles, safe_joint_speed, tcp as fk_tcp
from vh.telemetry import Telemetry
from vh.anomaly import AnomalyModels, Score, context_crop, reject_reason

from vh.config import POSES, CHECKPOINT as CP
G = POSES["grasp"]
TZ = G["table_z"]
WATCH_J = CP["watch_pose"]["joints_deg"]
# Per-move joint speed (--tcp-limit): every joint move runs at the fastest leading-joint speed whose peak TOOL speed stays
# under a limit, from the move's own joint path (vh.kinematics.safe_joint_speed). The xArm firmware limits the TCP to
# 1000 mm/s; one speed for every move put the tip at 2.4-2.9 m/s on lift -> front at 180 deg/s, and ~874 mm/s even at 60.
NORMAL_SPEED, NORMAL_ACCEL = 60.0, 381.67   # the module defaults: restored at run end; also every straight (planner) move
RUN_ACCEL = 600.0                   # deg/s^2 during a run (module limit 1145): the value the speed limits were analysed at
LIFT_Z = 280.0                      # TCP height before swinging to the checkpoint: clears the box walls (100) + flap (140)
HOVER_Z = TZ + 10 + G["approach_height_mm"]
VIEW_ORDER = ["front", "yaw-20", "yaw+35", "pitch-25"]   # this order keeps every leg clear of the box
VIEW_J = {k: flip(v["joints_deg"]) for k, v in CP["views"].items()}   # wrist-flipped: j4 near 0, no 180 deg wrist spin
GOOD_TCP = (470.0, -120.0, 260.0)
# Upright parts hang in line with the gripper: end face first (pointed at the lens), then the side all round with the
# gripper pointing down and joint 6 turned 0 / +120 / -120. Ends at a pose whose path to the good box clears the divider.
_D = ik(np.array([285.0, -150.0, 300.0]), axis=(0, 0, -1), seed=VIEW_J["front"])[0]
UPRIGHT_J = {"end": VIEW_J["front"], "side0": _D, "side+120": _D[:5] + [_D[5] + 120], "side-120": _D[:5] + [_D[5] - 120]}
UPRIGHT_ORDER = ["end", "side0", "side+120", "side-120"]   # over the far (good) compartment, pointing down
PM = np.array(CP["webcam"]["P_world_to_px"])
STABLE_MM, STABLE_DEG = 3.0, 8.0
STANDING_MM = 15                    # taller than this: upright (a flat nut is 8-10 mm; a short bolt on its end is 22 mm)
HOVER_HIGH_Z = 230.0                # TCP height for a squat blob (nut flat or screw upright): depth needs >~20 cm range
ZONE = {"x_min": 190, "x_max": 450, "y_min": 260, "y_max": 410}   # pick zone on the bare table (kit storage starts ~y 470)
# Per --background: surface z (poses.json grasp.surface_z, touch-measured) and pick zone. The cardboard pad spans
# world x ~104-415 (flap seam at ~415), y ~162-546 from the wrist image, so its zone stops 25 mm short of the seam.
SURFACE_Z = G["surface_z"]
ZONES = {"white": ZONE, "cardboard": {"x_min": 150, "x_max": 400, "y_min": 200, "y_max": 500}}
# 18:35 pad (larger sheet) measured from the watch frame: x 109-454 (flap seam ~410), y 168-531. Zone keeps >=40 mm
# inside; IK + joint-path checks pass at a 5x5 grid x 4 yaws over it (look, low hover, lift).
# Top image: wrist lens centred over the part, this high above the surface (0.21 mm/px at 1280x720). Measured
# 2026-11-13 17:21 + 17:31 (runs/look_height_sweep_*, runs/look_height_led_*): all heights in focus; without the
# lamp LED the arm's shadow reached the part at 190, with the LED (now part of the capture recipe) it is even and
# neutral. 170 is refused by the planner (gripper:claws vs table). The old look centred the TCP (camera ~70 mm
# off-axis), so it hovered at TCP 230 (lens ~360, 0.39 mm/px) to keep long parts in frame.
LOOK_LENS_MM = 190.0
STILL_S = 0.3                       # part unchanged this long ...
HAND_FRAC, HAND_HOLDOFF_S = 0.02, 0.8   # ... and no hand (2% of the frame changed outside the pad) for 0.8 s
REF_STEADY_FRAC = 0.002             # outside-pad change between consecutive frames: scene is steady
REF_STALE_S = 3.0                   # a "hand" not moving at all this long = stale reference; re-take it
# Webcam crops are the whole gripper window: the blue-zinc socket_m16 reads up to 2.2% "tape" there (18:17 run, 153
# views; 18:50 a clean socket screw was rejected at 1.9%). Top view: part-only bbox, good parts <= 0.08%.
TAPE_FRAC_WEB = 0.04
TAPE_FRAC = 0.01                    # share of the part crop that is tape-blue to call it "known: tape"
# Wrist RGB controls (2026-11-13 17:05, runs/camera_lock_*): 1280x720, brightness 8, manual exposure 10 ms (luma ~123,
# no clipping, matches auto). Auto white balance kept: every manual temperature 4200-5500 K gave a red cast (R/G ~2.1).
# v4l2 controls reset when the camera/module restarts, so every run sets and records them.
WRIST_V4L2 = {"brightness": 8, "auto_exposure": 1, "exposure_time_absolute": 100, "white_balance_automatic": 1}
WRIST_DEV = "/dev/video4"
STATES_SORT = ["WATCH", "PICK", "LIFT", "INSPECT", "DECIDE", "DROP", "RETURN"]
STATES_COLLECT = ["WATCH", "PICK", "LIFT", "INSPECT", "PLACE", "RETURN"]


def sound(name="Ping"):
    """Warning chime on this computer before the arm moves. Non-blocking (Popen ~1 ms), so it costs no latency."""
    import subprocess
    try:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{name}.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def say(text):
    import subprocess
    try:
        subprocess.run(["say", text], timeout=5)
    except Exception:
        pass


def iso(t):
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="milliseconds")   # with UTC offset: the station is MST


def tape_fraction(rgb):
    """Share of pixels that are saturated blue (painter's tape), not the cyan-ish zinc of the plated parts."""
    f = rgb.astype(np.float32) / 255
    mx, mn = f.max(-1), f.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    hue_blue = (b == mx) & (b - np.maximum(r, g) > 0.12) & (r < g)          # blue dominant, not violet
    # 18:08 with the lamp LED + auto WB, tape on the top view read b-g ~0.21 vs b-r ~0.47 and failed the old 0.6 ratio
    # (tape 0.05% -> missed). 0.4: tape 2.3-3.9% of the crop, every good top image (36) <= 0.08%. Zinc is excluded by sat.
    blue = hue_blue & (sat > 0.45) & (mx > 0.25) & ((b - g) > 0.4 * (b - r))    # deep blue, not cyan (g close to b)
    return float(blue.mean())



def outside_change(rgb, ref, pad_px):
    """Share of the frame outside the pad (+15 px) that differs from the reference: a hand or arm reaching in."""
    a, b = rgb[::4, ::4].astype(np.int16), ref[::4, ::4].astype(np.int16)
    diff = np.abs(a - b).sum(-1) > 90
    x0, y0, x1, y1 = [v // 4 for v in pad_px]
    diff[max(0, y0 - 4):y1 + 4, max(0, x0 - 4):x1 + 4] = False
    return float(diff.mean())


def zone_px(view, z):
    """Pixel bbox of a world-xy rectangle on the table, in the wrist view (for the hand check)."""
    k = view.k
    us, vs = [], []
    for x in (z["x_min"], z["x_max"]):
        for y in (z["y_min"], z["y_max"]):
            c = view.rot.T @ (np.array([x, y, view.table_z]) - view.t)
            us.append(k.focal_x_px * c[0] / c[2] + k.center_x_px); vs.append(k.focal_y_px * c[1] / c[2] + k.center_y_px)
    return [int(max(0, min(us))), int(max(0, min(vs))), int(min(k.width_px, max(us))), int(min(k.height_px, max(vs)))]


def round_part(it):
    """Nuts and other squat parts: their long-axis angle is noise, so it doesn't count for 'still'."""
    x0, y0, x1, y1 = it[4]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    # A long part lying at ~45 deg also has a square axis-aligned box, but fills only ~1/3 of it (a nut ~3/4).
    # 17:37: a diagonal hex bolt (aspect 1.07, fill 0.33) went to the depth check, read 48 mm "upright", was skipped.
    return max(w, h) < 1.4 * min(w, h) and it[2] / (w * h) > 0.55


def project(pt):
    x = PM @ np.array([pt[0], pt[1], pt[2], 1.0])
    return x[:2] / x[2]


class Sorter:
    def __init__(self, m, args):
        self.m, self.args = m, args
        self.mv = Mover(m, True, False, table_z=TZ)
        self.arm, self.gripper = self.mv.arm, self.mv.gripper
        self.cam = Camera.from_robot(m, "cam")
        self.web = Camera.from_robot(m, "overview-cam")
        self.obs = load_obstacles(table_z=TZ)    # the pick surface: bare table or the cardboard pad
        self.run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + args.mode
        self.dir = ROOT / "runs" / self.run_id
        self.dir.mkdir(parents=True)
        self.tel = Telemetry(host=args.dash_host, run_id=self.run_id)
        if args.anomaly_bundle and str(args.anomaly_bundle) == "active":     # set from the training dashboard
            args.anomaly_bundle = Path((ROOT / "models" / "ACTIVE").read_text().strip())
            print(f"active anomaly bundle: {args.anomaly_bundle}", flush=True)
        self.anomaly = AnomalyModels(args.anomaly_bundle, args.anomaly_device, sizes=ROOT / "config" / "part_sizes.json") \
            if args.anomaly_bundle else None
        if self.anomaly:
            loaded = self.anomaly.warm(args.type, args.background)  # compile and warm BEFORE any arm motion
            print(f"Anomaly models ready on {args.anomaly_device}: {len(loaded)} groups", flush=True)
        self.judge = open(self.dir / "decisions.jsonl", "a", buffering=1)
        self.q = None                 # last known joints
        self.n = 0
        self.good_j = ik(np.array(GOOD_TCP), seed=VIEW_J["front"])[0]
        self.good_j_up = ik(np.array(GOOD_TCP[:2] + (300.0,)), seed=UPRIGHT_J["side-120"])[0]   # hanging part clears the divider
        self.view = None              # WristView at the watch pose (fixed: computed once)
        self.pad = dict(ZONE)         # pixel bounds are added at the watch pose
        self.ignore_xy = []           # parts deliberately left in place (upright, grasp disabled)

    # ---- helpers ---------------------------------------------------------------------------------
    def state(self, s, **kw):
        self.tel.state(s, item=self.n, **kw)
        print(f"[{self.n}] {s}", flush=True)

    async def joints(self):
        self.q = [float(v) for v in (await self.arm.get_joint_positions()).values]
        return self.q

    async def jmove(self, q, label, holding):
        """Joint move to q after checking the joint-space path against the obstacles, at the fastest joint speed that
        keeps this move's peak tool speed under --tcp-limit (--tcp-limit-holding with a part in the gripper)."""
        q0 = self.q or await self.joints()
        ok, c, where = check_path(q0, q, self.obs, holding=holding, margin=0)
        if not ok:
            self.tel.emit("error", msg=f"{label}: path blocked ({c} mm, {where}); not moving")
            raise RuntimeError(f"{label}: joint path would hit {where} ({c} mm)")
        speed = NORMAL_SPEED
        if self.args.tcp_limit:
            limit = self.args.tcp_limit_holding if holding else self.args.tcp_limit
            speed = safe_joint_speed(q0, q, limit, RUN_ACCEL)
        await self.set_joint_speed(speed)
        t = time.time()
        p, _ = fk_tcp(q)
        self.tel.emit("move", label=label, component="arm", joints=[round(v, 1) for v in q], target={"x": p[0], "y": p[1], "z": p[2]},
                      clearance_mm=c, joint_speed=speed)
        with self.tel.span(label, phase=label.split()[0], item=self.n):
            await self.arm.move_to_joint_positions(JointPositions(values=list(q)))
        self.q = list(q)
        return t

    async def straight(self, x, y, z, label):
        # the module plans straight moves itself (motion service), so their joint path, and tool speed, isn't ours to
        # bound: always the default 60 deg/s
        await self.set_joint_speed(NORMAL_SPEED)
        with self.tel.span(label, phase=label.split()[0], item=self.n):
            await self.mv.straight(x, y, z, label)
        self.q = None

    async def set_joint_speed(self, deg_s, accel=None):
        """Arm joint speed (and acceleration) via the module's set_speed / set_acceleration DoCommand; sent only when
        it changes. Lasts until changed or the module restarts, so run() restores the defaults at the end."""
        cmd = {}
        if getattr(self, "joint_speed", None) != deg_s:
            cmd["set_speed"] = float(deg_s)
        if accel is not None and getattr(self, "joint_accel", None) != accel:
            cmd["set_acceleration"] = float(accel)
        if cmd:
            await self.arm.do_command(cmd)
            self.joint_speed = deg_s
            self.joint_accel = accel if accel is not None else getattr(self, "joint_accel", None)

    async def release(self):
        """Open and wait until the fingers are really open: gripper.open() can return while they are still closed,
        and the next move then carries the part away (the taped nut fell under the watch pose that way)."""
        await self.gripper.open()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3.0:
            pos = await self.mv.finger_pos()
            if pos > 700:
                return pos
            await asyncio.sleep(0.05)
        self.tel.emit("error", msg=f"fingers still at {pos} 3 s after open")
        return pos

    async def wrist_jpeg(self):
        imgs, _ = await self.cam.get_images(filter_source_names=["color"])
        img = next(i for i in imgs if "depth" not in i.name)
        return img.data

    async def infer_crop(self, image, bbox, view):
        if self.anomaly is None:
            return Score("missing", detail="No anomaly bundle loaded"), bbox
        try:
            crop, box = self.anomaly.crop(image, bbox, view, getattr(self, "top_mmpx", None) if view == "top" else None)
        except ValueError as e:
            return Score("invalid", detail=str(e)), bbox
        result = await asyncio.to_thread(self.anomaly.score, crop, self.args.type, self.pose, view, self.args.background)
        return result, box

    def emit_anomaly(self, view, result, crop):
        fields = result.fields()
        self.meta.setdefault("anomaly", {})[view] = {**fields, "model_crop": crop}
        self.tel.emit("anomaly_result", frame=result.heatmap_bytes(), mime="application/x-anomaly-map;h=64;w=64",
                      n=self.n, view=view, model_crop=crop, background=self.args.background, **fields)

    async def web_jpeg(self):
        # the webcam hands out its newest buffered frame; the second call is taken after the arm stopped
        for _ in range(2):
            imgs, _ = await self.web.get_images()
        return imgs[0].data

    def item_px(self, it, view):
        """Overlay numbers for the dashboard: bbox, centre and long axis in pixels, world xy."""
        x, y, px, yaw, bbox = it
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        L = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 2
        w0 = view.to_world(cx, cy)
        def err(a):      # pixel direction whose world heading matches the part's long axis
            w1 = view.to_world(cx + 10 * math.cos(a), cy + 10 * math.sin(a))
            return abs((math.degrees(math.atan2(w1[1] - w0[1], w1[0] - w0[0])) - yaw + 90) % 180 - 90)
        a = min((math.radians(d) for d in range(0, 180, 3)), key=err)
        dx, dy = L * math.cos(a), L * math.sin(a)
        return {"bbox": bbox, "c": [cx, cy], "axis": [cx - dx, cy - dy, cx + dx, cy + dy], "xy": [round(x, 1), round(y, 1)],
                "yaw": round(yaw, 1), "px": px}

    # ---- stages ----------------------------------------------------------------------------------
    async def watch(self):
        """Until one part sits still on the pad. Returns (item, t_appeared, t_stable)."""
        self.state("WATCH")
        if self.view is None:
            self.watch_tcp = await tcp_pose(self.m)    # with view.t: the camera's offset from the TCP (look_joints)
            rot, t = await cam_to_world(self.m)
            k = (await self.cam.get_properties()).intrinsic_parameters
            self.view = WristView(k, rot, t, TZ)
            # Fixed pick zone on the bare table. No cardboard pad: the grasp goes 2 mm above the TABLE, so a pad
            # thicker than that gets pinched and dragged (it moved ~10 cm in 3 picks at 15:15).
            self.pad = dict(ZONE)
            self.pad["px"] = zone_px(self.view, ZONE)
            self.zone = self.pad
            print(f"pick zone x {ZONE['x_min']}..{ZONE['x_max']}, y {ZONE['y_min']}..{ZONE['y_max']} (pixels {self.pad['px']})")
            self.tel.emit("note", step="pick pad", **{k: round(v) if isinstance(v, float) else v for k, v in self.pad.items()})
            # 20:25 run 182455_sort: ONE reference frame, grabbed right after the arm/camera settings changed, latched
            # the "hand" gate on for 2180/2181 frames of a still scene. Take it only once frames stop changing.
            self.ref = await self.settled_ref()
        last, t_appeared, still_since, hand_until = None, None, None, 0.0
        prev_rgb, static_since = None, None
        while True:
            t0 = time.perf_counter()
            jpg = await self.wrist_jpeg()
            t1 = time.perf_counter()
            rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
            items = sorted(detect(rgb, self.view, self.zone), key=lambda it: -it[2])
            if not items:
                self.ignore_xy = []                     # zone empty: forget parts we chose to leave
            items = [it for it in items if all(math.dist(it[:2], q) > 25 for q in self.ignore_xy)]
            t2 = time.perf_counter()
            it = items[0] if items else None
            now = time.time()
            if it and t_appeared is None:
                t_appeared = now
            if not it:
                t_appeared, last = None, None
            hand = outside_change(rgb, self.ref, self.pad["px"]) > HAND_FRAC
            # Frame-to-frame steady outside the pad: either nothing is there, or the "hand" is just a stale reference.
            steady = prev_rgb is not None and outside_change(rgb, prev_rgb, self.pad["px"]) <= REF_STEADY_FRAC
            static_since = (static_since or now) if steady else None
            prev_rgb = rgb
            if hand and static_since and (not it or now - static_since >= REF_STALE_S):
                # zone empty and steady, or a "hand" that hasn't moved a pixel for REF_STALE_S: re-take the reference
                self.ref = rgb
                self.ref_updates += 1
                Image.fromarray(rgb).save(self.dir / f"ref_{self.ref_updates:02d}.jpg", quality=92)
                self.tel.emit("note", step="watch reference refreshed", reason="zone empty" if not it else "static",
                              n=self.ref_updates)
                print(f"  watch reference refreshed ({'zone empty' if not it else 'static change'})", flush=True)
                hand, static_since = False, None
            if hand:
                hand_until = now + HAND_HOLDOFF_S          # wait a moment after the hand leaves
            same = bool(it and last and math.dist(it[:2], last[:2]) < STABLE_MM
                        and (round_part(it) or abs((it[3] - last[3] + 90) % 180 - 90) < STABLE_DEG))
            still_since = (still_since or now) if same else None
            stable = bool(same and now > hand_until and now - still_since >= STILL_S)
            self.tel.emit("watch", frame=jpg, item=self.item_px(it, self.view) if it else None, placed=stable,
                          hand=hand or now < hand_until, n_items=len(items), rpc_ms=round((t1 - t0) * 1000, 1), proc_ms=round((t2 - t1) * 1000, 1))
            if stable:
                return it, t_appeared, now, jpg
            last = it
            if self.args.watch_timeout and t_appeared is None and now - self._watch_start > self.args.watch_timeout:
                return None, None, None, None

    async def settled_ref(self, max_s=5.0):
        """Reference for the hand gate: the first frame that matches the one before it outside the pad (arm and
        camera exposure/WB have settled). Saved as ref_00.jpg."""
        prev, t0 = None, time.monotonic()
        while True:
            rgb = np.asarray(Image.open(io.BytesIO(await self.wrist_jpeg())).convert("RGB"))
            d = None if prev is None else outside_change(rgb, prev, self.pad["px"])
            if d is not None and (d <= REF_STEADY_FRAC or time.monotonic() - t0 > max_s):
                break
            prev = rgb
            await asyncio.sleep(0.15)
        self.ref_updates = 0
        Image.fromarray(rgb).save(self.dir / "ref_00.jpg", quality=92)
        print(f"  watch reference taken (frame-to-frame change {d:.4f})", flush=True)
        return rgb

    def look_joints(self, item):
        """Joints putting the wrist lens LOOK_LENS_MM straight above the part, by translating the watch pose (same
        wrist heading, so the camera offset from the TCP measured at the watch pose stays valid)."""
        w = self.watch_tcp
        off = np.asarray(self.view.t) - np.array([w.x, w.y, w.z])                     # camera minus TCP, world, at the watch pose
        y = frames(WATCH_J)[-1][:3, 1]
        heading = math.degrees(math.atan2(y[1], y[0]))
        target = np.array([item[0] - off[0], item[1] - off[1], TZ + LOOK_LENS_MM - off[2]])
        q, err, _ = ik(target, seed=WATCH_J, jaw_heading_deg=heading)
        p, _ = fk_tcp(q)
        if np.linalg.norm(p - target) > 2 or p[2] - G["tcp_to_tip_mm"] < TZ + 30:
            raise RuntimeError(f"look pose unreachable or too low: {np.round(p, 1).tolist()} vs {np.round(target, 1).tolist()}")
        return q

    async def look(self, item, attempt, heading):
        """Top image with the lens centred LOOK_LENS_MM above the part: position and angle of the same part."""
        jpg, (rot, t), props = await asyncio.gather(self.wrist_jpeg(), cam_to_world(self.m), self.cam.get_properties())
        view = WristView(props.intrinsic_parameters, rot, t, TZ)
        rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
        near = [it for it in detect(rgb, view, None) if math.dist(it[:2], item[:2]) < 60]
        new = None
        if near:
            # At 0.21 mm/px a shiny head can split off from the threads as its own blob. 18:20 socket_m16 #17/#27: the
            # nearest blob was a head fragment -> tiny top crop, grasp at the head, #27 dropped. Merge the blobs.
            big = max(near, key=lambda it: it[2])
            n = sum(it[2] for it in near)
            new = (sum(it[0] * it[2] for it in near) / n, sum(it[1] * it[2] for it in near) / n, n, big[3],
                   (min(it[4][0] for it in near), min(it[4][1] for it in near),
                    max(it[4][2] for it in near), max(it[4][3] for it in near)))
        tape = None
        if new:
            x0, y0, x1, y1 = new[4]
            tape = tape_fraction(rgb[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6])
        (self.idir / f"top_{attempt}.jpg").write_bytes(jpg)
        self.top_image, self.top_bbox = jpg, list(new[4]) if new else None
        self.top_mmpx = (t[2] - TZ) / props.intrinsic_parameters.focal_x_px     # part size in mm (type auto)
        self.meta.setdefault("top", {})[f"top_{attempt}"] = {
            "bbox": list(new[4]) if new else None, "xy": [round(new[0], 1), round(new[1], 1)] if new else None,
            "yaw_world": round(new[3], 1) if new else None, "pixels": new[2] if new else None,
            "cam_R": np.round(rot, 5).tolist(), "cam_t": np.round(t, 2).tolist()}
        self.tel.emit("look", frame=jpg, n=self.n, label=f"hover look {attempt}", item=self.item_px(new, view) if new else None,
                      m={"x": new[0], "y": new[1], "yaw_long": new[3], "height": 10} if new else None, tape=tape,
                      shape=self.args.type, grasp={"jaw_heading": heading % 180, "tip_z": TZ + G["min_table_clearance_mm"], "ok": True})
        return new, tape

    async def depth_look(self, xy):
        """One color+depth frame from hover: is the part near xy standing up? Returns (height_mm, xy_of_upper_half)
        or (None, None) without depth. Color alone can't tell an upright screw from a flat nut, and puts an upright
        part's top ~20 mm off (it isn't on the table plane), so standing parts are located from depth points."""
        imgs, _ = await self.cam.get_images()
        dimg = next((i for i in imgs if i.name == "depth"), None)
        if dimg is None:
            return None, None
        D = np.asarray(dimg.bytes_to_depth_array(), dtype=float)
        k = (await self.cam.get_properties()).intrinsic_parameters
        rot, t = await cam_to_world(self.m)
        h, w = D.shape
        u, v = np.meshgrid(np.arange(w), np.arange(h))
        P = np.stack([(u - k.center_x_px) * D / k.focal_x_px, (v - k.center_y_px) * D / k.focal_y_px, D], -1) @ rot.T + t
        sel = (D > 0) & (np.hypot(P[..., 0] - xy[0], P[..., 1] - xy[1]) < 45) & (P[..., 2] > TZ + 6)
        pts = P[sel]
        if len(pts) < 25:
            return 0.0, None
        top = float(np.percentile(pts[:, 2], 95))
        upper = pts[pts[:, 2] > TZ + 0.5 * (top - TZ)]
        self.tel.emit("note", step="depth look", height=round(top - TZ, 1), points=int(len(pts)),
                      xy=[round(float(c), 1) for c in upper[:, :2].mean(0)])
        return top - TZ, upper[:, :2].mean(0)

    async def pick(self, item):
        """Hover, look, descend, grab, lift. Returns (held, item, t_cmd) with t_cmd = first motion command."""
        self.state("PICK")
        t_cmd = None
        theta_extra = 0.0
        self.upright = 0.0                 # mm of part hanging past the fingertips when held in line (0: held across)
        squat = round_part(item)
        # The top image now comes from the camera-centred look pose, so the gripper hover only has to be high where the
        # depth look needs range (squat parts: nut flat or a part standing). Long parts: the low hover (no down-up-down).
        hz = HOVER_HIGH_Z if squat else HOVER_Z
        # collect mode: one grasp attempt only. 19:03 a short hex bolt was stabbed 3x per item, nudged each time, and the
        # closing fingertips tore the cardboard pad. A miss in collect mode stops the run (see cycle()).
        retries = 0 if self.args.mode == "collect" else G["retries"]
        for attempt in range(1, 2 + retries):
            heading = item[3] + G["jaw_offset_deg"] + theta_extra
            if attempt == 1:
                sound("Ping")
            t = await self.jmove(self.look_joints(item), f"look {attempt}", holding=False)   # FIRST MOTION
            t_cmd = t_cmd or t
            new, tape = await self.look(item, attempt, heading)
            if new is None:
                self.tel.emit("recovery", level="L1", what=f"part not seen from hover (attempt {attempt}): back to watch, no grab")
                print(f"  part not seen from hover: not grabbing")
                self.not_seen = True
                return False, item, t_cmd
            self.top_tape = tape
            item = new
            height = None
            # hover with the gripper (not the camera) over the part, jaws across it. The depth look for squat parts
            # runs from here: depth needs > ~28 cm range at 1280x720, more than the camera-centred look gives.
            heading = item[3] + G["jaw_offset_deg"] + theta_extra
            q, _, _ = ik(np.array([item[0], item[1], hz]), seed=self.q, jaw_heading_deg=heading)
            await self.jmove(q, f"hover {attempt}", holding=False)
            # --assume-lying: an operator laid the part flat (collect). The depth height read 42-48 mm for flat parts
            # (18:58 hex_bolt_short, 17:37 diagonal bolt), so for squat parts it skipped good picks.
            if squat and attempt == 1 and not getattr(self.args, "assume_lying", False):
                height, dxy = await self.depth_look(item[:2])
                print(f"  height from depth: {height if height is None else round(height)} mm")
                if height and height > STANDING_MM and dxy is not None and not self.args.allow_upright:
                    # 15:48 an upright bolt hit the gripper body on the way down (E-stop). Until the grasp height
                    # keeps the part top below the palm (measured), leave upright parts where they are.
                    self.skip_reason = f"upright part ({height:.0f} mm tall): not picked, upright grasp disabled"
                    self.ignore_xy.append((float(dxy[0]), float(dxy[1])))
                    self.tel.emit("recovery", level="L1", what=self.skip_reason)
                    print("  " + self.skip_reason)
                    return False, item, t_cmd
                if height and height > STANDING_MM and dxy is not None:
                    self.upright = height
                    item = (float(dxy[0]), float(dxy[1])) + tuple(item[2:])
                    self.tel.emit("note", step="standing", height=round(height, 1), x=item[0], y=item[1])
                    q, _, _ = ik(np.array([item[0], item[1], hz]), seed=self.q, jaw_heading_deg=heading)
                    await self.jmove(q, f"aim upright {attempt}", holding=False)
            if await self.mv.finger_pos() < 780:
                with self.tel.span("open", phase="pick", item=self.n):
                    await self.release()
            # lying: closed tips 2 mm above the table; standing: halfway up (vh.motion.grasp_height, Pranav's rule)
            gz = grasp_height(SimpleNamespace(top_z=TZ + 10), TZ, G)
            if self.upright:                                         # Pranav's halfway rule, for any upright part
                gz = TZ + self.upright / 2 + G["tcp_to_tip_mm"]
            self.pose = "upright" if self.upright else "lying"
            if self.upright:
                self.upright = (gz - G["tcp_to_tip_mm"]) - TZ      # what hangs below the tips once lifted
            await self.straight(item[0], item[1], gz, f"descend {attempt}")
            with self.tel.span(f"grab {attempt}", phase="grab", item=self.n):
                pos = await self.mv.grab()
            self.state("LIFT")
            await self.straight(item[0], item[1], LIFT_Z, f"lift {attempt}")
            pl = await self.mv.finger_pos()
            ok = held(pl, G)
            self.tel.emit("gripper", pos=pl, holding=ok)
            self.tel.emit("grasp_result", n=self.n, ok=bool(ok), pos=pl, holding=ok, attempt=attempt, expected_pos=None)
            if ok:
                self.grasp_z = gz
                return True, item, t_cmd
            with self.tel.span("open", phase="pick", item=self.n):
                await self.release()
            theta_extra += 90.0
            self.tel.emit("recovery", level="L1", what=f"missed grasp {attempt}: retry with the jaws turned 90 deg")
        return False, item, t_cmd

    async def inspect(self):
        """Webcam views at the checkpoint. Returns the decision (sort mode decides after every view)."""
        scores = {}
        decision, reason, at = None, None, None
        top, top_box = await self.infer_crop(self.top_image, self.top_bbox, "top")
        scores["top"] = {**top.fields(), "anomaly": top.score, "tape": self.top_tape}
        self.emit_anomaly("top", top, top_box)
        if self.args.mode == "sort" and self.top_tape is not None and self.top_tape > TAPE_FRAC:
            # A top-view decision still travels to a checkpoint before releasing into reject.
            decision, reason, at = "reject", f"known: tape (top face, {100 * self.top_tape:.1f}% of part)", "top"
        elif self.args.mode == "sort" and top.fields()["anomalous"]:
            decision, reason, at = "reject", reject_reason(scores, ["top"]), "top"
        hold = self.upright or True
        order = UPRIGHT_ORDER if self.upright else VIEW_ORDER
        vj = UPRIGHT_J if self.upright else VIEW_J
        self.state("INSPECT", views=order, pose=self.pose)
        for name in order:
            try:
                await self.jmove(vj[name], f"view {name}", holding=hold)
            except RuntimeError as e:              # path blocked for this part: skip the view, keep going
                self.tel.emit("recovery", level="L1", what=f"view {name} skipped: {e}")
                print(f"  view {name} skipped: {e}")
                continue
            t0 = time.perf_counter()
            jpg = await self.web_jpeg()
            ms = (time.perf_counter() - t0) * 1000
            p, z = fk_tcp(vj[name])
            u, v = project(p + z * (20 + 0.5 * self.upright))
            box = [int(max(0, u - 260)), int(max(0, v - 330)), int(min(1920, u + 260)), int(min(1080, v + 330))]
            crop = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))[box[1]:box[3], box[0]:box[2]]
            tape = tape_fraction(crop)
            (self.idir / f"web_{name}.jpg").write_bytes(jpg)
            Image.fromarray(crop).save(self.idir / f"crop_{name}.jpg", quality=92)
            result, model_box = await self.infer_crop(jpg, box, name)
            anomaly = result.score
            scores[name] = {"tape": round(tape, 4), "anomaly": anomaly, "frame_ms": round(ms), **result.fields()}
            self.meta.setdefault("views", {})[name] = {"crop_box": box, "joints_deg": [round(v, 2) for v in vj[name]],
                                                       "tcp": [round(float(c), 1) for c in p], "tool_axis": [round(float(c), 3) for c in z]}
            jaw = await self.mv.finger_pos()
            self.meta["views"][name]["jaw"] = jaw
            self.tel.emit("view", frame=jpg, n=self.n, view=name, crop=box, tape=tape, anomaly=anomaly, frame_ms=round(ms), jaw=jaw)
            self.emit_anomaly(name, result, model_box)
            if not held(jaw, G):
                self.tel.emit("recovery", level="L2", what=f"part dropped during view {name}")
                return "dropped", f"dropped during view {name}", name, scores
            if self.args.mode == "sort" and not decision and tape > TAPE_FRAC_WEB:
                decision, reason, at = "reject", f"known: tape ({name}, {100 * tape:.1f}% of crop)", name
            elif self.args.mode == "sort" and not decision and result.fields()["anomalous"] and getattr(self.args, "decide", "all") == "all":
                decision, reason, at = "reject", reject_reason(scores, [name]), name
            if decision:
                break
        if not any(name in scores for name in order):
            raise RuntimeError("No inspection checkpoint reached; refusing to release over the pickup area")
        if self.args.mode == "collect":
            return "collect", self.args.label, None, scores
        if not decision:
            # --decide top: the webcam anomaly scores are logged as evidence only (crop under rework, 17:58)
            uncertain = reject_reason(scores, ["top", *order] if getattr(self.args, "decide", "all") == "all" else ["top"])
            decision, reason, at = ("reject", uncertain, "fusion") if uncertain else ("good", "all required anomaly views below threshold; no tape", "fusion")
        return decision, reason, at, scores

    async def capture_refs(self):
        """Every webcam view with the EMPTY gripper (fingers open): the fixed background each view's part mask is
        differenced against (config/webcam_refs/<view>.jpg). The fingers close to the part's width when holding, so
        the mask also ignores the finger region (known from the projected TCP)."""
        out = ROOT / "config" / "webcam_refs"
        out.mkdir(exist_ok=True)
        self.state("REFS")
        if await self.mv.finger_pos() < 780:
            await self.release()
        for vj, order in ((VIEW_J, VIEW_ORDER), (UPRIGHT_J, UPRIGHT_ORDER)):
            for name in order:
                try:
                    await self.jmove(vj[name], f"ref {name}", holding=False)
                except RuntimeError as e:
                    print(f"  ref {name} skipped: {e}")
                    continue
                jpg = await self.web_jpeg()
                (out / f"{name}.jpg").write_bytes(jpg)
                self.tel.emit("view", frame=jpg, n=0, view=name, crop=[0, 0, 1920, 1080], tape=0.0, anomaly=None, frame_ms=0,
                              jaw=await self.mv.finger_pos())
        await self.jmove(WATCH_J, "return", holding=False)
        print(f"  empty-gripper references -> {out}")

    async def place_back(self):
        """Collect mode: put the part on the pad at a new random spot and angle."""
        self.state("PLACE")
        sound("Ping")
        r = self.pad
        # Keep >= 60 mm inside the zone in y: near the pad edge the white table enters the 190 mm look frame and the
        # part merges with the background-edge band (18:40, button screw set down at y 233 -> unseen from the look).
        x = random.uniform(r["x_min"] + 40, r["x_max"] - 40)
        y = random.uniform(r["y_min"] + 60, r["y_max"] - 60)
        q, _, _ = ik(np.array([x, y, LIFT_Z]), seed=WATCH_J, jaw_heading_deg=random.uniform(0, 180))
        await self.jmove(q, "over pad", holding=self.upright or True)
        # set it down (upright parts stay upright) or let go 20-35 mm up so it lands on a random face / tips over
        how = random.choice(["set", "drop"]) if self.args.drops else "set"   # round parts roll ~12 cm when dropped
        drop = 3.0 if how == "set" else random.uniform(20, 35)
        self.meta["placed_next"] = {"x": round(x, 1), "y": round(y, 1), "how": how, "release_above_mm": round(drop, 1)}
        await self.straight(x, y, self.grasp_z + drop, "lower")
        with self.tel.span(f"release ({how})", phase="place", item=self.n):
            await self.release()
        await self.straight(x, y, HOVER_Z, "retreat")

    async def cycle(self):
        self.n += 1
        self.idir = self.dir / f"item_{self.n:03d}"
        self.idir.mkdir()
        self.meta = {"item": self.n, "label": self.args.label, "type": self.args.type, "mode": self.args.mode,
                     "background": self.args.background, "camera": getattr(self, "camera_settings", None)}
        self._watch_start = time.time()
        item, t_app, t_stable, watch_jpg = await self.watch()
        if item is None:
            return False
        (self.idir / "watch.jpg").write_bytes(watch_jpg)
        self.not_seen, self.skip_reason = False, None
        ok, item, t_cmd = await self.pick(item)
        lat = {"n": self.n, "t_appeared": t_app, "t_stable": t_stable, "t_cmd": t_cmd, "t_moving": t_cmd,
               "ms_to_stable": round((t_stable - t_app) * 1000), "ms_to_cmd": round((t_cmd - t_app) * 1000),
               "ms_to_motion": round((t_cmd - t_app) * 1000)}
        self.tel.emit("latency", **lat)
        rec = {"item": self.n, "t_seen": iso(t_app), "t_first_motion": iso(t_cmd), "latency_ms": lat["ms_to_motion"],
               "pick_xy": [round(item[0], 1), round(item[1], 1)], "yaw": round(item[3], 1)}
        if not ok:
            rec.update(decision="none", reason=self.skip_reason or ("part not seen from hover" if self.not_seen else "could not grasp"),
                       t_decided=iso(time.time()))
            if self.args.mode == "sort" and self.skip_reason and getattr(self, "top_image", None) and self.top_bbox:
                # left in place (upright grasp disabled), but the top image was taken: decide from it, mark not moved
                top, _ = await self.infer_crop(self.top_image, self.top_bbox, "top")
                f = top.fields()
                rec.update(decision="reject" if f["anomalous"] is not False else "good", picked=False,
                           reason=f"{self.skip_reason}; top {f['status']} {f['score'] and round(f['score'], 2)} / "
                                  f"{f['threshold'] and round(f['threshold'], 2)} {f['detail'] or ''}",
                           scores={"top": f}, confidence=None)
            if self.gripper and await self.mv.finger_pos() < 780:
                await self.release()
            self.finish(rec)
            await self.jmove(WATCH_J, "return", holding=False)
            # 18:40: the same unseen part was retried 10x in a row. Two misses on the same spot: stop and ask a human.
            if self.args.mode == "collect" and not self.not_seen:
                print("  STOP: missed grasp in collect mode; check the part and the pad, then rerun")
                return False
            prev, self.last_miss = getattr(self, "last_miss", None), (item[0], item[1])
            if prev and math.dist(prev, self.last_miss) < 15:
                print(f"  STOP: part at ({item[0]:.0f}, {item[1]:.0f}) failed twice in a row; move it toward the pad centre and rerun")
                return False
            return True
        self.last_miss = None
        decision, reason, at, scores = await self.inspect()
        t_dec = time.time()
        rec.update(decision=decision, reason=reason, decided_at_view=at, scores=scores, t_decided=iso(t_dec),
                   top_tape=self.top_tape, pose=self.pose, height_mm=round(self.upright, 1) if self.upright else None)
        if self.args.mode == "collect":
            rec.update(label=self.args.label, type=self.args.type)
        if self.args.mode == "sort":
            self.state("DECIDE")
        self.tel.emit("decision", n=self.n, decision=decision, reason=reason, at=at, scores=scores,
                      ms_from_seen=round((t_dec - t_app) * 1000))
        if decision == "reject":
            self.state("DROP", decision="reject")
            with self.tel.span("release (reject)", phase="drop", item=self.n):
                await self.release()
        elif decision == "good":
            self.state("DROP", decision="good")
            await self.jmove(self.good_j_up if self.upright else self.good_j, "to good", holding=self.upright or True)
            with self.tel.span("release (good)", phase="drop", item=self.n):
                await self.release()
        elif decision == "collect":
            await self.place_back()
        rec["t_released"] = iso(time.time())
        self.state("RETURN")
        await self.jmove(WATCH_J, "return", holding=False)
        rec["cycle_s"] = round(time.time() - t_app, 2)
        self.finish(rec)
        return True

    def finish(self, rec):
        self.judge.write(json.dumps(rec) + "\n")
        self.meta.update(pose=getattr(self, "pose", None), height_mm=rec.get("height_mm"), decision=rec.get("decision"),
                         grasp_tcp_z=getattr(self, "grasp_z", None))
        (self.idir / "meta.json").write_text(json.dumps(self.meta, indent=1, default=float))
        self.tel.emit("cycle", item=self.n, result=rec["decision"], decision=f'{rec["decision"]}: {rec["reason"]}',
                      latency_ms=rec["latency_ms"], recoveries=0, t_first_motion=rec["t_first_motion"], shape=self.args.type,
                      cycle_s=rec.get("cycle_s"), scores=rec.get("scores"))
        print(f"[{self.n}] {rec['decision']}: {rec['reason']} · latency {rec['latency_ms']} ms · cycle {rec.get('cycle_s')} s", flush=True)

    async def set_camera(self):
        """Apply WRIST_V4L2 on the station and refuse to run unless the read-back and frame size match."""
        sets = " ".join(f"--set-ctrl {k}={v}" for k, v in WRIST_V4L2.items())
        rc, out = await station_exec(self.m, f"v4l2-ctl -d {WRIST_DEV} {sets} && v4l2-ctl -d {WRIST_DEV} "
                                             f"--get-ctrl {','.join(WRIST_V4L2)}", 30)
        got = {ln.split(":")[0].strip(): int(ln.split(":")[1].split()[0]) for ln in out.splitlines() if ":" in ln}
        if rc or any(got.get(k) != v for k, v in WRIST_V4L2.items()):
            raise SystemExit(f"wrist camera controls not applied: {out}")
        k = (await Camera.from_robot(self.m, "cam").get_properties()).intrinsic_parameters
        self.camera_settings = {**got, "width_px": k.width_px, "height_px": k.height_px, "fx": round(k.focal_x_px, 2)}
        if (k.width_px, k.height_px) != (1280, 720):
            raise SystemExit(f"wrist camera is {k.width_px}x{k.height_px}, expected 1280x720 (fresh dataset)")
        print("wrist camera", self.camera_settings, flush=True)

    async def run(self):
        a = self.args
        self.tel.emit("run", cmd=f"sort.py --mode {a.mode}", live=True, release=a.mode, states=STATES_SORT if a.mode == "sort" else STATES_COLLECT, views=VIEW_ORDER,
                      label=a.label, type=a.type, platform=sys.platform, host=socket.gethostname())
        if (await Generic.from_robot(self.m, "teleop").do_command({"command": "status"})).get("running"):
            raise SystemExit("teleop is running: someone else is driving")
        j0 = await self.joints(); await asyncio.sleep(1)
        if max(abs(x - y) for x, y in zip(j0, await self.joints())) > 0.2:
            raise SystemExit("arm moving: someone else is driving")
        print("WARNING: arm about to move"); sound("Sosumi"); say("Robot arm moving. Stand clear.")
        if sys.platform != "darwin":
            await asyncio.sleep(2.5)          # the laptop dashboard speaks the warning (it got the run event); let it finish
        await self.set_camera()
        if await self.mv.finger_pos() < 780:
            await self.release()
        p, _ = fk_tcp(self.q)
        if math.dist(p, fk_tcp(WATCH_J)[0]) > 5:
            # first move of the run: from wherever the arm is, via the planner (unknown start)
            wp, _ = fk_tcp(WATCH_J)
            await self.mv.to(float(wp[0]), float(wp[1]), float(wp[2]), 0, "to watch pose (planner)")
            await self.jmove(WATCH_J, "watch (exact joints)", holding=False)
        if a.refs:
            await self.capture_refs()
        count = a.reps if a.mode == "collect" else a.items
        self.joint_speed = self.joint_accel = None
        await self.set_joint_speed(NORMAL_SPEED, RUN_ACCEL if a.tcp_limit else NORMAL_ACCEL)
        try:
            for _ in range(count):
                if not await self.cycle():
                    break
        finally:
            try:   # also after an error: never leave the arm faster than the module defaults
                await self.set_joint_speed(NORMAL_SPEED, NORMAL_ACCEL)
            except Exception as e:
                print(f"  could not restore the arm speed ({e}): arm DoCommand set_speed 60, set_acceleration 381.67")
            self.state("IDLE")
            print("telemetry", self.tel.report(), "->", self.dir)


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["sort", "collect"], required=True)
    p.add_argument("--items", type=int, default=6, help="sort: items to process")
    p.add_argument("--reps", type=int, default=5, help="collect: picks of the same part (placed anew each time)")
    p.add_argument("--label", default="unlabeled", help="collect: good | tape | other:<what>")
    p.add_argument("--type", default="unknown", help="collect: part type, e.g. socket_m16_long")
    p.add_argument("--dash-host", default="127.0.0.1")
    p.add_argument("--anomaly-bundle", type=Path, help="Per-type/view bundle.json, or 'active' (models/ACTIVE, set from the training dashboard); without a model, sort mode rejects as uncertain")
    p.add_argument("--anomaly-device", choices=["CPU", "GPU", "NPU"], default="CPU")
    p.add_argument("--background", choices=["white", "cardboard"], default="white", help="Must match the model's training background")
    p.add_argument("--drops", action="store_true", help="collect: half the time let go 20-35 mm up (random face); "
                   "only for parts that don't roll (hex nuts, hex bolts)")
    p.add_argument("--allow-upright", action="store_true", help="grasp upright parts (UNSAFE: hit the gripper 15:48)")
    p.add_argument("--assume-lying", action="store_true", help="collect: skip the depth upright check (operator lays parts flat)")
    p.add_argument("--decide", choices=["all", "top"], default="all",
                   help="sort: which anomaly views can reject (top = wrist top view only; webcam scores logged as evidence)")
    p.add_argument("--tcp-limit", type=float, default=900.0, metavar="MM_S",
                   help="per joint move: the fastest joint speed (<= 180 deg/s) whose peak tool speed stays under this; "
                        "the xArm firmware's TCP limit is 1000 mm/s. 0 = off (60 deg/s for every move)")
    p.add_argument("--tcp-limit-holding", type=float, default=800.0, metavar="MM_S",
                   help="the same limit while a part is in the gripper (it can swing loose)")
    p.add_argument("--refs", action="store_true", help="first capture every webcam view with the EMPTY gripper")
    p.add_argument("--watch-timeout", type=float, default=120, help="give up waiting for a part after this many s")
    a = p.parse_args()
    if a.tcp_limit and not (0 < a.tcp_limit_holding <= a.tcp_limit <= 1000):
        raise SystemExit("need 0 < --tcp-limit-holding <= --tcp-limit <= 1000 mm/s (the xArm firmware's TCP limit)")
    global TZ, HOVER_Z, ZONE        # every pick height, the planner's table and the zone follow the pick surface
    if a.background not in SURFACE_Z:
        raise SystemExit(f"no measured surface_z for {a.background!r} in config/poses.json")
    TZ, ZONE = SURFACE_Z[a.background], ZONES[a.background]
    HOVER_Z = TZ + 10 + G["approach_height_mm"]
    print(f"surface {a.background}: z {TZ} mm, pick zone {ZONE}", flush=True)
    ik(np.array([300.0, 300.0, 200.0]))          # warm up scipy (first call ~0.4 s)
    async with await connect() as m:
        await Sorter(m, a).run()


if __name__ == "__main__":
    asyncio.run(main())
