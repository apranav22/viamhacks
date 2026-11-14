"""Save the gripper's current world position as a destination in config/poses.json.

Put the arm where the gripper should release items (over the box, the reject bin or the
hold area, e.g. by teleop), stop teleop, then run:  python -m tools.record_pose box
"""

import asyncio
import json
import sys

from viam.proto.common import Pose, PoseInFrame

from vh.config import POSES_PATH
from station import connect
from tools.identity import identity_line


async def main(name: str):
    async with await connect() as machine:
        r = await machine.transform_pose(PoseInFrame(reference_frame="gripper", pose=Pose(o_z=1)), "world")
    with open(POSES_PATH) as f:
        poses = json.load(f)
    poses["destinations"][name] = {"x": round(r.pose.x, 1), "y": round(r.pose.y, 1), "z": round(r.pose.z, 1),
                                  "_comment": f"{identity_line()} Measured world TCP with transform_pose after manual positioning."}
    with open(POSES_PATH, "w") as f:
        json.dump(poses, f, indent=2)
    print(name, poses["destinations"][name])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
