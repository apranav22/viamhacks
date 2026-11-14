"""Which webcam presentations put clean wall (not gripper/RealSense/cable) behind the held part?
Part held across the jaws: long axis = flange x, closing = flange y, underside faces +flange z (tool axis)."""
import json, math, sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vh.kinematics import frames, check_path, load_obstacles, JOINT_LIMITS, TCP_MM
CP = json.load(open("config/checkpoint.json"))
P = np.array(CP["webcam"]["P_world_to_px"]); LENS = np.array(CP["webcam"]["lens_world_mm"], float)
C = np.array(CP["webcam"]["optical_axis_world"], float); C /= np.linalg.norm(C)
OBS = load_obstacles(); FRONT = [-12.67, -52.37, -62.3, -202.02, 111.71, 176.24]
CENTER = np.array([285.0, -150.0, 260.0]) + np.array([-0.966, -0.14, 0.217]) * 25   # held part ~ where it is today

def boxpts(lo, hi, n=7):
    g = [np.linspace(a, b, n) for a, b in zip(lo, hi)]
    return np.stack(np.meshgrid(*g), -1).reshape(-1, 3)
GRIPPER = np.vstack([boxpts((-45, -60, 0), (45, 60, 115), 9),          # housing
                     boxpts((-12, -45, 115), (12, -8, 168), 5), boxpts((-12, 8, 115), (12, 45, 168), 5)])  # fingers
REALSENSE = boxpts((55, -70, 0), (85, 70, 30), 7)
CABLE = boxpts((70, 70, 0), (75, 120, 15), 4)
def part(L=65, r=6):
    s = np.linspace(-L / 2, L / 2, 40); a = np.linspace(0, 2 * np.pi, 16)
    S, A = np.meshgrid(s, a)
    return np.stack([S, r * np.cos(A), TCP_MM + 12 + r * np.sin(A)], -1).reshape(-1, 3)   # held at the tips

def proj(W):
    h = np.c_[W, np.ones(len(W))] @ P.T
    return h[:, :2] / h[:, 2:3], (W - LENS) @ C

def solve(axis, xhint, seed=FRONT):
    """flange z = axis (tool), flange x ~ xhint (part long axis); part centre at CENTER."""
    axis = axis / np.linalg.norm(axis)
    def res(q, reg):
        F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]
        pc = t + R @ np.array([0, 0, TCP_MM + 12])
        return list((pc - CENTER) / 5) + list((R[:, 2] - axis) * 50) + list((R[:, 0] - xhint / np.linalg.norm(xhint)) * 50) + list((np.asarray(q) - seed) * reg)
    q = least_squares(lambda v: res(v, .02), seed, method="lm").x
    q = least_squares(lambda v: res(v, 0), q, method="lm", xtol=1e-9).x
    return q

def score(q, label):
    F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]
    W = lambda pts: pts @ R.T + t
    pp, pd = proj(W(part()))
    lim = all(lo <= v <= hi for v, (lo, hi) in zip(q, JOINT_LIMITS))
    ok, cl, where = check_path(FRONT, q, OBS, holding=True, margin=10)
    # rasterise at 1/8 res
    def mask(pts):
        uv, dep = proj(W(pts)); m = {}
        for (u, v), d in zip((uv / 8).astype(int), dep): m[(u, v)] = min(d, m.get((u, v), 1e9))
        return m
    pm, gm = mask(part()), {}
    for b in (GRIPPER, REALSENSE, CABLE):
        for k, d in mask(b).items(): gm[k] = min(d, gm.get(k, 1e9))
    # dilate gripper mask by 1 cell (sparse sampling)
    g2 = {}
    for (u, v), d in gm.items():
        for du in (-1, 0, 1):
            for dv in (-1, 0, 1): g2[(u + du, v + dv)] = min(d, g2.get((u + du, v + dv), 1e9))
    behind = sum(1 for k, d in pm.items() if k in g2 and g2[k] > d) / len(pm)
    front = sum(1 for k, d in pm.items() if k in g2 and g2[k] < d - 5) / len(pm)
    # how much of the underside (+z normals) faces the lens
    view = LENS - (t + R @ np.array([0, 0, TCP_MM + 12])); view /= np.linalg.norm(view)
    under = math.degrees(math.acos(np.clip(R[:, 2] @ view, -1, 1)))
    box = pp.min(0).round().tolist() + pp.max(0).round().tolist()
    print(f"{label:28s} limits={'ok' if lim else 'NO'} path={'ok' if ok else 'BLOCKED'}({cl:.0f}mm) part-on-gripper-bg={behind:4.0%} "
          f"occluded={front:4.0%} underside-normal-to-lens={under:5.1f}deg bbox={box}")
    return q

if __name__ == "__main__":
    up = np.array([0, 0, 1.0]); side = np.cross(C, up); side /= np.linalg.norm(side)
    toward = -C
    # A (part axis) vertical in the image, like today; tilt the tool about A
    for A, an in ((up - (up @ C) * C, "A vertical"), (side, "A horizontal")):
        A = A / np.linalg.norm(A)
        n = np.cross(A, toward)
        for tilt in (0, 30, 45, 60, 90):
            for s in ((1, -1) if tilt else (1,)):
                ax = math.cos(math.radians(tilt)) * toward + math.sin(math.radians(tilt)) * s * n
                score(solve(ax, A), f"{an} tilt {s*tilt:+d}")
    # end views: part axis at the lens, tool pointing down / sideways
    for ax, an in ((-up, "tool down"), (side, "tool sideways")):
        for s in (1, -1):
            score(solve(ax, s * toward), f"end-on ({an}, {'+' if s>0 else '-'}end)")
