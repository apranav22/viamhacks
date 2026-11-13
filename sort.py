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
height, jaw direction, held check and retries come from pipeline.py and config/poses.json unchanged.

Every stage is sent to the dashboard as UDP telemetry (vh/telemetry.py: non-blocking, measured in microseconds).
Every decision is written to runs/<run>/decisions.jsonl with ms timestamps (the judge log).
"""

import argparse
import asyncio
import io
import json
import math
import random
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

from viam.proto.common import GeometriesInFrame, WorldState
from viam.proto.component.arm import JointPositions
from pipeline import Mover, box, cam_to_world, grasp_height, held, world_state
from screws import WristView, detect
from station import connect
from vh.kinematics import check_path, flip, ik, load_obstacles, tcp as fk_tcp
from vh.telemetry import Telemetry

POSES = json.load(open(ROOT / "config" / "poses.json"))
CP = json.load(open(ROOT / "config" / "checkpoint.json"))
G = POSES["grasp"]
TZ = G["table_z"]
PAD = CP["pick_pad"]["pick_region"]
WATCH_J = CP["watch_pose"]["joints_deg"]
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
ZONE = {"x_min": 220, "x_max": 450, "y_min": 260, "y_max": 410}   # pick zone on the bare table (kit storage starts ~y 470)
STILL_S = 0.3                       # part unchanged this long ...
HAND_FRAC, HAND_HOLDOFF_S = 0.02, 0.8   # ... and no hand (2% of the frame changed outside the pad) for 0.8 s
TAPE_FRAC = 0.02                    # share of the part crop that is tape-blue to call it "known: tape"
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
    return datetime.fromtimestamp(t).isoformat(timespec="milliseconds")


def tape_fraction(rgb):
    """Share of pixels that are saturated blue (painter's tape), not the cyan-ish zinc of the plated parts."""
    f = rgb.astype(np.float32) / 255
    mx, mn = f.max(-1), f.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    hue_blue = (b == mx) & (b - np.maximum(r, g) > 0.12) & (r < g)          # blue dominant, not violet
    blue = hue_blue & (sat > 0.45) & (mx > 0.25) & ((b - g) > 0.6 * (b - r))    # deep blue, not cyan (g close to b)
    return float(blue.mean())


def find_pad(rgb, view):
    """The brown cardboard pick pad, found in the watch frame (people move it): its interior as a world-xy region."""
    from scipy import ndimage
    f = rgb.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mask = (r > g) & (g > b) & (r - b > 25) & (r < 235)
    mask = ndimage.binary_opening(mask, iterations=2)
    lab, n = ndimage.label(mask)
    if not n:
        return None
    k = 1 + int(np.argmax(ndimage.sum(mask, lab, range(1, n + 1))))
    ys, xs = np.nonzero(lab == k)
    if len(xs) < 5000:
        return None
    m = 12                                   # stay off the pad's edge
    corners = [view.to_world(u, v, view.table_z) for u, v in ((xs.min() + m, ys.min() + m), (xs.max() - m, ys.min() + m),
                                                            (xs.min() + m, ys.max() - m), (xs.max() - m, ys.max() - m))]
    X, Y = [c[0] for c in corners], [c[1] for c in corners]
    return {"x_min": float(min(X)), "x_max": float(max(X)), "y_min": float(min(Y)), "y_max": float(max(Y)),
            "px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}


PAD_MM = (232, 129)       # the cardboard pad, measured 14:50


def pad_plausible(pad):
    a, b = pad["x_max"] - pad["x_min"], pad["y_max"] - pad["y_min"]
    return 80 < a < 1.3 * PAD_MM[0] and 80 < b < 1.3 * PAD_MM[1]     # may run off the frame edge


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
    return [int(max(0, min(us))), int(max(0, min(vs))), int(min(640, max(us))), int(min(480, max(vs)))]


def round_part(it):
    """Nuts and other squat parts: their long-axis angle is noise, so it doesn't count for 'still'."""
    x0, y0, x1, y1 = it[4]
    return max(x1 - x0, y1 - y0) < 1.4 * max(1, min(x1 - x0, y1 - y0))


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
        self.obs = load_obstacles()
        self.run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + args.mode
        self.dir = ROOT / "runs" / self.run_id
        self.dir.mkdir(parents=True)
        self.tel = Telemetry(host=args.dash_host, run_id=self.run_id)
        self.judge = open(self.dir / "decisions.jsonl", "a", buffering=1)
        self.q = None                 # last known joints
        self.n = 0
        self.good_j = ik(np.array(GOOD_TCP), seed=VIEW_J["front"])[0]
        self.good_j_up = ik(np.array(GOOD_TCP[:2] + (300.0,)), seed=UPRIGHT_J["side-120"])[0]   # hanging part clears the divider
        self.view = None              # WristView at the watch pose (fixed: computed once)
        self.pad = dict(PAD)          # replaced by the pad found in the first watch frame
        extra = [box(n, *c, *d) for n, (c, d) in self.obs[4:]]     # tripod, lamp, box (for the one planner move)
        self.mv.ws = WorldState(obstacles=list(world_state(TZ).obstacles) + [GeometriesInFrame(reference_frame="world", geometries=extra)])

    # ---- helpers ---------------------------------------------------------------------------------
    def state(self, s, **kw):
        self.tel.state(s, item=self.n, **kw)
        print(f"[{self.n}] {s}", flush=True)

    async def joints(self):
        self.q = [float(v) for v in (await self.arm.get_joint_positions()).values]
        return self.q

    async def jmove(self, q, label, holding):
        """Joint move to q after checking the joint-space path against the obstacles."""
        q0 = self.q or await self.joints()
        ok, c, where = check_path(q0, q, self.obs, holding=holding, margin=0)
        if not ok:
            self.tel.emit("error", msg=f"{label}: path blocked ({c} mm, {where}); not moving")
            raise RuntimeError(f"{label}: joint path would hit {where} ({c} mm)")
        t = time.time()
        p, _ = fk_tcp(q)
        self.tel.emit("move", label=label, component="arm", joints=[round(v, 1) for v in q], target={"x": p[0], "y": p[1], "z": p[2]},
                      clearance_mm=c)
        with self.tel.span(label, phase=label.split()[0], item=self.n):
            await self.arm.move_to_joint_positions(JointPositions(values=list(q)))
        self.q = list(q)
        return t

    async def straight(self, x, y, z, label):
        with self.tel.span(label, phase=label.split()[0], item=self.n):
            await self.mv.straight(x, y, z, label)
        self.q = None

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
            rot, t = await cam_to_world(self.m)
            k = (await self.cam.get_properties()).intrinsic_parameters
            self.view = WristView(k, rot, t, TZ)
            self.ref = np.asarray(Image.open(io.BytesIO(await self.wrist_jpeg())).convert("RGB"))
            # Fixed pick zone on the bare table. No cardboard pad: the grasp goes 2 mm above the TABLE, so a pad
            # thicker than that gets pinched and dragged (it moved ~10 cm in 3 picks at 15:15).
            self.pad = dict(ZONE)
            self.pad["px"] = zone_px(self.view, ZONE)
            self.zone = self.pad
            print(f"pick zone x {ZONE['x_min']}..{ZONE['x_max']}, y {ZONE['y_min']}..{ZONE['y_max']} (pixels {self.pad['px']})")
            self.tel.emit("note", step="pick pad", **{k: round(v) if isinstance(v, float) else v for k, v in self.pad.items()})
        last, t_appeared, still_since, hand_until = None, None, None, 0.0
        while True:
            t0 = time.perf_counter()
            jpg = await self.wrist_jpeg()
            t1 = time.perf_counter()
            rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
            items = sorted(detect(rgb, self.view, self.zone), key=lambda it: -it[2])
            t2 = time.perf_counter()
            it = items[0] if items else None
            now = time.time()
            if it and t_appeared is None:
                t_appeared = now
            if not it:
                t_appeared, last = None, None
            hand = outside_change(rgb, self.ref, self.pad["px"]) > HAND_FRAC
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

    async def look(self, item, attempt, heading):
        """Look again from hover (0.45 mm/px): position and angle of the same part. Saves the top-face image."""
        jpg, (rot, t), props = await asyncio.gather(self.wrist_jpeg(), cam_to_world(self.m), self.cam.get_properties())
        view = WristView(props.intrinsic_parameters, rot, t, TZ)
        rgb = np.asarray(Image.open(io.BytesIO(jpg)).convert("RGB"))
        near = [it for it in detect(rgb, view, None) if math.dist(it[:2], item[:2]) < 60]
        new = min(near, key=lambda it: math.dist(it[:2], item[:2])) if near else None
        tape = None
        if new:
            x0, y0, x1, y1 = new[4]
            tape = tape_fraction(rgb[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6])
        (self.idir / f"top_{attempt}.jpg").write_bytes(jpg)
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
        hz = HOVER_HIGH_Z if squat else HOVER_Z
        for attempt in range(1, 2 + G["retries"]):
            heading = item[3] + G["jaw_offset_deg"] + theta_extra
            q, err, _ = ik(np.array([item[0], item[1], hz]), seed=self.q or WATCH_J, jaw_heading_deg=heading)
            if attempt == 1:
                sound("Ping")
            t = await self.jmove(q, f"hover {attempt}", holding=False)
            t_cmd = t_cmd or t
            new, tape = await self.look(item, attempt, heading)
            if new is None:
                self.tel.emit("recovery", level="L1", what=f"part not seen from hover (attempt {attempt}): back to watch, no grab")
                print(f"  part not seen from hover: not grabbing")
                self.not_seen = True
                return False, item, t_cmd
            self.top_tape = tape
            shift = math.dist(new[:2], item[:2])
            turn = abs((new[3] - item[3] + 90) % 180 - 90)
            item = new
            height = None
            if squat and attempt == 1:
                height, dxy = await self.depth_look(item[:2])
                print(f"  height from depth: {height if height is None else round(height)} mm")
                if height and height > STANDING_MM and dxy is not None:
                    self.upright = height
                    item = (float(dxy[0]), float(dxy[1])) + tuple(item[2:])
                    shift = 99.0
                    self.tel.emit("note", step="standing", height=round(height, 1), x=item[0], y=item[1])
            if shift > 2.0 or turn > 4.0:
                heading = item[3] + G["jaw_offset_deg"] + theta_extra
                q, _, _ = ik(np.array([item[0], item[1], hz]), seed=self.q, jaw_heading_deg=heading)
                await self.jmove(q, f"aim {attempt}", holding=False)
            if await self.mv.finger_pos() < 780:
                with self.tel.span("open", phase="pick", item=self.n):
                    await self.release()
            # lying: closed tips 2 mm above the table; standing: halfway up (pipeline.grasp_height, Pranav's rule)
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
        if self.args.mode == "sort" and self.top_tape is not None and self.top_tape > TAPE_FRAC:
            # decided from the hover look; still go to the first view: it is over the reject compartment
            decision, reason, at = "reject", f"known: tape (top face, {100 * self.top_tape:.1f}% of part)", "top"
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
            anomaly = None            # PatchCore score goes here once trained (per type, per view)
            scores[name] = {"tape": round(tape, 4), "anomaly": anomaly, "frame_ms": round(ms)}
            jaw = await self.mv.finger_pos()
            self.tel.emit("view", frame=jpg, n=self.n, view=name, crop=box, tape=tape, anomaly=anomaly, frame_ms=round(ms), jaw=jaw)
            if not held(jaw, G):
                self.tel.emit("recovery", level="L2", what=f"part dropped during view {name}")
                return "dropped", f"dropped during view {name}", name, scores
            if self.args.mode == "sort" and not decision and tape > TAPE_FRAC:
                decision, reason, at = "reject", f"known: tape ({name}, {100 * tape:.1f}% of crop)", name
            if decision:
                break
        if self.args.mode == "collect":
            return "collect", self.args.label, None, scores
        if not decision:
            decision, reason, at = "good", "no tape in any view; anomaly model not loaded yet", order[-1]
        return decision, reason, at, scores

    async def place_back(self):
        """Collect mode: put the part on the pad at a new random spot and angle."""
        self.state("PLACE")
        sound("Ping")
        r = self.pad
        x = random.uniform(r["x_min"] + 40, r["x_max"] - 40)
        y = random.uniform(r["y_min"] + 30, r["y_max"] - 30)
        q, _, _ = ik(np.array([x, y, LIFT_Z]), seed=WATCH_J, jaw_heading_deg=random.uniform(0, 180))
        await self.jmove(q, "over pad", holding=self.upright or True)
        await self.straight(x, y, self.grasp_z + 3, "lower")
        with self.tel.span("release", phase="place", item=self.n):
            await self.release()
        await self.straight(x, y, HOVER_Z, "retreat")

    async def cycle(self):
        self.n += 1
        self.idir = self.dir / f"item_{self.n:03d}"
        self.idir.mkdir()
        self._watch_start = time.time()
        item, t_app, t_stable, watch_jpg = await self.watch()
        if item is None:
            return False
        (self.idir / "watch.jpg").write_bytes(watch_jpg)
        self.not_seen = False
        ok, item, t_cmd = await self.pick(item)
        lat = {"n": self.n, "t_appeared": t_app, "t_stable": t_stable, "t_cmd": t_cmd, "t_moving": t_cmd,
               "ms_to_stable": round((t_stable - t_app) * 1000), "ms_to_cmd": round((t_cmd - t_app) * 1000),
               "ms_to_motion": round((t_cmd - t_app) * 1000)}
        self.tel.emit("latency", **lat)
        rec = {"item": self.n, "t_seen": iso(t_app), "t_first_motion": iso(t_cmd), "latency_ms": lat["ms_to_motion"],
               "pick_xy": [round(item[0], 1), round(item[1], 1)], "yaw": round(item[3], 1)}
        if not ok:
            rec.update(decision="none", reason="part not seen from hover" if self.not_seen else "could not grasp",
                       t_decided=iso(time.time()))
            if self.gripper and await self.mv.finger_pos() < 780:
                await self.release()
            self.finish(rec)
            await self.jmove(WATCH_J, "return", holding=False)
            return True
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
        self.tel.emit("cycle", item=self.n, result=rec["decision"], decision=f'{rec["decision"]}: {rec["reason"]}',
                      latency_ms=rec["latency_ms"], recoveries=0, t_first_motion=rec["t_first_motion"], shape=self.args.type,
                      cycle_s=rec.get("cycle_s"), scores=rec.get("scores"))
        print(f"[{self.n}] {rec['decision']}: {rec['reason']} · latency {rec['latency_ms']} ms · cycle {rec.get('cycle_s')} s", flush=True)

    async def run(self):
        a = self.args
        self.tel.emit("run", cmd=f"sort.py --mode {a.mode}", live=True, release=a.mode, states=STATES_SORT if a.mode == "sort" else STATES_COLLECT, views=VIEW_ORDER,
                      label=a.label, type=a.type)
        if (await Generic.from_robot(self.m, "teleop").do_command({"command": "status"})).get("running"):
            raise SystemExit("teleop is running: someone else is driving")
        j0 = await self.joints(); await asyncio.sleep(1)
        if max(abs(x - y) for x, y in zip(j0, await self.joints())) > 0.2:
            raise SystemExit("arm moving: someone else is driving")
        print("WARNING: arm about to move"); sound("Sosumi"); say("Robot arm moving. Stand clear.")
        if await self.mv.finger_pos() < 780:
            await self.release()
        p, _ = fk_tcp(self.q)
        if math.dist(p, fk_tcp(WATCH_J)[0]) > 5:
            # first move of the run: from wherever the arm is, via the planner (unknown start)
            wp, _ = fk_tcp(WATCH_J)
            await self.mv.to(float(wp[0]), float(wp[1]), float(wp[2]), 0, "to watch pose (planner)")
            await self.jmove(WATCH_J, "watch (exact joints)", holding=False)
        count = a.reps if a.mode == "collect" else a.items
        try:
            for _ in range(count):
                if not await self.cycle():
                    break
        finally:
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
    p.add_argument("--watch-timeout", type=float, default=120, help="give up waiting for a part after this many s")
    a = p.parse_args()
    ik(np.array([300.0, 300.0, 200.0]))          # warm up scipy (first call ~0.4 s)
    async with await connect() as m:
        await Sorter(m, a).run()


if __name__ == "__main__":
    asyncio.run(main())
