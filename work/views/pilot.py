"""LIVE pilot, one part: watch -> top look -> oblique wrist-cam looks ±45 -> pick (sort.py unchanged) -> new webcam
views (tilt ±60 about the part axis, both ends) -> place back on the pad -> watch. Collect mode, nothing decided.
    ../sorter/.venv/bin/python work/views/pilot.py --type <part>"""
import argparse, asyncio, json, math, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "work" / "views")]
import sort as S
from vh.kinematics import flip, ik
import oblique as OB
import webcam_views as WV

def web_targets():
    up = np.array([0, 0, 1.0]); toward = -WV.C
    A = up - (up @ WV.C) * WV.C; A /= np.linalg.norm(A); n = np.cross(A, toward)
    seed = np.array(flip(WV.FRONT), float); out = []
    for tilt in (60, -60):
        ax = math.cos(math.radians(tilt)) * toward + math.sin(math.radians(tilt)) * n
        out.append((f"web_tilt{tilt:+d}", [float(v) for v in WV.solve(ax, A, seed)]))
    for s, nm in ((1, "web_end_a"), (-1, "web_end_b")):
        out.append((nm, [float(v) for v in WV.solve(-up, s * toward, seed)]))
    return out

class Pilot(S.Sorter):
    async def jmove(self, q, label, holding):
        q = [float(v) for v in q]
        if self.q is not None:      # nearest j6 turn that stays inside the controller's +-360
            q[5] = min((q[5] + 360 * k for k in range(-3, 4) if -355 <= q[5] + 360 * k <= 355), key=lambda c: abs(c - self.q[5]))
        S.sound("Sosumi")                                  # alarm before every arm move
        return await super().jmove(q, label, holding)

    async def snap_wrist(self, name):
        await asyncio.sleep(0.3)
        jpg = await self.wrist_jpeg(); jpg = await self.wrist_jpeg()
        (self.idir / f"{name}.jpg").write_bytes(jpg)
        print(f"  saved {name}", flush=True)

    async def snap_web(self, name):
        await asyncio.sleep(0.4)
        jpg = await self.web_jpeg()
        (self.idir / f"{name}.jpg").write_bytes(jpg)
        print(f"  saved {name}", flush=True)

    async def cycle(self):
        self.n += 1
        self.idir = self.dir / f"item_{self.n:03d}"; self.idir.mkdir()
        self.meta = {"item": self.n, "type": self.args.type, "mode": "pilot-coverage", "views": {}}
        self._watch_start = time.time()
        item, *_ , watch_jpg = await self.watch()
        if item is None:
            print("no part seen"); return False
        (self.idir / "watch.jpg").write_bytes(watch_jpg)
        # top look (sort.py's own), refines position + long axis
        top_q = self.look_joints(item)
        await self.jmove(top_q, "look", holding=False)
        new, tape = await self.look(item, 1, item[3] + 90)
        if new is None:
            print("part not seen from the look pose"); await self.jmove(S.WATCH_J, "return", holding=False); return False
        item = new
        x, y, yaw = item[0], item[1], item[3]
        print(f"  part at ({x:.0f}, {y:.0f}) yaw {yaw:.0f}", flush=True)
        # oblique looks
        for phi in (45, -45):
            done = False
            for d in (260, 230, 300):
                r = OB.oblique(x, y, yaw, phi, d, self.q)
                if r is None or r[0] < 10:
                    continue
                try:
                    await self.jmove(r[1], f"oblique {phi:+d}", holding=False)
                except RuntimeError as e:
                    print(f"  oblique {phi:+d} d={d} blocked: {e}"); continue
                await self.snap_wrist(f"oblique{phi:+d}_d{d}")
                self.meta["views"][f"oblique{phi:+d}"] = {"d_mm": d, "joints": self.q}
                done = True
                break
            if not done:
                print(f"  oblique {phi:+d}: no clear pose")
            await self.jmove(top_q, "back over part", holding=False)
        # grasp (sort.py pick, collect mode: one attempt)
        ok, item, _ = await self.pick(item)
        if not ok:
            print("  grasp failed"); await self.release(); await self.jmove(S.WATCH_J, "return", holding=False); return False
        await self.jmove(flip(WV.FRONT), "checkpoint", holding=True)
        await self.snap_web("web_front_old")
        for name, q in web_targets():
            try:
                await self.jmove(q, name, holding=True)
            except RuntimeError as e:
                print(f"  {name} blocked: {e}"); continue
            await self.snap_web(name)
            self.meta["views"][name] = {"joints": self.q}
        await self.jmove(flip(WV.FRONT), "checkpoint", holding=True)
        await self.place_back()
        await self.jmove(S.WATCH_J, "return", holding=False)
        (self.idir / "meta.json").write_text(json.dumps(self.meta, indent=1, default=float))
        return True

async def recover(m, args):
    """Holding a part at the checkpoint: unwind j6, place it back on the pad, return to watch."""
    from types import SimpleNamespace
    s = Pilot(m, args); s.n = 1; s.idir = s.dir; s.meta = {}
    await s.joints()
    await s.jmove(S.VIEW_J["front"], "to front view", holding=True)      # path-checked; j6 nearest valid turn
    s.pad = dict(S.ZONES["cardboard"]); s.upright = 0.0
    s.grasp_z = S.grasp_height(SimpleNamespace(top_z=S.TZ + 10), S.TZ, S.G)
    await s.place_back()
    await s.jmove(S.WATCH_J, "return", holding=False)

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--recover", action="store_true")
    p.add_argument("--type", default="unknown")
    a = p.parse_args()
    args = argparse.Namespace(mode="collect", items=1, reps=1, label="good", type=a.type, dash_host="127.0.0.1",
                              anomaly_bundle=None, anomaly_device="CPU", background="cardboard", drops=False,
                              allow_upright=False, assume_lying=True, decide="all", refs=False, watch_timeout=60)
    S.TZ, S.ZONE = S.SURFACE_Z["cardboard"], S.ZONES["cardboard"]
    S.HOVER_Z = S.TZ + 10 + S.G["approach_height_mm"]
    ik(np.array([300.0, 300.0, 200.0]))
    async with await S.connect() as m:
        await (recover(m, args) if a.recover else Pilot(m, args).run())

if __name__ == "__main__":
    asyncio.run(main())
