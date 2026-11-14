"""Measure the cardboard pad's surface height by touch: you lower the closed fingertips step by step until
they just touch the cardboard. Run it in your own terminal (needs the keyboard). E-stop attended.

    python -m tools.pad_touch                       # spots (300,340) then (230,290)
    python -m tools.pad_touch --spots 300,340       # one spot
    python -m tools.pad_touch --dry                 # pre-checks only, no motion

At each spot:  Enter = down 5 mm · a number = down that many mm (negative = up) · q = tips touching now
               s = skip this spot
Pad z = TCP z at touch - tcp_to_tip_mm (closed, 20.5 from config/poses.json).
Hard floor: the TCP never goes below table_z + tcp_to_tip_mm, i.e. closed tips never below the BARE table.
Moves: planner (table/walls/ceiling + tripod/lamp/box from config/obstacles.json) between spots at a safe height,
straight vertical moves for the descent. Ends back at the start pose with the fingers open.
"""
import argparse
import asyncio
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from viam.proto.common import Pose, PoseInFrame
from viam.services.generic import Generic

from vh.motion import Mover, ctrl_c_raises, halt, tcp_pose
from station import connect
from tools.identity import identity_line

G = json.load(open(ROOT / "config" / "poses.json"))["grasp"]
TABLE_Z, TIP = G["table_z"], G["tcp_to_tip_mm"]
FLOOR_TCP = TABLE_Z + TIP          # closed tips exactly at the bare table: never go lower
SAFE_TCP = TABLE_Z + 120           # TCP height for travel between spots (tips ~100 mm above the table)
def log(msg):
    with (ROOT / "docs/AGENT_LOG.md").open("a") as f:
        f.write(f"\n{identity_line()}\n{msg}\n")


def say(text):
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"], timeout=5)
        subprocess.run(["say", text], timeout=10)
    except Exception:
        print("(no audio)", text)


async def main(args):
    spots = [tuple(float(v) for v in s.split(",")) for s in args.spots]
    ctrl_c_raises()
    async with await connect() as m:
        mv = Mover(m, True, False, table_z=TABLE_Z)
        if (await Generic.from_robot(m, "teleop").do_command({"command": "status"})).get("running") is not False:
            raise SystemExit("teleop not confirmed off: someone else may be driving")
        j0 = list((await mv.arm.get_joint_positions()).values); await asyncio.sleep(1)
        if max(abs(a - b) for a, b in zip(j0, (await mv.arm.get_joint_positions()).values)) > 0.2:
            raise SystemExit("arm is moving: someone else is driving")
        start = await tcp_pose(m)
        if start.o_z > -0.99:
            raise SystemExit("tool not pointing down at the start; not moving")
        print(f"start TCP ({start.x:.0f}, {start.y:.0f}, {start.z:.0f}); floor TCP z {FLOOR_TCP:.1f}; spots {spots}")
        if args.dry:
            print("dry run: pre-checks passed, no motion")
            return
        if input("E-stop attended, workspace clear, nobody else driving? type yes: ").strip() != "yes":
            raise SystemExit("not confirmed; no motion")
        log(f"ARM: taken (Ali at E-stop). pad_touch.py: closed-tip touch on the cardboard at {spots}; "
            f"planner with all obstacles between spots, straight vertical descent, TCP floor {FLOOR_TCP:.1f}.")
        results, out = [], ROOT / "runs" / f"pad_touch_{time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            say("Robot arm moving. Stand clear.")
            await mv.grab()                    # tcp_to_tip_mm was measured with the fingers closed
            for x, y in spots:
                await mv.to(x, y, SAFE_TCP, start.theta, "over touch spot (planner)")
                z = (await tcp_pose(m)).z
                print(f"\n=== spot ({x:.0f}, {y:.0f}) ===  Enter=5 mm down · number=mm down (neg=up) · q=touching · s=skip")
                touched = False
                while True:
                    cmd = await asyncio.to_thread(input, f"TCP z {z:6.1f}  tips {z - TIP:6.1f}  > ")
                    cmd = cmd.strip().lower()
                    if cmd in ("q", "s"):
                        touched = cmd == "q"
                        break
                    try:
                        dz = float(cmd) if cmd else 5.0
                    except ValueError:
                        continue
                    if z - dz < FLOOR_TCP:
                        print(f"  refusing: tips would go below the bare table (TCP floor {FLOOR_TCP:.1f})")
                        continue
                    await mv.straight(x, y, z - dz, f"{'down' if dz > 0 else 'up'} {abs(dz):g} mm")
                    z = (await tcp_pose(m)).z
                if touched:
                    p = await tcp_pose(m)
                    r = {"x": round(p.x, 1), "y": round(p.y, 1), "tcp_z": round(p.z, 2), "pad_z": round(p.z - TIP, 2),
                         "above_table_mm": round(p.z - TIP - TABLE_Z, 2)}
                    results.append(r)
                    print(f"  -> pad surface z {r['pad_z']:.1f} mm ({r['above_table_mm']:.1f} above the bare table)")
                await mv.straight(x, y, SAFE_TCP, "up to travel height")
            await mv.to(start.x, start.y, start.z, start.theta, "back to start pose (planner)")
            await mv.open()
        except BaseException as e:
            await halt(mv)
            log(f"pad_touch ABORTED ({type(e).__name__}: {e}); arm/gripper stop requested. Results so far: {results}")
            raise
        finally:
            out.write_text(json.dumps({"tcp_to_tip_mm": TIP, "table_z": TABLE_Z, "results": results}, indent=1))
        log(f"ARM: released (start pose, fingers open). Pad touch results {results} -> {out.relative_to(ROOT)}.")
        if results:
            zs = [r["pad_z"] for r in results]
            print(f"\npad z: {zs}  mean {sum(zs) / len(zs):.1f}  spread {max(zs) - min(zs):.1f} mm   saved {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spots", nargs="+", default=["300,340", "230,290"])
    ap.add_argument("--dry", action="store_true")
    asyncio.run(main(ap.parse_args()))
