"""The static overview-cam as a feedback sensor for motion: it sees the item and the gripper claws in
the same image, whatever the arm is doing.

    python overview.py selftest                    # offline: camera model + tracker on synthetic data
    python overview.py calibrate                   # dry run of the calibration moves
    python overview.py calibrate --live --step     # move the claws over a 3x3 grid at two heights
    python overview.py watch                       # read-only: print tracked items, save annotated frames
    python overview.py refit logs/overview-calib-X  # redo the analysis on saved raw frames (offline)

Calibration: the claw tip (lowest point of the black claws in the image) is found at known world
points on two horizontal planes. A homography per plane, interpolated in z, maps any world point
in the work area to a pixel and a pixel at a known height back to the world. Measure
grasp.tcp_to_tip_mm first (motion_probe.py --touch), because the planes are labelled by tip height.

Feedback (used by motion_probe.py --overview):
    Watcher   background task: frame -> items on the table (world xy) -> Tracker; also the claw tip
    Tracker   follows one item: alpha-beta filter, how long it has been still, lost
    align()   at hover, moves the arm until the seen claw tip is over the seen item (servo)
    guarded() runs a descent and stops the arm if the item is seen moving away
"""

import argparse
import asyncio
import io
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from viam.components.camera import Camera

from tracking import Tracker
from pipeline import HERE, LOG_DIR, POSES_PATH, Mover, gripper_theta, scan, tcp_pose, world_state

CALIB_PATH = os.path.join(HERE, "config", "overview_calib.json")
CAM = "overview-cam"

DARK = 70             # claws are black: gray below this ...
DARK_DIFF = 50        # ... and this much darker than the background frame
ITEM_DIFF = 60        # summed RGB distance from the local background that counts as an item
ITEM_PIXELS = (12, 4000)
ITEM_MIN_GRAY = 80    # darker blobs are the arm's black parts, not fasteners
ARM_MASK_PX = 40      # half-width of the band masked along the gripper axis
ITEM_Z_ABOVE_TABLE = 5


# ---------------------------------------------------------------- camera model

def apply_h(H, pts) -> np.ndarray:
    p = np.c_[np.asarray(pts, float), np.ones(len(pts))] @ H.T
    return p[:, :2] / p[:, 2:]


def fit_h(src, dst) -> np.ndarray:
    """Homography src -> dst (normalized DLT), from >= 4 point pairs."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)

    def norm(p):
        c = p.mean(axis=0)
        s = math.sqrt(2) / np.mean(np.linalg.norm(p - c, axis=1))
        return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])

    ts, td = norm(src), norm(dst)
    a = []
    for (x, y), (u, v) in zip(apply_h(ts, src), apply_h(td, dst)):
        a.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        a.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    h = np.linalg.svd(np.array(a))[2][-1].reshape(3, 3)
    h = np.linalg.inv(td) @ h @ ts
    return h / h[2, 2]


class Model:
    """World (x, y, z) <-> overview pixel, from claw-tip points on two planes z0 < z1."""

    def __init__(self, calib: dict):
        self.calib = calib
        self.table_z = calib["table_z"]
        self.z0, self.z1 = calib["z0"], calib["z1"]
        self.world = np.array(calib["world_xy"], float)
        self.uv0, self.uv1 = np.array(calib["uv0"], float), np.array(calib["uv1"], float)
        self.h0, self.h1 = fit_h(self.world, self.uv0), fit_h(self.world, self.uv1)
        self._cache = {}

    def h_at(self, z: float) -> np.ndarray:
        key = round(z, 1)
        if key not in self._cache:
            t = (z - self.z0) / (self.z1 - self.z0)
            self._cache[key] = fit_h(self.world, self.uv0 + t * (self.uv1 - self.uv0))
        return self._cache[key]

    def to_image(self, x, y, z) -> tuple:
        u, v = apply_h(self.h_at(z), [[x, y]])[0]
        return float(u), float(v)

    def to_world(self, u, v, z) -> tuple:
        x, y = apply_h(np.linalg.inv(self.h_at(z)), [[u, v]])[0]
        return float(x), float(y)

    def height_of(self, u, v, x, y) -> float:
        """The z at which a point above world (x, y) appears at pixel (u, v)."""
        p0, p1 = apply_h(self.h0, [[x, y]])[0], apply_h(self.h1, [[x, y]])[0]
        d = p1 - p0
        return float(self.z0 + np.dot(np.array([u, v]) - p0, d) / np.dot(d, d) * (self.z1 - self.z0))

    def region_polygon(self, region: dict) -> list:
        z = self.table_z + ITEM_Z_ABOVE_TABLE
        corners = [(region["x_min"], region["y_min"]), (region["x_max"], region["y_min"]),
                   (region["x_max"], region["y_max"]), (region["x_min"], region["y_max"])]
        return [self.to_image(x, y, z) for x, y in corners]


MAX_CALIB_ERR_MM = 15  # leave-one-out error above this: the calibration is not usable


def load_model() -> "Model":
    with open(CALIB_PATH) as f:
        calib = json.load(f)
    err = calib.get("loo_err_mm_max")
    if err is None or err > MAX_CALIB_ERR_MM:
        raise SystemExit(f"{CALIB_PATH} is not usable (leave-one-out error {err} mm); rerun overview.py calibrate")
    return Model(calib)


def fit_calib(pts, uv0, uv1, base: dict, max_err_mm=8.0, min_points=6) -> tuple:
    """Fit the two-plane model, dropping the worst point while its leave-one-out error (fit on the
    other points, predict this one) is above max_err_mm. Returns (calib, {point: err})."""
    keep = list(range(len(pts)))

    def loo(i, idx):
        rest = [j for j in idx if j != i]
        m = Model({**base, "world_xy": [pts[j] for j in rest], "uv0": [uv0[j] for j in rest],
                   "uv1": [uv1[j] for j in rest]})
        e0 = math.dist(m.to_world(*uv0[i], base["z0"]), pts[i])
        e1 = math.dist(m.to_world(*uv1[i], base["z1"]), pts[i])
        return max(e0, e1)

    while True:
        errs = {i: loo(i, keep) for i in keep}
        worst = max(errs, key=errs.get)
        if errs[worst] <= max_err_mm or len(keep) <= min_points:
            break
        keep.remove(worst)
    calib = {**base, "world_xy": [pts[i] for i in keep], "uv0": [uv0[i] for i in keep],
             "uv1": [uv1[i] for i in keep], "loo_err_mm_max": round(max(errs.values()), 1)}
    return calib, {tuple(pts[i]): round(e, 1) for i, e in errs.items()}


# ---------------------------------------------------------------- detection

async def grab(machine) -> np.ndarray:
    images, _ = await Camera.from_robot(machine, CAM).get_images()
    img = next(i for i in images if "depth" not in i.name)
    return np.asarray(Image.open(io.BytesIO(img.data)).convert("RGB"))


def gray(rgb) -> np.ndarray:
    return rgb.astype(float) @ [0.299, 0.587, 0.114]


def claw_tip(rgb, background, near=None):
    """Pixel of the claw tip: the lowest rows of the black blob that isn't in the background (the
    one nearest `near` if given). None if no such blob."""
    g, bg = gray(rgb), gray(background)
    mask = ndimage.binary_opening((g < DARK) & (bg - g > DARK_DIFF), iterations=1)
    labels, n = ndimage.label(mask)
    if n == 0:
        return None
    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    candidates = [i + 1 for i in range(n) if sizes[i] >= 40]
    if not candidates:
        return None
    if near is not None:
        coms = ndimage.center_of_mass(mask, labels, candidates)
        best = min(zip(candidates, coms), key=lambda c: math.dist((c[1][1], c[1][0]), near))[0]
    else:
        best = max(candidates, key=lambda i: sizes[i - 1])
    ys, xs = np.nonzero(labels == best)
    bottom = ys >= ys.max() - 3
    return float(xs[bottom].mean()), float(ys[bottom].mean())


def _dark_blobs(a, b) -> list:
    """Blobs black in gray image `a` and much brighter in `b`, not touching the image border:
    [(size, (u, v) of the blob's lowest rows)], largest first."""
    mask = ndimage.binary_opening((a < DARK) & (b - a > DARK_DIFF), iterations=1)
    labels, n = ndimage.label(mask)
    h, w = mask.shape
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        if len(xs) < 30 or xs.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1:
            continue  # cut off by the frame edge: the tip may be outside the image
        bottom = ys >= ys.max() - 3
        out.append((len(xs), (float(xs[bottom].mean()), float(ys[bottom].mean()))))
    return sorted(out, reverse=True)


def pair_tips(high_rgb, low_rgb):
    """Claw tips in the two shots over the same grid point (high stop, low stop). Between the shots
    only the gripper moved, so the claws are the black pixels present in one and not the other;
    laptops, the arm base and anything else static cancel out. The low tip is the largest such
    blob; the high tip is the blob straight above it (the wrist-cam cable also moves, off to the
    side). None if either is missing or cut off by the frame edge."""
    gh, gl = gray(high_rgb), gray(low_rgb)
    lows = _dark_blobs(gl, gh)
    if not lows:
        return None
    lo = lows[0][1]
    above = [t for _, t in _dark_blobs(gh, gl) if 8 <= lo[1] - t[1] and abs(lo[0] - t[0]) <= (lo[1] - t[1]) / 2]
    if not above:
        return None
    hi = min(above, key=lambda t: abs(lo[0] - t[0]))
    return hi, lo


def arm_mask(shape, model: Model, tcp, tcp_to_tip: float) -> np.ndarray:
    """Pixels covered by the gripper: a band along its axis from the fingertips 350 mm back."""
    o = np.array([tcp.o_x, tcp.o_y, tcp.o_z])
    tip = np.array([tcp.x, tcp.y, tcp.z]) + o * tcp_to_tip
    pts = [model.to_image(*(tip - o * d)) for d in (0, 100, 200, 350)]
    img = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(img).line(pts, fill=255, width=2 * ARM_MASK_PX, joint="curve")
    for u, v in pts[:1]:
        ImageDraw.Draw(img).ellipse((u - ARM_MASK_PX, v - ARM_MASK_PX, u + ARM_MASK_PX, v + ARM_MASK_PX), fill=255)
    return np.asarray(img) > 0


def detect_items(rgb, model: Model, region_mask, exclude=None) -> list:
    """Items on the table: [(x, y, pixels, (u, v))], world xy at the table height."""
    f = rgb.astype(float)
    background = ndimage.gaussian_filter(f, sigma=(15, 15, 0))
    mask = (np.abs(f - background).sum(axis=-1) > ITEM_DIFF) & region_mask
    if exclude is not None:
        mask &= ~exclude
    mask = ndimage.binary_opening(mask, iterations=1)
    labels, n = ndimage.label(mask)
    g = gray(rgb)
    h, w = mask.shape
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        if not ITEM_PIXELS[0] <= len(xs) <= ITEM_PIXELS[1]:
            continue
        if xs.min() == 0 or ys.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1:
            continue  # touches the border: a hand or an arm, not a part
        if g[ys, xs].mean() < ITEM_MIN_GRAY:
            continue
        u, v = float(xs.mean()), float(ys.max())  # the bottom of the blob is where it meets the table
        x, y = model.to_world(u, v, model.table_z + ITEM_Z_ABOVE_TABLE)
        out.append((x, y, len(xs), (u, v)))
    return out


def polygon_mask(shape, poly) -> np.ndarray:
    img = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(img).polygon(poly, fill=255)
    return np.asarray(img) > 0


# ---------------------------------------------------------------- the feedback loop

class ItemMoved(Exception):
    pass


class Watcher:
    """Background task: overview frames -> items -> Tracker, plus the claw tip. Read-only."""

    def __init__(self, machine, model: Model, region: dict, tcp_to_tip: float):
        self.machine, self.model, self.tcp_to_tip = machine, model, tcp_to_tip
        self.region = region
        self.background = None  # the calibration median: the scene without the claws
        bg_path = os.path.join(HERE, "config", "overview_background.png")
        if os.path.exists(bg_path):
            self.background = np.asarray(Image.open(bg_path).convert("RGB"))
        self.tracker = None
        self.frames = 0
        self.last = None  # (t, rgb, tcp, dets, tip)
        self._task = None

    async def start(self, x, y):
        self.tracker = Tracker(x, y, time.monotonic())
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def look(self):
        """One frame: (t, rgb, tcp, items, claw tip pixel)."""
        rgb, tcp = await asyncio.gather(grab(self.machine), tcp_pose(self.machine))
        t = time.monotonic()
        region = polygon_mask(rgb.shape, self.model.region_polygon(self.region))
        arm = arm_mask(rgb.shape, self.model, tcp, self.tcp_to_tip)
        dets = detect_items(rgb, self.model, region, exclude=arm)
        tip = None
        if self.background is not None:
            o = np.array([tcp.o_x, tcp.o_y, tcp.o_z])
            expected = self.model.to_image(*(np.array([tcp.x, tcp.y, tcp.z]) + o * self.tcp_to_tip))
            tip = claw_tip(rgb, self.background, near=expected)
        return t, rgb, tcp, dets, tip

    async def _run(self):
        while True:
            try:
                self.last = await self.look()
                self.tracker.update(self.last[3], self.last[0])
                self.frames += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:  # a dropped frame must not kill the loop
                print(f"  overview: {type(e).__name__}: {e}")
                await asyncio.sleep(0.1)

    def position(self) -> tuple:
        return self.tracker.x, self.tracker.y

    async def wait_still(self, still_s=0.3, timeout_s=10.0) -> tuple:
        """Item xy once it has been still for still_s. Raises TimeoutError (still moving) or ItemMoved (lost)."""
        t_end = time.monotonic() + timeout_s
        while time.monotonic() < t_end:
            now = time.monotonic()
            if self.tracker.lost(now):
                raise ItemMoved("overview lost the item")
            if self.tracker.still_for(now) >= still_s:
                return self.position()
            await asyncio.sleep(0.03)
        raise TimeoutError(f"item still moving after {timeout_s:.0f} s (speed {self.tracker.speed():.0f} mm/s)")

    def moved_from(self, xy, tol_mm) -> bool:
        """Seen (in the last 0.3 s) more than tol_mm from xy. Not seen = not moved: near the table the
        claws hide the item."""
        now = time.monotonic()
        return now - self.tracker.last_seen < 0.3 and math.dist(self.position(), xy) > tol_mm

    def save(self, path, note=""):
        if self.last is None:
            return None
        _, rgb, tcp, dets, tip = self.last
        img = Image.fromarray(rgb)
        d = ImageDraw.Draw(img)
        d.polygon(self.model.region_polygon(self.region), outline="cyan")
        for x, y, _, (u, v) in dets:
            d.ellipse((u - 6, v - 6, u + 6, v + 6), outline="yellow", width=2)
        if self.tracker:
            u, v = self.model.to_image(*self.position(), self.model.table_z + ITEM_Z_ABOVE_TABLE)
            d.ellipse((u - 9, v - 9, u + 9, v + 9), outline="lime", width=3)
        if tip:
            d.line((tip[0] - 10, tip[1], tip[0] + 10, tip[1]), fill="red", width=2)
            d.line((tip[0], tip[1] - 10, tip[0], tip[1] + 10), fill="red", width=2)
        d.text((5, 5), note, fill="red")
        img.save(path)
        return path


async def align(watcher: Watcher, mover: Mover, item_xy, tol_mm=2.0, tries=3) -> dict:
    """Servo at hover: move the arm by (item - seen claw tip) until they line up in xy. Both come from
    the same image, so calibration error largely cancels. Returns the last error."""
    err = None
    for i in range(tries):
        t, rgb, tcp, dets, tip = await watcher.look()
        watcher.last = (t, rgb, tcp, dets, tip)
        if tip is None:
            raise RuntimeError("claw tip not found in the overview image")
        tip_z = tcp.z - watcher.tcp_to_tip
        tx, ty = watcher.model.to_world(*tip, tip_z)
        ix, iy = item_xy
        err = {"dx": round(ix - tx, 1), "dy": round(iy - ty, 1), "tip_xy": (round(tx, 1), round(ty, 1)),
               "tcp_xy": (round(tcp.x, 1), round(tcp.y, 1)), "tries": i + 1}
        print(f"  align {i + 1}: claw tip seen at ({tx:.0f}, {ty:.0f}), TCP at ({tcp.x:.0f}, {tcp.y:.0f}), "
              f"item at ({ix:.0f}, {iy:.0f}) -> correction ({err['dx']:+.1f}, {err['dy']:+.1f}) mm")
        if math.hypot(err["dx"], err["dy"]) < tol_mm or not mover.live:
            break
        await mover.straight(tcp.x + err["dx"], tcp.y + err["dy"], tcp.z, f"align {i + 1}")
    return err


async def guarded(watcher: Watcher, mover: Mover, move, item_xy, tol_mm=8.0):
    """Run `move` (a coroutine); stop the arm if the overview sees the item more than tol_mm away."""
    task = asyncio.create_task(move)
    while not task.done():
        if watcher.moved_from(item_xy, tol_mm):
            await mover.arm.stop()
            task.cancel()
            x, y = watcher.position()
            raise ItemMoved(f"item moved to ({x:.0f}, {y:.0f}) during the move; arm stopped")
        await asyncio.sleep(0.03)
    await task


# ---------------------------------------------------------------- calibration

async def calibrate(machine, args):
    with open(POSES_PATH) as f:
        poses = json.load(f)
    cfg = poses["overview"]
    g = poses["grasp"]
    out = os.path.join(LOG_DIR, f"overview-calib-{time.strftime('%H%M%S')}")
    os.makedirs(out, exist_ok=True)
    mover = Mover(machine, args.live, args.step, table_z=0.0)
    cam = Camera.from_robot(machine, "cam")

    await mover.joints(poses["scan_joints_deg"], "go to scan pose")
    s = await scan(machine, cam, poses["pick_region"])
    mover.ws = world_state(s.table_z)
    theta = await gripper_theta(machine)
    z0, z1 = (s.table_z + h for h in cfg["cal_tip_heights_mm"])
    hover = s.table_z + g["tcp_to_tip_mm"] + 150
    print(f"table z {s.table_z:.1f}; tip planes z0={z0:.1f} z1={z1:.1f}; frames -> {out}")

    shots = []  # (x, y, z, rgb)
    for x in cfg["cal_grid_x"]:
        for y in cfg["cal_grid_y"]:
            try:
                await mover.to(x, y, hover, theta, f"over ({x}, {y})")
                for z in (z1, z0):
                    await mover.straight(x, y, z + g["tcp_to_tip_mm"], f"tips at z {z:.0f}")
                    if args.live:
                        await asyncio.sleep(0.3)  # let it settle
                        shots.append((x, y, z, await grab(machine)))
                await mover.straight(x, y, hover, "up")
            except Exception as e:
                print(f"  ({x}, {y}) skipped: {type(e).__name__}: {e}")
    await mover.joints(poses["scan_joints_deg"], "return to scan pose")
    if not args.live:
        return

    for x, y, z, rgb in shots:  # raw frames, so `refit` can redo the analysis offline
        Image.fromarray(rgb).save(os.path.join(out, f"raw-x{x}-y{y}-z{z - s.table_z:.0f}.png"))
    base = {"table_z": s.table_z, "z0": z0, "z1": z1, "tcp_to_tip_mm": g["tcp_to_tip_mm"]}
    with open(os.path.join(out, "base.json"), "w") as f:
        json.dump(base, f)
    analyse(out, base, shots)


def analyse(out: str, base: dict, shots: list):
    """Claw tips from each high/low pair -> robust fit -> config/overview_calib.json if good enough."""
    z0, z1 = base["z0"], base["z1"]
    by_xy = {}
    for x, y, z, rgb in shots:
        by_xy.setdefault((x, y), {})["low" if abs(z - z0) < abs(z - z1) else "high"] = rgb
    pts, uv0, uv1 = [], [], []
    for (x, y), pair in sorted(by_xy.items()):
        tips = pair_tips(pair["high"], pair["low"]) if len(pair) == 2 else None
        if tips is None:
            print(f"  ({x}, {y}): claws not found in both shots (out of view or blocked)")
            continue
        hi, lo = tips
        print(f"  ({x}, {y}): tip high ({hi[0]:.0f}, {hi[1]:.0f}), low ({lo[0]:.0f}, {lo[1]:.0f})")
        for name, rgb, tip in (("high", pair["high"], hi), ("low", pair["low"], lo)):
            img = Image.fromarray(rgb)
            ImageDraw.Draw(img).ellipse((tip[0] - 8, tip[1] - 8, tip[0] + 8, tip[1] + 8), outline="red", width=3)
            img.save(os.path.join(out, f"tip-x{x}-y{y}-{name}.jpg"))
        pts.append((x, y))
        uv0.append(lo)
        uv1.append(hi)
    if len(pts) < 6:
        raise SystemExit(f"claw tips found at only {len(pts)} grid points; need 6. See {out}")
    calib, errs = fit_calib(pts, uv0, uv1, base)
    for p, e in errs.items():
        print(f"  leave-one-out error at {p}: {e:.1f} mm")
    dropped = [p for p in pts if list(p) not in [list(q) for q in calib["world_xy"]]]
    print(f"  kept {len(calib['world_xy'])} points, dropped {dropped or 'none'}; worst {calib['loo_err_mm_max']} mm")
    if calib["loo_err_mm_max"] > MAX_CALIB_ERR_MM:
        raise SystemExit(f"not saved: worst leave-one-out error {calib['loo_err_mm_max']} mm > {MAX_CALIB_ERR_MM}")
    calib["made"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(CALIB_PATH, "w") as f:
        json.dump(calib, f, indent=1)
    print(f"saved {CALIB_PATH}")


def refit(folder: str):
    """Redo the analysis on a calibration folder's raw frames (no robot needed)."""
    import glob
    import re
    with open(os.path.join(folder, "base.json")) as f:
        base = json.load(f)
    shots = []
    for path in glob.glob(os.path.join(folder, "raw-*.png")):
        x, y, h = (int(v) for v in re.match(r"raw-x(-?\d+)-y(-?\d+)-z(-?\d+)", os.path.basename(path)).groups())
        shots.append((x, y, base["table_z"] + h, np.asarray(Image.open(path).convert("RGB"))))
    analyse(folder, base, shots)


# ---------------------------------------------------------------- watch (read-only)

async def watch(machine, args):
    with open(POSES_PATH) as f:
        poses = json.load(f)
    model = load_model()
    w = Watcher(machine, model, poses["pick_region"], poses["grasp"]["tcp_to_tip_mm"])
    out = os.path.join(LOG_DIR, f"overview-watch-{time.strftime('%H%M%S')}")
    os.makedirs(out, exist_ok=True)
    for i in range(args.frames):
        t0 = time.perf_counter()
        w.last = await w.look()
        ms = (time.perf_counter() - t0) * 1000
        _, _, tcp, dets, tip = w.last
        items = ", ".join(f"({x:.0f}, {y:.0f}) {p}px" for x, y, p, _ in dets) or "none"
        tip_s = "" if tip is None else (f"  claw tip px ({tip[0]:.0f}, {tip[1]:.0f}), seen height "
                                        f"{model.height_of(*tip, tcp.x, tcp.y) - model.table_z:.0f} mm above table")
        print(f"{ms:5.0f} ms  items: {items}{tip_s}")
        w.save(os.path.join(out, f"{i:03d}.jpg"), f"{len(dets)} items")
    print("frames:", out)


# ---------------------------------------------------------------- selftest (offline)

def selftest():
    # a pinhole camera behind and above the work area, looking at it at a low angle
    f, cx, cy = 600, 320, 240
    cam_pos = np.array([-400.0, 50.0, 450.0])
    fwd = np.array([500.0, 0.0, -0.0]) - cam_pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)

    def project(p):
        d = np.asarray(p, float) - cam_pos
        return cx + f * d @ right / (d @ fwd), cy + f * d @ down / (d @ fwd)

    xs, ys, z0, z1 = (250, 400, 550), (-200, 0, 200), 15.0, 75.0
    pts = [(x, y) for x in xs for y in ys]
    model = Model({"table_z": 0.0, "z0": z0, "z1": z1, "world_xy": pts,
                   "uv0": [project((x, y, z0)) for x, y in pts], "uv1": [project((x, y, z1)) for x, y in pts]})
    rng = np.random.default_rng(0)
    worst_px = worst_mm = worst_z = 0.0
    for _ in range(200):
        p = (rng.uniform(250, 550), rng.uniform(-200, 200), rng.uniform(0, 100))
        u, v = model.to_image(*p)
        worst_px = max(worst_px, math.dist((u, v), project(p)))
        worst_mm = max(worst_mm, math.dist(model.to_world(*project(p), p[2]), p[:2]))
        worst_z = max(worst_z, abs(model.height_of(*project(p), p[0], p[1]) - p[2]))
    print(f"camera model: worst {worst_px:.2f} px, {worst_mm:.2f} mm back to world, {worst_z:.2f} mm in height")
    assert worst_mm < 3 and worst_z < 3

    # tracker: still, then pushed at 100 mm/s for 1 s, then still again; frames at 20 Hz
    tr = Tracker(400, 0, 0.0)
    for k in range(1, 81):
        t = k * 0.05
        x = 400 + 100 * min(max(t - 1.0, 0), 1.0)
        tr.update([(x + rng.normal(0, 1), rng.normal(0, 1)), (300, 150)], t)
        if k == 20:
            assert tr.still_for(t) > 0.9, tr.still_for(t)
        if k == 30:
            assert tr.still_for(t) < 0.2 and 60 < tr.speed() < 160, (tr.still_for(t), tr.speed())
    assert abs(tr.x - 500) < 4 and tr.still_for(80 * 0.05) > 1.5, (tr.x, tr.still_for(4.0))
    assert not tr.update([(700, 300)], 4.05), "a far blob must not be taken for the item"
    print(f"tracker: follows a push to x={tr.x:.1f} (true 500), ignores the distractor and far blobs")
    print("selftest ok")


async def amain(args):
    from station import connect
    async with await connect() as machine:
        await (calibrate if args.cmd == "calibrate" else watch)(machine, args)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["calibrate", "watch", "selftest", "refit"])
    p.add_argument("folder", nargs="?", help="refit: a logs/overview-calib-* folder")
    p.add_argument("--live", action="store_true", help="calibrate: move the arm (default: dry run)")
    p.add_argument("--step", action="store_true", help="calibrate: wait for Enter before each motion")
    p.add_argument("--frames", type=int, default=20, help="watch: how many frames")
    a = p.parse_args()
    if a.cmd == "selftest":
        selftest()
        sys.exit(0)
    if a.cmd == "refit":
        refit(a.folder)
        sys.exit(0)
    asyncio.run(amain(a))
