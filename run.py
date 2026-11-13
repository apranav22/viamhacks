"""Baseline cycle: see the item, move to it, pick it up, go home. Defect detection comes next.

    python run.py watch                    # perception only from the current pose; never moves
    python run.py pick                     # DRY RUN (default): live cameras, every move only logged
    python run.py pick --live --step       # real motion, Enter before every move (bring-up)
    python run.py pick --live --cycles 6 --release putback
    python run.py pick --fake site/img/home_color.jpg --cycles 2   # offline, no robot at all

Run `python dashboard/server.py` first (or any time) and open http://localhost:8765.

Cycle: WATCH (home view vs the empty-table reference; item present, hand gone, steady)
    -> HOVER (camera straight above the item: the first motion, latency stops here)
    -> LOOK  (color + depth close-up: center, height, yaw, shape class, grasp recipe; L1: gone -> WATCH)
    -> PICK  (open, pre-grasp, straight descent, grab, holding? L2: empty -> retry from HOVER)
    -> LIFT -> HOME -> RELEASE (hold: Enter to open | putback: put it back where it was)
One judge-log line per item in runs/<run>/judge.jsonl.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

import numpy as np

from pipeline import config as C
from pipeline import perception as P
from pipeline.geometry import down_pose, theta_for_jaw_heading
from pipeline.station import Station
from pipeline.telemetry import Telemetry


def iso(t):
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="milliseconds") if t else None


def project(T, intr, pts):
    """World points -> pixels (for overlays the dashboard draws)."""
    p = (np.atleast_2d(np.asarray(pts, float)) - T.t) @ T.R
    return [[round(float(intr.fx * x / z + intr.cx), 1), round(float(intr.fy * y / z + intr.cy), 1)] for x, y, z in p]


def depth_preview(depth, item_mask=None):
    """80x60 'height above the table' image, 1 byte per pixel (~5 KB), for the dashboard."""
    d = depth[::8, ::8]
    bg = d[(d > 0) & (True if item_mask is None else ~item_mask[::8, ::8])]
    table = float(np.median(bg)) if bg.size else float(np.median(d[d > 0]))
    h = np.clip((table - d) * 4.0, 0, 255)
    h[d == 0] = 0
    return h.astype(np.uint8).tobytes(), list(d.shape)


class Cycle:
    def __init__(self, st: Station, tel: Telemetry, args, run_dir):
        self.st, self.tel, self.args = st, tel, args
        self.ref = None
        self.judge = (run_dir / "judge.jsonl").open("a", buffering=1)

    async def capture_reference(self):
        color, _, _ = await self.st.frame()
        rgb = P.decode_color(color, P.WATCH_SCALE)
        self.ref = rgb.astype(np.float32) / 255.0
        leftovers = [b for b in P.blobs(P.segment(rgb, None, C.MASK_RECTS, P.WATCH_SCALE), P.WATCH_SCALE)
                     if not b.touches_border and b.area >= C.MIN_ITEM_PX_WATCH]
        self.tel.emit("reference", frame=color, blobs=[b.overlay() for b in leftovers])
        if leftovers:
            print(f"  note: {len(leftovers)} object(s) on the table in the reference; they'll be ignored as background")

    async def watch(self, n, seconds=None):
        """Until an item is placed. Returns (blob, rgb, color, t_appeared, t_stable)."""
        self.tel.state("WATCH", item=n)
        placement = P.Placement()
        T = await self.st.cam_transform()
        t_end = time.time() + seconds if seconds else None
        while not t_end or time.time() < t_end:
            t_rpc = time.perf_counter()
            color, _, t = await self.st.frame()
            rpc_ms = (time.perf_counter() - t_rpc) * 1000
            t0 = time.perf_counter()
            rgb = P.decode_color(color, P.WATCH_SCALE)
            res = P.watch(rgb, self.ref)
            placed = placement.update(t, res)
            proc_ms = (time.perf_counter() - t0) * 1000
            ov = res.item.overlay() if res.item else None
            if ov:
                ov["xy"] = [round(v, 1) for v in P.plane_xy(res.item, self.st.intr, T)]
            self.tel.emit("watch", frame=color, item=ov, hand=res.hand, blobs=res.n_blobs, placed=placed,
                          rpc_ms=round(rpc_ms, 1), proc_ms=round(proc_ms, 1), n=n)
            if placed:
                return res.item, rgb, color, placement.t_appeared, t
        return None

    async def look(self, n, attempt):
        """Close-up from the hover pose -> (Measurement, Grasp) or None if the item is gone (L1)."""
        self.tel.state("LOOK", item=n, attempt=attempt)
        with self.tel.span("look", item=n) as sp:
            color, raw_depth, _ = await self.st.frame(depth=True)
            T = await self.st.cam_transform(refresh=True)
            rgb = P.decode_color(color)
            depth = P.decode_depth(raw_depth) if raw_depth else None
            fg = P.segment(rgb, None, C.MASK_RECTS)
            cands = [b for b in P.blobs(fg) if not b.touches_border and b.area >= C.MIN_ITEM_PX_HOVER]
            if self.st.dry_run and self.ref is not None:   # the arm never moved: measure from the watch view
                half = P.decode_color(color, P.WATCH_SCALE)
                cands = [b for b in P.blobs(P.segment(half, self.ref, C.MASK_RECTS, P.WATCH_SCALE), P.WATCH_SCALE)
                         if not b.touches_border and b.area >= C.MIN_ITEM_PX_WATCH]
            if not cands:
                sp["result"] = "gone"
                self.tel.emit("look", frame=color, item=None, n=n)
                return None
            cx, cy = rgb.shape[1] / 2, rgb.shape[0] / 2
            blob = min(cands, key=lambda b: (b.centroid[0] - cx) ** 2 + (b.centroid[1] - cy) ** 2)
            m = P.measure(blob, depth, self.st.intr, T)
            shape = P.classify(m)
            g = P.grasp_for(m, shape)
            jaw = np.radians(g.jaw_heading)
            half = g.expected_width / 2 + 12
            ends = [[g.x - half * np.cos(jaw), g.y - half * np.sin(jaw), g.tip_z],
                    [g.x + half * np.cos(jaw), g.y + half * np.sin(jaw), g.tip_z]]
            mask = np.zeros(depth.shape, bool) if depth is not None else None
            if mask is not None:
                mask[blob.ys, blob.xs] = True
            self.tel.emit("look", frame=color, n=n, item=blob.overlay(), grasp=g.to_dict(), shape=shape,
                          shape_note=P.SHAPES[shape], m={k: round(v, 2) for k, v in m.__dict__.items()},
                          jaw_px=project(T, self.st.intr, ends), center_px=project(T, self.st.intr, [[g.x, g.y, g.tip_z]])[0])
            if depth is not None:
                prev, shp = depth_preview(depth, mask)
                self.tel.emit("depth", frame=prev, mime=f"application/x-height8;h={shp[0]};w={shp[1]}", n=n)
            sp.update(shape=shape, ok=g.ok)
            return m, g

    async def run(self, n):
        rec = {"item": n, "recoveries": 0, "events": []}
        found = await self.watch(n)
        blob, rgb, color, t_appeared, t_stable = found
        T = await self.st.cam_transform()
        x, y = P.plane_xy(blob, self.st.intr, T)
        cam_theta = self.st.cam_pose.theta
        attempt = 0
        while True:
            attempt += 1
            # HOVER: the first motion of the response
            self.tel.state("HOVER", item=n, attempt=attempt)
            hover = down_pose(x, y, C.TABLE_Z + C.CAM_HOVER_MM, cam_theta)
            with self.tel.span("hover", item=n):
                t_cmd, t_moving = await self.st.move(C.CAM, hover, "hover", watch_start=(attempt == 1))
            if attempt == 1:
                rec.update(t_appeared=t_appeared, t_stable=t_stable, t_cmd=t_cmd, t_moving=t_moving)
                self.tel.emit("latency", n=n, t_appeared=t_appeared, t_stable=t_stable, t_cmd=t_cmd, t_moving=t_moving,
                              ms_to_stable=round((t_stable - t_appeared) * 1000), ms_to_cmd=round((t_cmd - t_appeared) * 1000),
                              ms_to_motion=round((t_moving - t_appeared) * 1000))
            looked = await self.look(n, attempt)
            if looked is None:                                  # L1: item gone or moved out of view
                rec["recoveries"] += 1
                rec["events"].append("L1: not under the camera at the hover look")
                self.tel.emit("recovery", level="L1", n=n, what="item not at the hover look; back to WATCH")
                await self.st.home()
                found = await self.watch(n)
                blob, rgb, color, _, _ = found
                x, y = P.plane_xy(blob, self.st.intr, await self.st.cam_transform())
                continue
            m, g = looked
            rec.update(shape=g.shape, grasp=g.to_dict())
            if not g.ok:
                rec["result"] = f"not graspable: {g.reason}"
                await self.st.home()
                break
            if abs(m.x - x) + abs(m.y - y) > 3:                 # L1: refine (or follow a moved item)
                x, y = m.x, m.y
            # PICK
            self.tel.state("PICK", item=n, attempt=attempt)
            _, gpose = await self.st.gripper_pose()
            theta = theta_for_jaw_heading(g.jaw_heading, C.JAW_AXIS, near_theta=gpose.theta)
            gz = g.tip_z + C.TCP_TIP_OFFSET_MM
            with self.tel.span("pick", item=n, shape=g.shape):
                await self.st.open()
                await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz + C.PREGRASP_MM, theta), "pre-grasp")
                await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz, theta), "descend", linear=True, obstacles=False)
                grabbed = await self.st.grab()
                pos, holding = (g.expected_width * 10, True) if self.st.dry_run else await self.st.gripper_state()
            self.tel.state("LIFT", item=n)
            await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz + C.LIFT_MM, theta), "lift", linear=True, obstacles=False)
            got = holding or (pos is not None and pos > C.GRIP_EMPTY_POS)
            self.tel.emit("grasp_result", n=n, grabbed=grabbed, pos=pos, holding=holding, ok=got,
                          expected_pos=round(g.expected_width * 10))
            if got:
                break
            rec["recoveries"] += 1                              # L2: empty grab -> look again and retry
            rec["events"].append(f"L2: empty grab (pos {pos})")
            self.tel.emit("recovery", level="L2", n=n, what=f"empty grab (jaw pos {pos}); retry from hover")
            await self.st.open()
            if attempt > C.GRASP_RETRIES:
                rec["result"] = "gave up after retries"
                break
        if "result" not in rec:
            self.tel.state("HOME", item=n)
            with self.tel.span("home", item=n):
                await self.st.home()
            still = True if self.st.dry_run else (await self.st.gripper_state())[1]
            rec["result"] = "picked" if still else "lost after lift"
            self.tel.state("RELEASE", item=n)
            await self.release(g, theta, gz)
        rec.update(decision="pending", confidence=None, timestamp=iso(rec.get("t_cmd") or time.time()))
        line = {"item": n, "decision": rec["decision"], "confidence": rec["confidence"], "timestamp": rec["timestamp"],
                "t_appeared": iso(rec.get("t_appeared")), "t_first_motion": iso(rec.get("t_moving")),
                "latency_ms": round((rec["t_moving"] - rec["t_appeared"]) * 1000) if rec.get("t_moving") else None,
                "shape": rec.get("shape"), "result": rec["result"], "recoveries": rec["recoveries"],
                "events": rec["events"], "dry_run": self.st.dry_run}
        self.judge.write(json.dumps(line) + "\n")
        self.tel.emit("cycle", **line)
        self.tel.report()
        return line

    async def release(self, g, theta, gz):
        mode = self.args.release
        if mode == "putback":
            await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz + C.PREGRASP_MM, theta), "putback above")
            await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz + 3, theta), "putback down", linear=True, obstacles=False)
            await self.st.open()
            await self.st.move(C.GRIPPER, down_pose(g.x, g.y, gz + C.LIFT_MM, theta), "putback up", linear=True, obstacles=False)
            await self.st.home()
        else:
            if sys.stdin.isatty() and not self.st.dry_run:
                await asyncio.to_thread(input, "  holding the item at home. Hand under it, then Enter to open ")
            await self.st.open()


async def main(args):
    run_id = time.strftime("%Y%m%d_%H%M%S") + ("_dry" if not args.live else "_live")
    run_dir = C.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    tel = Telemetry(C.TELEMETRY_HOST, C.TELEMETRY_PORT, enabled=C.TELEMETRY and not args.no_telemetry, run_id=run_id)
    if args.fake:
        from pipeline.fake import FakeStation
        if args.live:
            raise SystemExit("--fake can't move anything; drop --live")
        st = FakeStation(tel, args.fake)
    else:
        st = Station(tel, dry_run=not args.live, step=args.step)
    await st.connect()
    tel.emit("run", cmd=args.cmd, live=args.live, step=args.step, release=args.release,
             config={k: v for k, v in vars(C).items() if k.isupper() and not k.endswith("FILE")})
    print(f"run {run_id}: {'LIVE MOTION' if args.live else 'dry run (nothing moves)'}; logs in {run_dir}")
    cyc = Cycle(st, tel, args, run_dir)
    try:
        if args.live:
            if await st.teleop_running():
                raise SystemExit("teleop is running: stop it first (one driver at a time)")
            if not await st.at_home():
                print("arm is not at the watch (home) pose")
                await st._confirm("go home first")
                await st.home()
        elif not await st.at_home():
            print("note: the arm isn't at home, so the watch geometry is whatever the camera sees now")
        if args.cmd == "watch":
            await cyc.capture_reference()
            print(f"watching for {args.seconds:.0f} s (place / move an item); nothing moves")
            while True:
                found = await cyc.watch(0, seconds=args.seconds)
                if not found:
                    break
                blob, _, _, t_app, t_st = found
                x, y = P.plane_xy(blob, st.intr, await st.cam_transform())
                print(f"  placed: world ({x:.0f}, {y:.0f}) mm, {blob.area} px, {1000 * (t_st - t_app):.0f} ms after it appeared")
                tel.emit("placed", x=round(x, 1), y=round(y, 1))
                await asyncio.sleep(1.0)
        else:
            await cyc.capture_reference()
            for n in range(1, args.cycles + 1):
                print(f"item {n}: waiting for an item to be placed ...")
                line = await cyc.run(n)
                print(f"  item {n}: {line['result']}, shape {line['shape']}, latency {line['latency_ms']} ms, "
                      f"recoveries {line['recoveries']}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("interrupted: stopping the arm")
        if args.live:
            await st.stop()
    finally:
        print("telemetry overhead:", tel.report())
        tel.state("IDLE")
        await st.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["watch", "pick"])
    ap.add_argument("--live", action="store_true", help="really move the arm (default: dry run)")
    ap.add_argument("--step", action="store_true", help="press Enter before every live move")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--release", choices=["hold", "putback"], default="hold")
    ap.add_argument("--seconds", type=float, default=30.0, help="watch: how long to run")
    ap.add_argument("--no-telemetry", action="store_true")
    ap.add_argument("--fake", metavar="IMAGE", help="offline: synthesize frames from a watch-pose image (no robot)")
    asyncio.run(main(ap.parse_args()))
