"""Read-only look at the station: resources, poses, camera formats. Moves nothing."""

import asyncio

from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.components.gripper import Gripper
from viam.services.generic import Generic

from station import connect


async def main():
    async with await connect() as machine:
        print("Resources:")
        for r in sorted(machine.resource_names, key=lambda r: (r.subtype, r.name)):
            print(f"  {r.namespace}:{r.type}:{r.subtype:<16} {r.name}")

        arm = Arm.from_robot(machine, "arm")
        print("\narm end position:", await arm.get_end_position())
        print("arm joints:", await arm.get_joint_positions())

        gripper = Gripper.from_robot(machine, "gripper")
        try:
            print("gripper do_command {}:", await gripper.do_command({}))
        except Exception as e:
            print("gripper do_command {} error:", e)

        for name in ("cam", "overview-cam"):
            images, _ = await Camera.from_robot(machine, name).get_images()
            for img in images:
                print(f"{name}: source={img.name!r} mime={img.mime_type} bytes={len(img.data)}")

        teleop = Generic.from_robot(machine, "teleop")
        print("\nteleop status:", await teleop.do_command({"command": "status"}))


if __name__ == "__main__":
    asyncio.run(main())
