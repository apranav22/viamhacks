import asyncio

from viam.components.camera import Camera
from viam.components.arm import Arm
from viam.components.gripper import Gripper
from viam.components.switch import Switch
from viam.components.sensor import Sensor
from viam.services.generic import Generic as GenericService

from station import connect

async def main():
    async with await connect() as machine:
        print('Resources:')
        print(machine.resource_names)
        
        # overview-cam
        overview_cam: Camera = Camera.from_robot(machine, "overview-cam")
        overview_cam_return_value = await overview_cam.get_images()
        print(f"overview-cam get_images return value: {overview_cam_return_value}")

        # leader-arm
        leader_arm: Arm = Arm.from_robot(machine, "leader-arm")
        leader_arm_return_value = await leader_arm.get_end_position()
        print(f"leader-arm get_end_position return value: {leader_arm_return_value}")

        # leader-gripper
        leader_gripper: Gripper = Gripper.from_robot(machine, "leader-gripper")
        leader_gripper_return_value = await leader_gripper.is_moving()
        print(f"leader-gripper is_moving return value: {leader_gripper_return_value}")

        # home-pose
        home_pose: Switch = Switch.from_robot(machine, "home-pose")
        home_pose_return_value = await home_pose.get_position()
        print(f"home-pose get_position return value: {home_pose_return_value}")

        # capture-control
        capture_control: Sensor = Sensor.from_robot(machine, "capture-control")
        capture_control_return_value = await capture_control.get_readings()
        print(f"capture-control get_readings return value: {capture_control_return_value}")

        # leader-home
        leader_home: Switch = Switch.from_robot(machine, "leader-home")
        leader_home_return_value = await leader_home.get_position()
        print(f"leader-home get_position return value: {leader_home_return_value}")

        # arm
        arm: Arm = Arm.from_robot(machine, "arm")
        arm_return_value = await arm.get_end_position()
        print(f"arm get_end_position return value: {arm_return_value}")

        # cam
        cam: Camera = Camera.from_robot(machine, "cam")
        cam_return_value = await cam.get_images()
        print(f"cam get_images return value: {cam_return_value}")

        # gripper
        gripper: Gripper = Gripper.from_robot(machine, "gripper")
        gripper_return_value = await gripper.is_moving()
        print(f"gripper is_moving return value: {gripper_return_value}")

        # Note that the following block is commented out because it may actuate
        # or because its argument semantics are unknown. Use with caution.
        # teleop
        # teleop: GenericService = GenericService.from_robot(machine, "teleop")
        # teleop_return_value = await teleop.do_command({})
        # print(f"teleop do_command return value: {teleop_return_value}")

        # Note that the following block is commented out because it may actuate
        # or because its argument semantics are unknown. Use with caution.
        # capture-webapp
        # capture_webapp: GenericService = GenericService.from_robot(machine, "capture-webapp")
        # capture_webapp_return_value = await capture_webapp.do_command({})
        # print(f"capture-webapp do_command return value: {capture_webapp_return_value}")

if __name__ == '__main__':
    asyncio.run(main())

