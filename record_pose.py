"""Save the gripper's current world position as a destination in config/poses.json.

Put the arm where the gripper should release items (over the box, the reject bin or the
hold area, e.g. by teleop), stop teleop, then run:  python record_pose.py box
"""

import asyncio
import json
import sys

from viam.proto.common import Pose, PoseInFrame

from pipeline import POSES_PATH
from station import connect


async def main(name: str):
    async with await connect() as machine:
        r = await machine.transform_pose(PoseInFrame(reference_frame="gripper", pose=Pose(o_z=1)), "world")
    with open(POSES_PATH) as f:
        poses = json.load(f)
    poses["destinations"][name] = {"x": round(r.pose.x, 1), "y": round(r.pose.y, 1), "z": round(r.pose.z, 1)}
    with open(POSES_PATH, "w") as f:
        json.dump(poses, f, indent=2)
    print(name, poses["destinations"][name])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
