import asyncio, sys, subprocess
sys.path.insert(0, '.')
import numpy as np
from station import connect
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.proto.component.arm import JointPositions
from pipeline import cam_to_world
D = sys.argv[1]
async def main():
    m = await connect(); cam = Camera.from_robot(m, "cam")
    kk = (await cam.get_properties()).intrinsic_parameters
    rot, t = await cam_to_world(m)
    Dp = np.load(f"{D}/depth.npy"); h, w = Dp.shape
    print("depth shape", Dp.shape, "range", Dp[Dp > 0].min(), Dp.max(), flush=True)
    sx, sy = w / kk.width_px, h / kk.height_px
    u, v = np.meshgrid(np.arange(w), np.arange(h))
    P = np.stack([(u - kk.center_x_px * sx) * Dp / (kk.focal_x_px * sx), (v - kk.center_y_px * sy) * Dp / (kk.focal_y_px * sy), Dp], -1) @ rot.T + t
    np.save(f"{D}/points.npy", P[Dp > 0]); np.save(f"{D}/pix.npy", np.c_[u[Dp > 0], v[Dp > 0]])
    print("cam t", np.round(t, 1).tolist(), flush=True)
    subprocess.Popen(["afplay", "/System/Library/Sounds/Sosumi.aiff"]); subprocess.run(["say", "arm returning"])
    await Arm.from_robot(m, "arm").move_to_joint_positions(JointPositions(values=[57.13, 6.59, -40.35, 0.0, -46.93, 57.13]))
    print("at watch", flush=True); await m.close()
asyncio.run(main())
