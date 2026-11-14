"""Shared motion and grasp primitives used by the sorter and calibration tools.

Measured grasp values are supplied from config/poses.json. This module has no
executable robot loop; sort.py is the supported collection/sorting entrypoint.
"""
from __future__ import annotations

import asyncio
import math
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from viam.components.arm import Arm
from viam.components.gripper import Gripper
from viam.proto.common import GeometriesInFrame, Geometry, Pose, PoseInFrame, RectangularPrism, Vector3, WorldState
from viam.proto.component.arm import JointPositions
from viam.services.motion import Motion
from .kinematics import load_obstacles

# Legacy depth-probe upright threshold; the sorter owns its measured-view policy.
STANDING_MM = 40

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")



def box(label, cx, cy, cz, dx, dy, dz) -> Geometry:
    return Geometry(center=Pose(x=cx, y=cy, z=cz, o_z=1),
                    box=RectangularPrism(dims_mm=Vector3(x=dx, y=dy, z=dz)), label=label)



def world_state(table_z: float) -> WorldState:
    """The same workcell geometry used by joint-path checks, including fixtures."""
    return WorldState(obstacles=[GeometriesInFrame(reference_frame="world", geometries=[
        box(name, *center, *dims) for name, (center, dims) in load_obstacles(table_z=table_z)
    ])])



async def cam_to_world(machine) -> tuple:
    """Rotation and translation taking camera-frame points (mm) to world, read from the frame
    system by transforming the camera origin and its unit axes."""
    pts = []
    for v in ((0, 0, 0), (100, 0, 0), (0, 100, 0), (0, 0, 100)):
        r = await machine.transform_pose(
            PoseInFrame(reference_frame="cam", pose=Pose(x=v[0], y=v[1], z=v[2], o_z=1)), "world")
        pts.append(np.array([r.pose.x, r.pose.y, r.pose.z]))
    t = pts[0]
    rot = np.stack([(p - t) / 100 for p in pts[1:]], axis=1)
    return rot, t



class Mover:
    def __init__(self, machine, live: bool, step: bool, table_z: float):
        self.machine = machine
        self.motion = Motion.from_robot(machine, "builtin")
        self.arm = Arm.from_robot(machine, "arm")
        self.gripper = Gripper.from_robot(machine, "gripper")
        self.live, self.step = live, step
        self.ws = world_state(table_z)
        self.first_motion_at = None

    def _gate(self, what: str) -> bool:
        if not self.live:
            print(f"  [dry run] would {what}")
            return False
        if self.step:
            input(f"  Enter to {what} (Ctrl-C aborts) ")
        if self.first_motion_at is None:
            self.first_motion_at = now_iso()
        print(f"  {what}")
        return True

    async def joints(self, deg, what):
        if self._gate(what):
            await self.arm.move_to_joint_positions(JointPositions(values=deg))

    async def to(self, x, y, z, theta, what):
        if self._gate(f"{what} -> ({x:.0f}, {y:.0f}, {z:.0f}) theta={theta:.0f}"):
            await self.motion.move("gripper", PoseInFrame(
                reference_frame="world", pose=Pose(x=x, y=y, z=z, o_z=-1, theta=theta)),
                world_state=self.ws)

    async def straight(self, x, y, z, what):
        """Move the gripper TCP in a straight line to (x, y, z), keeping its orientation, by moving the
        arm directly: no planner and no obstacle check. For the last few cm near the table, where the
        planner refuses every pose because the gripper's `claws` geometry reaches 50 mm past the TCP.
        The arm base is the world frame, so a TCP translation is the same flange translation."""
        if self._gate(f"{what} (straight) -> ({x:.0f}, {y:.0f}, {z:.0f})"):
            tcp = await tcp_pose(self.machine)
            p = await self.arm.get_end_position()
            await self.arm.move_to_position(Pose(
                x=p.x + x - tcp.x, y=p.y + y - tcp.y, z=p.z + z - tcp.z,
                o_x=p.o_x, o_y=p.o_y, o_z=p.o_z, theta=p.theta))

    async def open(self):
        if self._gate("open gripper"):
            await self.gripper.open()

    async def grab(self):
        """Close and wait until the fingers stop: gripper.grab() can return while they are still
        moving, and an arm that lifts then closes on air. Returns the final finger position
        (about 0 = closed on nothing), or None in a dry run."""
        if not self._gate("close gripper"):
            return None
        start = await self.finger_pos()
        await self.gripper.grab()
        return await self.fingers_settled(start)

    async def finger_pos(self) -> float:
        return float((await self.gripper.do_command({"get": True}))["pos"])

    async def fingers_settled(self, start: float, timeout_s=3.0) -> float:
        """Finger position once they stop. Steadiness only counts after they have moved 15 from
        `start` (or 1 s has passed): right after grab() returns they may not have started yet, and
        three equal readings of still-open fingers once passed for a finished grasp."""
        t0 = time.monotonic()
        last, steady = None, 0
        while time.monotonic() - t0 < timeout_s:
            pos = await self.finger_pos()
            started = abs(pos - start) > 15 or time.monotonic() - t0 > 1.0
            steady = steady + 1 if started and last is not None and abs(pos - last) < 3 else 0
            if steady >= 3:
                return pos
            last = pos
            await asyncio.sleep(0.05)
        return last



def ctrl_c_raises():
    """Make Ctrl-C raise KeyboardInterrupt at once. asyncio.run's own handler only cancels the main
    task on the first Ctrl-C, which does nothing while the script sits in input() at a prompt."""
    signal.signal(signal.SIGINT, signal.default_int_handler)



async def halt(mover: "Mover"):
    """Best-effort stop of the arm and gripper (after Ctrl-C: the RPC that was moving the arm is
    abandoned, but the move itself keeps going on the robot)."""
    for name, part in (("arm", mover.arm), ("gripper", mover.gripper)):
        try:
            await asyncio.wait_for(part.stop(), timeout=2)
            print(f"  {name} stopped")
        except Exception as e:
            print(f"  could not stop the {name}: {type(e).__name__}: {e}  -> use the E-stop")



async def tcp_pose(machine) -> Pose:
    """The gripper TCP (arm + 150 mm) in the world frame."""
    return (await machine.transform_pose(PoseInFrame(reference_frame="gripper", pose=Pose(o_z=1)), "world")).pose



async def gripper_theta(machine) -> float:
    return (await tcp_pose(machine)).theta



def wrap90(deg: float) -> float:
    """An angle mod 180 into [-90, 90): the two fingers are symmetric, so a closing direction and
    its opposite are the same grasp."""
    return (deg + 90) % 180 - 90



@dataclass
class JawFrame:
    """How the gripper's world theta turns the direction its fingers close, read from the frame
    system with the gripper pointing down. The fingers close along the gripper's y axis: the claws
    geometry is 120 mm along y (the 85 mm opening plus two fingers), the wrist cam sees the
    fingertips side by side along gripper y, and with x the jaws clamped an 85 mm bolt end to end
    (fingers stopped at 791). At the survey pose theta 0 closes along world y, and +theta turns the
    closing direction by -theta."""
    theta0: float   # world theta now
    close0: float   # heading (deg) the fingers close along now
    s_theta: float  # +1/-1: world theta change per turn about the gripper's own z
    s_close: float  # +1/-1: closing heading change per turn about the gripper's own z

    @classmethod
    async def measure(cls, machine) -> "JawFrame":
        async def world(p):
            return (await machine.transform_pose(PoseInFrame(reference_frame="gripper", pose=p), "world")).pose

        s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
        # the gripper's y axis, before and after a 30 deg turn about its own z
        o, turned, y0, y1 = await asyncio.gather(world(Pose(o_z=1)), world(Pose(o_z=1, theta=30)),
                                                 world(Pose(y=100, o_z=1)), world(Pose(x=-100 * s, y=100 * c, o_z=1)))

        def heading(w):
            return math.degrees(math.atan2(w.y - o.y, w.x - o.x))

        return cls(o.theta, heading(y0), math.copysign(1, wrap90(turned.theta - o.theta)),
                   math.copysign(1, wrap90(heading(y1) - heading(y0))))

    def theta_for(self, close_deg: float, near: float | None = None) -> float:
        """World theta that makes the fingers close along heading close_deg. Of the two that do
        (180 apart), the one nearest `near` (the current theta), else the smallest turn from theta0."""
        theta = self.theta0 + self.s_theta * wrap90((close_deg - self.close0) * self.s_close)
        if near is not None:
            theta = min((theta - 180, theta, theta + 180), key=lambda t: abs(t - near))
        return theta



def grasp_theta(jaw: JawFrame, item, g: dict, extra_deg: float = 0, near: float | None = None) -> float:
    """Fingers across the part: closing direction = long axis + jaw_offset_deg (90) + extra_deg
    (90 on a second pass)."""
    if not g["use_yaw"]:
        return jaw.theta_for(jaw.close0 + extra_deg, near)
    return jaw.theta_for(item.yaw_deg + g["jaw_offset_deg"] + extra_deg, near)



def grasp_height(item, table_z: float, g: dict) -> float:
    """TCP height for the grasp. A lying fastener is grasped with the closed fingertips a fixed
    clearance above the table: its measured height is depth noise (the same screw read 14 and 6 mm),
    and every lying fastener is taller than the clearance. tcp_to_tip_mm is how far the CLOSED
    fingertips reach past the 150 mm gripper TCP; open, they sit ~7-10 mm higher, so the descent
    with open fingers stays clear of the table."""
    tips_z = table_z + g["min_table_clearance_mm"]
    if item.top_z - table_z > STANDING_MM:
        tips_z = (item.top_z + table_z) / 2
    return tips_z + g["tcp_to_tip_mm"]



# Upright grasp guard (policy, not measurements): keep the part's top this far under the sensor body above the tips
# on the fallback grasp, and keep at least this much of the part above the closed tips to hold it.
SENSOR_MARGIN_MM = 8.0
MIN_GRIP_MM = 10.0


def upright_tips(height_mm: float, g: dict, longest_mm: float):
    """Closed-fingertip heights above the surface for grasping an upright part: (low, high, None), or
    (None, None, why) to leave it.

    low: Pranav's halfway rule for the measured height (lower if that holds less than MIN_GRIP_MM), tried first.
    Low first is the operator's choice (Pranav, 2026-11-14: "collisions are ok. low first."): the wrist depth
    under-reads upright parts (15:48: one bolt read 20-22 mm and 80 mm and hit the gripper body on the way down), so
    for a part taller than read the low descent can run its top into the sensor body. high: the height that keeps even
    max(measured, longest_mm) SENSOR_MARGIN_MM under the sensor (g["tip_to_sensor_mm"]), for the one retry after such
    a contact; None when low is already that safe."""
    gap = g.get("tip_to_sensor_mm")
    if gap is None:
        return None, None, "tip_to_sensor_mm not measured (config/poses.json grasp): upright grasp refused"
    low = max(g["min_table_clearance_mm"], min(height_mm / 2, height_mm - MIN_GRIP_MM))
    if height_mm - low < MIN_GRIP_MM:
        return None, None, f"upright part ({height_mm:.0f} mm) too short to hold {MIN_GRIP_MM:.0f} mm of it"
    high = max(height_mm, longest_mm) - (gap - SENSOR_MARGIN_MM)
    return low, (high if high > low else None), None


def held(pos, g: dict):
    """From the finger position: True holding, False closed on nothing, None unknown (dry run)."""
    return None if pos is None else pos > g["empty_below_pos"]



def table_height(measured: float, g: dict) -> float:
    """Use the touch-measured table height; depth noise never overrides calibration."""
    return g["table_z"]
