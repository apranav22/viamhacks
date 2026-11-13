"""Thin async wrapper over the station: frames, transforms, planned moves, gripper, home.

dry_run=True (the default everywhere): cameras and state are read live, every move and gripper
command is only logged (and reported to the dashboard). Nothing moves.
"""

import asyncio
import json
import math
import time

import viam.components.arm  # noqa: F401  (register the APIs before dialing)
import viam.components.camera  # noqa: F401
import viam.components.gripper  # noqa: F401
import viam.components.switch  # noqa: F401
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.components.gripper import Gripper
from viam.components.switch import Switch
from viam.proto.common import GeometriesInFrame, Geometry, PoseInFrame, RectangularPrism, Vector3, WorldState, Pose
from viam.proto.component.arm import JointPositions
from viam.proto.service.motion import Constraints, LinearConstraint
from viam.robot.client import RobotClient
from viam.services.generic import Generic
from viam.services.motion import MotionClient

from . import config as C
from .geometry import Intrinsics, frame_to_world


class Station:
    def __init__(self, tel, dry_run=True, step=False):
        self.tel = tel
        self.dry_run = dry_run
        self.step = step
        self.m = None
        self._cam_T = None          # cached cam->world while the arm is still

    # --- lifecycle ---------------------------------------------------------------------------
    async def connect(self):
        creds = json.loads(C.API_KEY_FILE.read_text())
        t0 = time.perf_counter()
        self.m = await RobotClient.at_address(creds["address"], RobotClient.Options.with_api_key(
            api_key=creds["api_key"], api_key_id=creds["api_key_id"]))
        self.arm = Arm.from_robot(self.m, C.ARM)
        self.gripper = Gripper.from_robot(self.m, C.GRIPPER)
        self.cam = Camera.from_robot(self.m, C.CAM)
        self.motion = MotionClient.from_robot(self.m, C.MOTION)
        self.intr = await Intrinsics.from_camera(self.cam)
        cfg = await Switch.from_robot(self.m, C.HOME_SWITCH).do_command({"cfg": True})
        self.home_deg = [math.degrees(v) for v in cfg["joints"]]
        self.tel.emit("connected", ms=round((time.perf_counter() - t0) * 1000), dry_run=self.dry_run,
                      intrinsics=self.intr.__dict__, home_deg=[round(v, 1) for v in self.home_deg])
        return self

    async def close(self):
        if self.m:
            await self.m.close()

    async def teleop_running(self):
        try:
            return bool((await Generic.from_robot(self.m, "teleop").do_command({"command": "status"})).get("running"))
        except Exception:
            return False

    # --- sensing -----------------------------------------------------------------------------
    async def frame(self, depth=False):
        """(color JPEG bytes, raw depth bytes or None, capture wall time). Color-only is ~10x faster."""
        t = time.time()
        imgs, _ = await self.cam.get_images(filter_source_names=None if depth else ["color"])
        color = next((i.data for i in imgs if i.name == "color"), None) or imgs[0].data
        dep = next((i.data for i in imgs if i.name == "depth"), None) if depth else None
        return color, dep, t

    async def cam_transform(self, refresh=False):
        if refresh or self._cam_T is None:
            self._cam_T, self.cam_pose = await frame_to_world(self.m, C.CAM)
        return self._cam_T

    async def gripper_pose(self):
        T, pose = await frame_to_world(self.m, C.GRIPPER)
        return T, pose

    async def joints(self):
        return list((await self.arm.get_joint_positions()).values)

    async def at_home(self, tol=1.5):
        j = await self.joints()
        return max(abs(a - b) for a, b in zip(j, self.home_deg)) <= tol

    async def gripper_state(self):
        pos = (await self.gripper.do_command({"get": True})).get("pos")
        holding = (await self.gripper.is_holding_something()).is_holding_something
        self.tel.emit("gripper", pos=pos, holding=holding)
        return pos, holding

    # --- acting -------------------------------------------------------------------------------
    @staticmethod
    def table_world():
        # A box in front of the arm (not under its base) whose top is just below the table surface.
        top = C.TABLE_Z - C.TABLE_OBSTACLE_MARGIN
        box = Geometry(center=Pose(x=500, y=0, z=top - 100, o_z=1), label="table",
                       box=RectangularPrism(dims_mm=Vector3(x=800, y=1400, z=200)))
        return WorldState(obstacles=[GeometriesInFrame(reference_frame="world", geometries=[box])])

    async def _confirm(self, what):
        if self.step and not self.dry_run:
            await asyncio.to_thread(input, f"  next: {what}  [Enter to run, Ctrl-C to abort] ")

    async def move(self, component, pose, label, linear=False, obstacles=True, watch_start=False):
        """Planned move of `component` (e.g. 'gripper', 'cam') to a world pose.
        Returns (t_cmd, t_moving): command time and, if watch_start, when the arm actually started moving."""
        target = {k: round(getattr(pose, k), 1) for k in ("x", "y", "z", "o_x", "o_y", "o_z", "theta")}
        self.tel.emit("move", label=label, component=component, target=target, linear=linear, dry_run=self.dry_run)
        self._cam_T = None
        if self.dry_run:
            await asyncio.sleep(0.25)
            t = time.time()
            return t, t
        await self._confirm(f"{label}: {component} -> {target}")
        cons = Constraints(linear_constraint=[LinearConstraint(line_tolerance_mm=C.LINEAR_TOL_MM,
                                                               orientation_tolerance_degs=5)]) if linear else None
        t_cmd, moving = time.time(), {}
        poller = asyncio.create_task(self._first_motion(moving)) if watch_start else None
        try:
            await asyncio.wait_for(self.motion.move(component_name=component,
                                                    destination=PoseInFrame(reference_frame="world", pose=pose),
                                                    world_state=self.table_world() if obstacles else None,
                                                    constraints=cons), C.MOVE_TIMEOUT_S)
        except BaseException:
            await self.stop()
            raise
        finally:
            if poller:
                poller.cancel()
        return t_cmd, moving.get("t", t_cmd)

    async def _first_motion(self, out):
        """Timestamp of the first is_moving()==True: the honest 'arm started its response' time."""
        while True:
            if await self.arm.is_moving():
                out["t"] = time.time()
                self.tel.emit("first_motion", t_moving=out["t"])
                return
            await asyncio.sleep(0.01)

    async def home(self):
        self.tel.emit("move", label="home", component=C.ARM, joints=[round(v, 1) for v in self.home_deg],
                      dry_run=self.dry_run)
        self._cam_T = None
        if self.dry_run:
            await asyncio.sleep(0.25)
            return
        await self._confirm("home (joint move)")
        try:
            await asyncio.wait_for(self.arm.move_to_joint_positions(JointPositions(values=self.home_deg)),
                                   C.MOVE_TIMEOUT_S)
        except BaseException:
            await self.stop()
            raise

    async def open(self):
        self.tel.emit("gripper_cmd", cmd="open", dry_run=self.dry_run)
        if not self.dry_run:
            await self.gripper.open()

    async def grab(self):
        self.tel.emit("gripper_cmd", cmd="grab", dry_run=self.dry_run)
        if self.dry_run:
            return True
        return await self.gripper.grab()

    async def stop(self):
        for c in (self.arm, self.gripper):
            try:
                await c.stop()
            except Exception:
                pass
        self.tel.emit("stopped")
