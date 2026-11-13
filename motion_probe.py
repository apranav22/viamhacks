"""Naive run of the three motion tasks to see what the motion planner can do: pick -> present -> place.
Every motion is timed and logged; a view the planner can't reach is logged and skipped.

    python motion_probe.py                      # dry run: connect, scan, print every motion; nothing moves
    python motion_probe.py --live --step        # move, waiting for Enter before every motion
    python motion_probe.py --live --step --small-moves 5   # also time 10 mm direct moves at hover
    python motion_probe.py --live --touch 400,0 --closed  # lower over a clear spot to measure tcp_to_tip_mm

1. pick:    survey -> hover above the biggest item (planner) -> re-look from hover, correct once if it
            moved -> open -> descend -> grab -> holding? -> lift to the present height
2. present: the planner reorients the gripper in place: tilts ±45 deg about x and y, spin 90 deg,
            fingertips horizontal toward +x; holding? after each
3. place:   --dest box|reject uses poses.json; default "back" puts the item down where it was picked

Results go to logs/motion-probe-<time>/, written as the run goes (survives a crash or Ctrl-C):
    steps.jsonl     one line per step: ok, ms, error, arm joints, TCP pose, gripper pos, holding, frames
    NN-<step>-<cam>.jpg   a frame from each --snap-cams camera (default the static overview-cam) after
                    every step, failed or not
"""

import argparse
import asyncio
import io
import json
import math
import os
import re
import time

from PIL import Image
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.proto.common import Pose, PoseInFrame

from overview import Watcher, align, guarded, load_model
from pipeline import (LOG_DIR, POSES_PATH, JawFrame, Mover, ctrl_c_raises, grasp_height, grasp_theta, gripper_theta,
                      halt, held, now_iso, scan, table_height, tcp_pose, world_state)
from station import connect

PRESENT_HEIGHT_MM = 250   # gripper TCP above the table while reorienting
RELOOK_MAX_SHIFT_MM = 60  # at hover, the nearest item within this distance is the same item
RELOOK_MIN_SHIFT_MM = 3   # smaller shifts aren't worth a correction
RELOOK_MIN_TURN_DEG = 5   # nor smaller jaw turns
SMALL_MOVE_MM = 10

S45 = math.sqrt(0.5)
VIEWS = [  # name, gripper pointing direction (orientation vector), extra theta (deg)
    ("tilt +x", (S45, 0, -S45), 0),
    ("tilt -x", (-S45, 0, -S45), 0),
    ("tilt +y", (0, S45, -S45), 0),
    ("tilt -y", (0, -S45, -S45), 0),
    ("spin 90", (0, 0, -1), 90),
    ("horizontal +x", (1, 0, 0), 0),
]


class Probe:
    """Times each step and, after it (ok or failed), records the arm state and camera frames."""

    def __init__(self, machine, mover: Mover, live: bool, snap_cams: list):
        self.machine, self.mover, self.live, self.snap_cams = machine, mover, live, snap_cams
        self.dir = os.path.join(LOG_DIR, f"motion-probe-{time.strftime('%H%M%S')}")
        os.makedirs(self.dir, exist_ok=True)
        self.log = open(os.path.join(self.dir, "steps.jsonl"), "a")
        self.n = 0
        self.failures = []
        self.watcher = None  # with --overview: also save its annotated frame after every step

    def note(self, **kw):
        self.log.write(json.dumps({"t": now_iso(), **kw}) + "\n")
        self.log.flush()

    async def arm_state(self) -> dict:
        async def joints():
            return [round(v, 2) for v in (await self.mover.arm.get_joint_positions()).values]

        async def tcp():
            p = await tcp_pose(self.machine)
            return {k: round(getattr(p, k), 2) for k in ("x", "y", "z", "o_x", "o_y", "o_z", "theta")}

        async def grip():
            return (await self.mover.gripper.do_command({"get": True})).get("pos")

        async def held():
            return (await self.mover.gripper.is_holding_something()).is_holding_something

        names = ("joints_deg", "tcp", "gripper_pos", "holding")
        results = await asyncio.gather(joints(), tcp(), grip(), held(), return_exceptions=True)
        return {k: (f"{type(v).__name__}: {v}" if isinstance(v, Exception) else v) for k, v in zip(names, results)}

    async def frame(self, cam_name: str, tag: str):
        images, _ = await Camera.from_robot(self.machine, cam_name).get_images()
        img = next(i for i in images if "depth" not in i.name)
        path = os.path.join(self.dir, f"{tag}-{cam_name}.jpg")
        Image.open(io.BytesIO(img.data)).convert("RGB").save(path)
        return os.path.basename(path)

    async def snapshot(self, tag: str) -> dict:
        state, *frames = await asyncio.gather(
            self.arm_state(), *(self.frame(c, tag) for c in self.snap_cams), return_exceptions=True)
        if isinstance(state, Exception):
            state = {"arm_state_error": f"{type(state).__name__}: {state}"}
        state["frames"] = [f if not isinstance(f, Exception) else f"{type(f).__name__}: {f}" for f in frames]
        return state

    async def step(self, name: str, fn, fatal=True):
        """Run one timed step; non-fatal failures are logged and the run goes on. The snapshot is
        taken after the timer stops, so it doesn't count toward the step's ms."""
        self.n += 1
        t0 = time.perf_counter()
        try:
            out, ok, err = await fn(), True, None
        except Exception as e:
            out, ok, err = None, False, f"{type(e).__name__}: {e}"
        ms = (time.perf_counter() - t0) * 1000
        print(f"  {'ok ' if ok else 'ERR'} {name:<30} {ms:7.0f} ms  {err or ''}")
        tag = f"{self.n:02d}-{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}"
        snap = await self.snapshot(tag)
        if self.watcher:
            self.watcher.save(os.path.join(self.dir, f"{tag}-tracked.jpg"), name)
            snap["tracked_xy"] = [round(v, 1) for v in self.watcher.position()]
        self.note(n=self.n, step=name, ok=ok, ms=round(ms), error=err, live=self.live, **snap)
        if not ok:
            self.failures.append((self.n, name, err, snap.get("frames")))
        if not ok and fatal:
            raise RuntimeError(f"{name} failed: {err}")
        return out


async def move_oriented(mover: Mover, x, y, z, o, theta, what):
    """motion.move the gripper to a pose with any pointing direction (Mover.to only points down)."""
    if mover._gate(f"{what} -> ({x:.0f}, {y:.0f}, {z:.0f}) o={tuple(round(c, 2) for c in o)} theta={theta:.0f}"):
        await mover.motion.move("gripper", PoseInFrame(reference_frame="world", pose=Pose(
            x=x, y=y, z=z, o_x=o[0], o_y=o[1], o_z=o[2], theta=theta)), world_state=mover.ws)


async def holding(mover: Mover):
    if not mover.live:
        return None
    status = await mover.gripper.is_holding_something()
    return status.is_holding_something


async def _flange_for(mover: Mover, machine, x, y, z) -> Pose:
    tcp = await tcp_pose(machine)
    p = await mover.arm.get_end_position()
    return Pose(x=p.x + x - tcp.x, y=p.y + y - tcp.y, z=p.z + z - tcp.z, o_x=p.o_x, o_y=p.o_y, o_z=p.o_z,
                theta=p.theta)


async def touch(mover: Mover, machine, poses: dict, x: float, y: float, closed: bool):
    """Interactive: lower the gripper over a clear spot until the fingertips just touch a sheet of
    paper on the table; tcp_to_tip_mm = TCP z - table z at that moment. closed: with the fingers shut,
    as they are around a screw (the linkage may carry the tips lower than when open)."""
    cam = Camera.from_robot(machine, "cam")
    await mover.joints(poses["scan_joints_deg"], "go to scan pose")
    s = await scan(machine, cam, poses["pick_region"])
    mover.ws = world_state(s.table_z)
    base_theta = await gripper_theta(machine)
    z = s.table_z + 150
    floor = s.table_z + 3  # measured: the tips reach ~10 mm past the TCP
    await (mover.grab() if closed else mover.open())
    await mover.to(x, y, z, base_theta, "over the touch spot")
    print(f"table z {s.table_z:.1f}. Enter = down 5 mm, a number = down that many mm (negative = up), "
          f"q = done (tips touching the paper)")
    while True:
        cmd = input(f"TCP z {z:.1f} ({z - s.table_z:.1f} above table) > ").strip()
        if cmd == "q":
            break
        try:
            dz = float(cmd) if cmd else 5.0
        except ValueError:
            continue
        if z - dz < floor:
            print(f"  refusing: TCP would go below {floor:.1f}")
            continue
        await mover.arm.move_to_position(await _flange_for(mover, machine, x, y, z - dz))
        z = (await tcp_pose(machine)).z
    print(f"\ntcp_to_tip_mm = {z - s.table_z:.1f} with the fingers {'closed' if closed else 'open'}   "
          f"(put this in config/poses.json -> grasp)")
    await mover.straight(x, y, s.table_z + 150, "up")
    await mover.joints(poses["scan_joints_deg"], "return to scan pose")


async def small_moves(probe: Probe, mover: Mover, n: int):
    """Direct arm moves (no planner, no obstacles) of SMALL_MOVE_MM back and forth in x: the
    tracking rate a chase loop could get."""
    arm: Arm = mover.arm
    for i in range(n):
        dx = SMALL_MOVE_MM if i % 2 == 0 else -SMALL_MOVE_MM

        async def go():
            p = await arm.get_end_position()
            if mover._gate(f"direct move dx={dx:+d} mm"):
                await arm.move_to_position(Pose(x=p.x + dx, y=p.y, z=p.z, o_x=p.o_x, o_y=p.o_y,
                                                o_z=p.o_z, theta=p.theta))
        await probe.step(f"small move {i + 1} ({dx:+d} mm)", go, fatal=False)


async def relook(probe: Probe, machine, cam, poses: dict, item, table_z: float, attempt: int):
    """Look again (from wherever the arm is) and return the item nearest the last estimate; its
    position and angle replace the old ones. Keeps the old item if nothing is near."""
    s2 = await probe.step(f"look ({attempt})", lambda: scan(machine, cam, poses["pick_region"]))
    near = [it for it in s2.items if math.dist((it.x, it.y), (item.x, item.y)) < RELOOK_MAX_SHIFT_MM]
    if not near:
        print("  item not seen; keeping the last estimate")
        probe.note(step="look", attempt=attempt, seen=False)
        return item
    new = min(near, key=lambda it: math.dist((it.x, it.y), (item.x, item.y)))
    shift = math.dist((new.x, new.y), (item.x, item.y))
    print(f"  look: item at ({new.x:.0f}, {new.y:.0f}), {shift:.1f} mm from the last estimate, yaw {new.yaw_deg:.0f}")
    probe.note(step="look", attempt=attempt, seen=True, shift_mm=round(shift, 1), x=new.x, y=new.y,
               yaw_deg=new.yaw_deg, top_z=new.top_z, pixels=new.pixels)
    return new


async def run(probe: Probe, mover: Mover, machine, poses: dict, args):
    g = poses["grasp"]
    cam = Camera.from_robot(machine, "cam")

    # ---- 1. pick
    await probe.step("survey pose (joints)", lambda: mover.joints(poses["scan_joints_deg"], "go to scan pose"))
    jaw = await JawFrame.measure(machine)  # at the survey pose, pointing down
    base_theta = jaw.theta0
    s = await probe.step("scan", lambda: scan(machine, cam, poses["pick_region"]))
    if not s.items:
        print(f"no item in the pick region (table_z={s.table_z:.1f}); put a part on the table")
        probe.note(step="no item", table_z=s.table_z)
        return
    item = s.items[0]
    s.table_z = table_height(s.table_z, g)
    mover.ws = world_state(s.table_z)
    theta = grasp_theta(jaw, item, g)
    grasp_z = grasp_height(item, s.table_z, g)
    above = item.top_z + g["approach_height_mm"]
    print(f"item at ({item.x:.0f}, {item.y:.0f}), top {item.top_z - s.table_z:.0f} mm above table "
          f"z={s.table_z:.1f}, yaw {item.yaw_deg:.0f} deg, {len(s.items)} in view")
    print(f"  jaws: close along {item.yaw_deg + g['jaw_offset_deg']:.0f} deg -> gripper theta {theta:.0f} "
          f"(survey theta {base_theta:.0f}, use_yaw={g['use_yaw']})")
    probe.note(step="item", x=item.x, y=item.y, top_z=item.top_z, table_z=s.table_z, yaw_deg=item.yaw_deg,
               pixels=item.pixels, in_view=len(s.items), base_theta=base_theta, theta=theta)

    await probe.step("hover (planner)", lambda: mover.to(item.x, item.y, above, theta, "hover"))
    if args.small_moves:
        await small_moves(probe, mover, args.small_moves)
        await probe.step("back to hover (planner)", lambda: mover.to(item.x, item.y, above, theta, "hover"))

    watcher = None
    if args.overview:
        oc = poses["overview"]
        watcher = Watcher(machine, load_model(), poses["pick_region"], g["tcp_to_tip_mm"])
        await watcher.start(item.x, item.y)
        probe.watcher = watcher

    # grasp attempts: each one looks again from hover; a retry turns the jaws 90 deg from the last try
    attempts = 1 + g["retries"]
    got = None
    for attempt in range(1, attempts + 1):
        extra = 90.0 * (attempt - 1)
        if args.live:
            item = await relook(probe, machine, cam, poses, item, s.table_z, attempt)
        new_theta = grasp_theta(jaw, item, g, extra, near=theta)
        print(f"  attempt {attempt}/{attempts}: jaws close along {item.yaw_deg + g['jaw_offset_deg'] + extra:.0f} deg "
              f"(+{extra:.0f}) -> theta {new_theta:.0f}")
        theta = new_theta
        await probe.step(f"aim ({attempt}, planner)", lambda: mover.to(item.x, item.y, above, theta, "aim"))
        if watcher:
            xy = await probe.step("wait until item still (overview)",
                                  lambda: watcher.wait_still(oc["still_s"], oc["still_timeout_s"]))
            item.x, item.y = xy
            await probe.step("re-aim at hover (straight)", lambda: mover.straight(item.x, item.y, above, "re-aim"))

        await probe.step(f"open ({attempt})", mover.open)
        grasp_z = grasp_height(item, s.table_z, g)
        print(f"  grasp: tips {grasp_z - g['tcp_to_tip_mm'] - s.table_z:.1f} mm above table z {s.table_z:.1f} "
              f"-> TCP z {grasp_z:.1f} (tcp_to_tip {g['tcp_to_tip_mm']})")
        probe.note(step="grasp plan", attempt=attempt, x=item.x, y=item.y, theta=theta, tcp_z=round(grasp_z, 1),
                   tips_above_table=round(grasp_z - g["tcp_to_tip_mm"] - s.table_z, 1), table_z=s.table_z)
        descend = lambda: mover.straight(item.x, item.y, grasp_z, "descend")
        if watcher:
            await probe.step(f"descend ({attempt}, straight, guarded)", lambda: guarded(
                watcher, mover, descend(), (item.x, item.y), poses["overview"]["descent_abort_mm"]))
        else:
            await probe.step(f"descend ({attempt}, straight)", descend)
        pos = await probe.step(f"grab ({attempt})", mover.grab)
        await probe.step(f"lift ({attempt}, straight)", lambda: mover.straight(item.x, item.y, above, "lift"))
        pos_lifted = await mover.finger_pos() if args.live else None
        got = held(pos_lifted, g)
        print(f"  attempt {attempt}: fingers at {pos} after closing, {pos_lifted} after lifting -> "
              f"{'HOLDING' if got else 'missed' if got is False else 'dry run'}")
        probe.note(step="grasp result", attempt=attempt, pos_closed=pos, pos_lifted=pos_lifted, held=got,
                   extra_deg=extra)
        if got is not False:
            break
    if got is False:
        await probe.step("open (gave up)", mover.open)
        raise RuntimeError(f"no grasp after {attempts} attempts")

    present_z = s.table_z + PRESENT_HEIGHT_MM
    await probe.step("to present height (planner)",
                     lambda: mover.to(item.x, item.y, present_z, theta, "to present height"))

    # ---- 2. present
    for name, o, dtheta in VIEWS:
        await probe.step(f"view {name} (planner)", lambda o=o, dtheta=dtheta, name=name: move_oriented(
            mover, item.x, item.y, present_z, o, theta + dtheta, f"view {name}"), fatal=False)
        if args.live and held(await mover.finger_pos(), g) is False:
            print(f"  dropped during view {name}")
            probe.note(step="dropped", view=name)
            break
    await probe.step("point down again (planner)",
                     lambda: mover.to(item.x, item.y, present_z, theta, "point down"), fatal=False)

    # ---- 3. place
    dest = poses["destinations"].get(args.dest) if args.dest != "back" else None
    if args.dest != "back" and dest is None:
        print(f"  destination {args.dest!r} not recorded (python record_pose.py {args.dest}); placing back")
    if dest is None:
        dest = {"x": item.x, "y": item.y, "z": grasp_z + 5}
    approach = dest["z"] + g["approach_height_mm"]
    await probe.step("over destination (planner)",
                     lambda: mover.to(dest["x"], dest["y"], approach, base_theta, "over destination"))
    await probe.step("lower (straight)", lambda: mover.straight(dest["x"], dest["y"], dest["z"], "lower"))
    await probe.step("release", mover.open)
    await probe.step("retreat (straight)", lambda: mover.straight(dest["x"], dest["y"], approach, "retreat"))


async def main(args):
    with open(POSES_PATH) as f:
        poses = json.load(f)
    os.makedirs(LOG_DIR, exist_ok=True)

    ctrl_c_raises()
    async with await connect() as machine:
        mover = Mover(machine, args.live, args.step, table_z=0.0)
        try:
            await probe_or_touch(machine, mover, poses, args)
        except KeyboardInterrupt:
            print("\nCtrl-C: stopping")
            if args.live:
                await halt(mover)
            raise SystemExit(130)


async def probe_or_touch(machine, mover: Mover, poses: dict, args):
    if args.touch:
        if not args.live:
            raise SystemExit("--touch moves the arm; add --live")
        x, y = (float(v) for v in args.touch.split(","))
        await touch(mover, machine, poses, x, y, args.closed)
        return
    cams = [c for c in args.snap_cams.split(",") if c]
    probe = Probe(machine, mover, args.live, cams)
    print(f"motion probe {'LIVE' if args.live else 'dry run'} at {now_iso()} -> {probe.dir}")
    probe.note(step="start", live=args.live, args=vars(args), grasp=poses["grasp"], **await probe.snapshot("00-start"))
    try:
        try:
            await run(probe, mover, machine, poses, args)
        finally:
            if probe.watcher:
                await probe.watcher.stop()
    except Exception as e:
        # a failed step: log it and go home. Ctrl-C (not an Exception) skips this, so an abort
        # never starts another motion.
        probe.note(step="aborted", error=f"{type(e).__name__}: {e}")
        print(f"aborted: {e}")
    await probe.step("home (joints)", lambda: mover.joints(poses["scan_joints_deg"], "return to scan pose"),
                     fatal=False)

    print(f"\n{probe.n} steps, {len(probe.failures)} failed")
    for n, name, err, frames in probe.failures:
        print(f"  #{n} {name}: {err}\n      frames: {frames}")
    print("log:", probe.dir)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true", help="move the arm (default: dry run)")
    p.add_argument("--step", action="store_true", help="with --live, wait for Enter before each motion")
    p.add_argument("--dest", default="back", help="box | reject | back (put it down where it was picked)")
    p.add_argument("--small-moves", type=int, default=0, help="time N direct 10 mm moves at hover")
    p.add_argument("--snap-cams", default="cam,overview-cam",
                   help="comma-separated cameras to save a frame from after every step ('' = none), e.g. overview-cam,cam")
    p.add_argument("--overview", action="store_true", help="close the loop with the overview-cam: wait until "
                   "the item is still, servo the claws over it, stop the descent if it moves (run overview.py calibrate first)")
    p.add_argument("--closed", action="store_true", help="with --touch: measure with the fingers closed")
    p.add_argument("--touch", metavar="X,Y", help="with --live: lower over a clear table spot (world mm) "
                   "step by step to measure tcp_to_tip_mm")
    asyncio.run(main(p.parse_args()))
