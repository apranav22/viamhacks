"""LIVE: empty gripper through candidate webcam presentation poses; saves webcam frames with the projected part box.
Moves the arm. Every leg path-checked (margin 0, like sort.py) and announced with a sound first."""
import asyncio, io, json, math, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, ".")
sys.path.insert(0, "work/views")
from station import connect
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.services.generic import Generic
from viam.proto.component.arm import JointPositions
from vh.kinematics import flip, check_path, frames, TCP_MM
import webcam_views as W

WATCH_J = [57.13, 6.59, -40.35, 0.0, -46.93, 57.13]
OUT = Path("runs") / ("webcam_bg_" + time.strftime("%Y%m%d_%H%M%S")); OUT.mkdir(parents=True)

def alarm(msg):
    subprocess.Popen(["afplay", "/System/Library/Sounds/Sosumi.aiff"])
    subprocess.run(["say", msg], timeout=6)

def candidates():
    up = np.array([0, 0, 1.0]); toward = -W.C
    side = np.cross(W.C, up); side /= np.linalg.norm(side)
    A = up - (up @ W.C) * W.C; A /= np.linalg.norm(A)
    n = np.cross(A, toward); seed = np.array(flip(W.FRONT), float)
    out = []
    for tilt in (0, 45, -45, 60, -60, 90, -90):
        ax = math.cos(math.radians(tilt)) * toward + math.sin(math.radians(tilt)) * n
        out.append((f"Avert_tilt{tilt:+d}", W.solve(ax, A, seed)))
    for s in (1, -1):
        out.append((f"end_tooldown_{'p' if s > 0 else 'm'}", W.solve(-up, s * toward, seed)))
    return out

async def main():
    m = await connect()
    arm, web = Arm.from_robot(m, "arm"), Camera.from_robot(m, "overview-cam")
    st = await Generic.from_robot(m, "teleop").do_command({"command": "status"})
    assert not st["running"], "teleop running"
    j1 = (await arm.get_joint_positions()).values; time.sleep(1); j2 = (await arm.get_joint_positions()).values
    assert np.abs(np.array(j1) - np.array(j2)).max() < 0.05, "someone else is moving the arm"
    q = list(j2); log = []
    plan = [("front_flip", flip(W.FRONT))] + [(k, list(v)) for k, v in candidates()]
    try:
        for name, tgt in plan:
            tgt = [float(v) for v in tgt]
            tgt[5] -= 360 * round((tgt[5] - q[5]) / 360)    # nearest j6 turn: no needless spins
            ok, cl, where = check_path(q, tgt, W.OBS, holding=False, margin=0)
            if not ok:
                print(f"SKIP {name}: path {cl} mm {where}"); log.append({"name": name, "skipped": where}); continue
            alarm("arm moving")
            await arm.move_to_joint_positions(JointPositions(values=tgt)); q = tgt
            await asyncio.sleep(0.6)
            for _ in range(2): imgs, _ = await web.get_images()
            im = Image.open(io.BytesIO(imgs[0].data)).convert("RGB")
            F = frames(tgt)[-1]; R, t = F[:3, :3], F[:3, 3]
            uv, _ = W.proj(W.part() @ R.T + t)
            d = ImageDraw.Draw(im); b = [*uv.min(0), *uv.max(0)]
            d.rectangle(b, outline=(255, 0, 0), width=3)
            im.save(OUT / f"{name}.jpg", quality=90)
            log.append({"name": name, "joints": tgt, "clearance": cl, "part_bbox_px": [round(float(v)) for v in b]})
            print(f"{name}: ok, clearance {cl} mm, part box {np.round(b).tolist()}")
    finally:
        back = [flip(W.FRONT), WATCH_J]
        for tgt in back:
            ok, cl, where = check_path(q, tgt, W.OBS, holding=False, margin=0)
            if ok:
                alarm("arm returning"); await arm.move_to_joint_positions(JointPositions(values=list(tgt))); q = list(tgt)
            else:
                print(f"RETURN leg blocked ({cl} {where}); arm left at {q}"); break
        json.dump(log, open(OUT / "poses.json", "w"), indent=1)
        print("frames ->", OUT)
        await m.close()
asyncio.run(main())
