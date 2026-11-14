"""Forward kinematics of the xArm 850 from the URDF the arm reports (arm.get_kinematics), plus a check of
joint-space moves against the workcell obstacles. Lets us replace planner moves with recorded joint moves and
screen their sampled paths against the box, tripod, lamp, table and walls.

The arm controller moves joint-space linearly (all joints start and stop together), so sampling the straight
line between two joint vectors gives the path the arm actually takes."""
import json
import math
from pathlib import Path

import numpy as np

from .config import GRASP, TABLE_Z

# joint origins from the URDF (xyz in m, rpy in rad); every axis is local z
URDF_JOINTS = [
    ((0, 0, 0.364), (0, 0, 0)),
    ((0, 0, 0), (1.5708, -1.5708, 0)),
    ((0.39, 0, 0), (-3.1416, 0, -1.5708)),
    ((0.15, 0.426, 0), (-1.5708, 0, 0)),
    ((0, 0, 0), (-1.5708, 0, 0)),
    ((0, -0.09, 0), (1.5708, 0, 0)),
]
TCP_MM = 150.0            # gripper frame: flange + 150 mm along the flange z
TIP_CLOSED_MM = GRASP["tcp_to_tip_mm"]


def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _T(R, t):
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = t
    return T


_STATIC = None


def frames(joints_deg):
    """World 4x4 transforms (mm) of joints 1..6 and the flange, for joint angles in degrees."""
    global _STATIC
    if _STATIC is None:
        _STATIC = [_T(_rpy(*rpy), np.array(xyz) * 1000.0) for xyz, rpy in URDF_JOINTS]
    T = np.eye(4); out = []
    for S, q in zip(_STATIC, joints_deg):
        c, s = math.cos(math.radians(q)), math.sin(math.radians(q))
        Rz = np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])
        T = T @ S @ Rz
        out.append(T)
    return out


def tcp(joints_deg):
    F = frames(joints_deg)[-1]
    return F[:3, 3] + F[:3, 2] * TCP_MM, F[:3, 2]      # TCP position, tool axis


def body_points(joints_deg, holding=True):
    """Points (mm, world) along the arm and gripper that must stay outside obstacles, with a radius each."""
    F = frames(joints_deg)
    pts = []
    # links as capsules sampled every ~40 mm: shoulder->elbow, elbow->wrist
    for a, b, r in ((F[1][:3, 3], F[2][:3, 3], 70), (F[2][:3, 3], F[3][:3, 3], 60), (F[3][:3, 3], F[5][:3, 3], 55)):
        n = max(2, int(np.linalg.norm(b - a) / 40))
        pts += [(a + (b - a) * i / n, r) for i in range(n + 1)]
    fl, z, x = F[5][:3, 3], F[5][:3, 2], F[5][:3, 0]
    for d in (0, 40, 80, 110):                    # gripper body (~90 x 120 mm), then the claws
        pts.append((fl + z * d, 55))
    y = F[5][:3, 1]
    for s in (-1, 1):                              # claws reach +-60 mm along the gripper y
        pts.append((fl + z * 135 + y * 45 * s, 20))
    tip = fl + z * (TCP_MM + TIP_CLOSED_MM)
    pts.append((tip, 12))
    if holding is True or holding == "across":     # lying part held across the jaws: ~45 mm either side, along gripper x
        for s in (-45, 45):
            pts.append((tip + x * s, 12))
    elif isinstance(holding, (int, float)) and not isinstance(holding, bool) and holding > 0:
        for d in np.arange(0, holding + 1, 12):    # upright part held in line: `holding` mm past the tips, along z
            pts.append((tip + z * d, 12))
    return pts


def load_obstacles(path=None, table_z=None):
    """Workcell boxes as (center, dims) in mm: Pranav's table/walls/ceiling + config/obstacles.json."""
    table_z = TABLE_Z if table_z is None else table_z
    boxes = [((0, 0, table_z - 105), (3000, 3000, 200)), ((740, 0, 300), (100, 3000, 1600)),
             ((0, -500, 300), (3000, 100, 1600)), ((0, 0, 1050), (3000, 3000, 100))]
    names = ["table", "wall-front", "wall-side", "ceiling"]
    p = Path(path or Path(__file__).resolve().parent.parent / "config" / "obstacles.json")
    for k, v in json.loads(p.read_text()).items():
        if not k.startswith("_"):
            boxes.append((tuple(v["center"]), tuple(v["dims"]))); names.append(k)
    return list(zip(names, boxes))


def clearance(pt, r, box):
    c, d = np.array(box[0], float), np.array(box[1], float) / 2
    q = np.abs(pt - c) - d
    outside = np.linalg.norm(np.maximum(q, 0)); inside = min(max(q.max(), -1e9), 0)
    return outside + inside - r          # < 0: the sphere touches the box


def check_path(j_from, j_to, obstacles, holding=True, steps=60, margin=10, ignore=()):
    """Sample the joint-space line; return (ok, worst clearance mm, where) over all body points and obstacles.
    ~10 ms for 60 steps."""
    a, b = np.array(j_from, float), np.array(j_to, float)
    obs = [(n, np.array(c, float), np.array(d, float) / 2) for n, (c, d) in obstacles if n not in ignore]
    worst = (1e9, None)
    for i in range(steps + 1):
        bp = body_points(a + (b - a) * i / steps, holding)
        P = np.array([p for p, _ in bp]); R = np.array([r for _, r in bp], float)
        for name, c, h in obs:
            q = np.abs(P - c) - h
            cl = np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(axis=1), 0) - R
            k = int(cl.argmin())
            if cl[k] < worst[0]:
                worst = (float(cl[k]), f"{name} at step {i}/{steps}, point {np.round(P[k]).tolist()}")
    return bool(worst[0] >= margin), round(worst[0], 1), worst[1]


def flip(j):
    """The same pose with the wrist flipped (spherical wrist: j4+180, -j5, j6+180), joints wrapped to +-180."""
    w = lambda a: (a + 180) % 360 - 180
    return [j[0], j[1], j[2], w(j[3] + 180), -j[4], w(j[5] + 180)]


JOINT_LIMITS = [(-360, 360), (-132, 132), (-242, 3.5), (-360, 360), (-124, 124), (-360, 360)]


def ik(pos, axis=(0, 0, -1), seed=None, jaw_heading_deg=None, reg=0.02):
    """Joint angles (deg) putting the TCP at `pos` (mm) with the tool pointing along `axis`, nearest `seed`.
    jaw_heading_deg: world heading of the gripper y axis (the closing direction), for pointing-down grasps."""
    from scipy.optimize import least_squares
    seed = np.array(seed if seed is not None else [0, 22.57, -50.68, 0, -74.05, 0], float)
    axis = np.array(axis, float) / np.linalg.norm(axis)

    def res(q, reg=reg):
        F = frames(q)[-1]; p = F[:3, 3] + F[:3, 2] * TCP_MM
        r = list((p - pos) / 10.0) + list((F[:3, 2] - axis) * 50)
        if jaw_heading_deg is not None:
            h = math.radians(jaw_heading_deg); y = F[:3, 1]
            r += list((np.cross(y, [math.cos(h), math.sin(h), 0]) * 50)[2:])   # y parallel to the heading (either sign)
        r += list((q - seed) * reg)
        return r
    q = least_squares(res, seed, method="lm", xtol=1e-6).x               # near the seed ...
    q = least_squares(lambda v: res(v, 0.0), q, method="lm", xtol=1e-8).x  # ... then exact
    for i, period in ((0, 360), (3, 360), (5, 180)):   # j6 by 180: the jaws close the same either way round
        q[i] -= period * round((q[i] - seed[i]) / period)
    for v, (lo, hi) in zip(q, JOINT_LIMITS):
        if not lo <= v <= hi:
            raise ValueError(f"IK solution outside joint limits: {np.round(q, 1).tolist()}")
    p, z = tcp(q)
    return [round(float(v), 2) for v in q], float(np.linalg.norm(p - pos)), float(np.degrees(np.arccos(np.clip(z @ axis, -1, 1))))


def tcp_speed_profile(j_from, j_to, n=60):
    """(d, mm_per_deg): the leading joint's travel d (deg) and, per segment of the joint-space line, how many mm the
    TCP moves per degree of the leading joint. Geometry only; multiply by the leading joint's speed for mm/s."""
    a, b = np.array(j_from, float), np.array(j_to, float)
    d = float(np.abs(b - a).max())
    if d < 1e-6:
        return 0.0, np.zeros(n - 1)
    P = np.array([tcp(a + (b - a) * s)[0] for s in np.linspace(0, 1, n)])
    return d, np.linalg.norm(np.diff(P, axis=0), axis=1) / (d / (n - 1))


def peak_tcp_speed(d, mm_per_deg, v, acc):
    """Peak TCP speed (mm/s) of a joint move whose leading joint follows a trapezoid profile (cruise v deg/s,
    acceleration acc deg/s^2; a triangle when the move is too short to reach v), as the xArm module runs joint moves."""
    if d <= 0:
        return 0.0
    n = len(mm_per_deg) + 1
    vp = min(v, math.sqrt(acc * d))
    pos = np.linspace(0, 1, n)[1:] * d
    vel = np.minimum(vp, np.sqrt(2 * acc * np.minimum(pos, d - pos + d / (n - 1))))
    return float((mm_per_deg * vel).max())


def safe_joint_speed(j_from, j_to, tcp_limit, acc, v_max=180.0, v_min=10.0):
    """Fastest leading-joint speed (deg/s, whole degrees, <= v_max) whose peak TCP speed stays <= tcp_limit mm/s.
    The xArm firmware limits the TCP to 1000 mm/s (UFACTORY: TCP 1000 mm/s, joints 180 deg/s, 1146 deg/s^2); one
    joint speed for every move drove the tool tip to 2.4-2.9 m/s on the long swings at 180 deg/s."""
    d, k = tcp_speed_profile(j_from, j_to)
    if d <= 0 or peak_tcp_speed(d, k, v_max, acc) <= tcp_limit:
        return float(v_max)
    lo, hi = v_min, v_max
    for _ in range(20):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if peak_tcp_speed(d, k, mid, acc) <= tcp_limit else (lo, mid)
    return float(max(v_min, math.floor(lo)))
