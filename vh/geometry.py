"""Camera model, frame transforms and Viam orientation-vector math.

Verified read-only on the station (2026-11-13): R = Rz(lon)·Ry(lat)·Rz(theta) reproduces the frame
system's own transforms for `gripper`, `cam` and `arm` to 1e-4. For a frame pointing straight down
(o = (0, 0, -1)) that gives:  x-axis heading = 180° - theta,  y-axis heading = 90° - theta.
"""

import asyncio
import math
from dataclasses import dataclass

import numpy as np
from viam.proto.common import Pose, PoseInFrame


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def ov_to_R(ox, oy, oz, theta_deg):
    """Viam orientation vector (degrees) -> 3x3 rotation matrix (rdk OrientationVector.ToQuat)."""
    n = math.sqrt(ox * ox + oy * oy + oz * oz)
    ox, oy, oz = ox / n, oy / n, oz / n
    lat = math.acos(max(-1.0, min(1.0, oz)))
    lon = math.atan2(oy, ox) if 1 - abs(oz) > 1e-4 else 0.0
    return _rz(lon) @ _ry(lat) @ _rz(math.radians(theta_deg))


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def theta_for_jaw_heading(jaw_heading_deg, axis="x", near_theta=0.0):
    """Theta (o = (0,0,-1)) that points the gripper's jaw axis along `jaw_heading_deg` in the world.
    A parallel jaw is symmetric under 180°, so pick the solution nearest `near_theta` (least wrist turn)."""
    base = (180.0 if axis == "x" else 90.0) - jaw_heading_deg
    candidates = [base + k * 180.0 for k in range(-3, 4)]
    best = min(candidates, key=lambda t: abs(wrap180(t - near_theta)))
    return near_theta + wrap180(best - near_theta)


def jaw_heading_for_theta(theta_deg, axis="x"):
    return wrap180((180.0 if axis == "x" else 90.0) - theta_deg)


@dataclass
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @classmethod
    async def from_camera(cls, cam):
        p = (await cam.get_properties()).intrinsic_parameters
        return cls(p.focal_x_px, p.focal_y_px, p.center_x_px, p.center_y_px, p.width_px, p.height_px)

    def rays(self, u, v):
        """Pixel(s) -> direction(s) in the camera frame with z = 1 (so depth * ray = 3D point)."""
        u, v = np.asarray(u, float), np.asarray(v, float)
        return np.stack([(u - self.cx) / self.fx, (v - self.cy) / self.fy, np.ones_like(u)], axis=-1)


@dataclass
class Transform:
    """Rigid transform frame -> world: p_world = R @ p + t."""
    R: np.ndarray
    t: np.ndarray

    def point(self, p):
        return np.asarray(p, float) @ self.R.T + self.t

    def direction(self, d):
        return np.asarray(d, float) @ self.R.T

    def ray_to_plane(self, rays_cam, z):
        """Intersect camera rays with the world plane at height z. Returns world points (N, 3)."""
        d = self.direction(rays_cam)
        s = (z - self.t[2]) / np.where(np.abs(d[..., 2]) < 1e-9, -1e-9, d[..., 2])
        return self.t + d * s[..., None]

    def heading_of(self, axis_index):
        a = self.R[:, axis_index]
        return math.degrees(math.atan2(a[1], a[0]))


async def frame_to_world(machine, frame):
    """Current transform of `frame` into the world, from 4 concurrent TransformPose calls (one RTT)."""
    def tp(x, y, z):
        return machine.transform_pose(PoseInFrame(reference_frame=frame, pose=Pose(x=x, y=y, z=z, o_z=1)), "world")
    o, px, py, pz = await asyncio.gather(tp(0, 0, 0), tp(100, 0, 0), tp(0, 100, 0), tp(0, 0, 100))
    t = np.array([o.pose.x, o.pose.y, o.pose.z])
    R = np.stack([(np.array([q.pose.x, q.pose.y, q.pose.z]) - t) / 100.0 for q in (px, py, pz)], axis=1)
    return Transform(R, t), o.pose


def down_pose(x, y, z, theta):
    """A pose pointing straight down (frame z axis = world -z)."""
    return Pose(x=float(x), y=float(y), z=float(z), o_x=0.0, o_y=0.0, o_z=-1.0, theta=float(theta))
