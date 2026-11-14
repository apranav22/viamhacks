"""LIVE: wrist depth survey of the bins from high above; fits the bin box (world mm). Moves the arm (high legs only)."""
import asyncio, io, json, sys, time
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, ".")
from station import connect
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.proto.component.arm import JointPositions
from pipeline import cam_to_world
from vh.kinematics import ik, body_points, check_path, load_obstacles
import subprocess
WATCH_J = [57.13, 6.59, -40.35, 0.0, -46.93, 57.13]
OUT = Path("runs") / ("bins_" + time.strftime("%Y%m%d_%H%M%S")); OUT.mkdir(parents=True)
OBS = [o for o in load_obstacles() if o[0] != "cardboard-box"]          # the box is what we are measuring

def low(a, b):
    return min(min(p[2] - r for p, r in body_points(list(np.array(a) + (np.array(b) - np.array(a)) * i / 40), False)) for i in range(41))

async def main():
    m = await connect()
    arm, cam = Arm.from_robot(m, "arm"), Camera.from_robot(m, "cam")
    q0 = [float(v) for v in (await arm.get_joint_positions()).values]
    assert max(abs(a - b) for a, b in zip(q0, WATCH_J)) < 1, f"not at watch: {q0}"
    target = ik(np.array([380.0, -120.0, 480.0]), seed=WATCH_J)[0]
    ok, cl, where = check_path(q0, target, OBS, holding=False, margin=10)
    lo = low(q0, target)
    print("survey pose", target, "path", ok, cl, "lowest body z", round(lo))
    assert ok and lo > 250, "survey leg not clearly above the bins"
    subprocess.Popen(["afplay", "/System/Library/Sounds/Sosumi.aiff"]); subprocess.run(["say", "arm moving"])
    await arm.move_to_joint_positions(JointPositions(values=target))
    await asyncio.sleep(1.0)
    pts_all = []
    for k in range(3):
        imgs, _ = await cam.get_images()
        color = next(i for i in imgs if i.name == "color"); depth = next(i for i in imgs if i.name == "depth")
        D = np.asarray(depth.bytes_to_depth_array(), float)
        kk = (await cam.get_properties()).intrinsic_parameters
        rot, t = await cam_to_world(m)
        h, w = D.shape; u, v = np.meshgrid(np.arange(w), np.arange(h))
        P = np.stack([(u - kk.center_x_px) * D / kk.focal_x_px, (v - kk.center_y_px) * D / kk.focal_y_px, D], -1) @ rot.T + t
        pts_all.append(P[D > 0])
        if k == 0:
            Image.open(io.BytesIO(color.data)).save(OUT / "color.jpg"); np.save(OUT / "depth.npy", D)
    np.save(OUT / "points.npy", np.vstack(pts_all))
    subprocess.Popen(["afplay", "/System/Library/Sounds/Sosumi.aiff"]); subprocess.run(["say", "arm returning"])
    await arm.move_to_joint_positions(JointPositions(values=WATCH_J))
    print("cam at", np.round(t, 1).tolist(), "->", OUT)
    await m.close()
asyncio.run(main())
