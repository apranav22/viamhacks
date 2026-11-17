"""Oblique wrist-cam looks: lens at distance d from the part, tilted phi about the part's long axis.
Full-orientation IK on the URDF; obstacle + table clearance of the static pose and the joint path from the top look."""
import math, sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vh.kinematics import frames, body_points, load_obstacles, check_path, ik, JOINT_LIMITS, tcp

CAM_IN_FLANGE = np.array([67.5, -23.1, 17.5])     # live frame system 2026-11-14 10:15, camera axis = flange z
SURF = 6.5                                         # cardboard surface z
WATCH_J = [57.13, 6.59, -40.35, 0.0, -46.93, 57.13]
OBS = load_obstacles()

def pose_ik(cam_pos, axis, yhint, seed):
    axis = axis / np.linalg.norm(axis)
    def res(q, reg):
        F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]
        c = t + R @ CAM_IN_FLANGE
        r = list((c - cam_pos) / 5.0) + list((R[:, 2] - axis) * 50) + list(np.cross(R[:, 1], yhint) * 50)
        return r + list((np.asarray(q) - seed) * reg)
    q = least_squares(lambda v: res(v, 0.02), seed, method="lm").x
    q = least_squares(lambda v: res(v, 0.0), q, method="lm", xtol=1e-9).x
    q[5] -= 360 * round((q[5] - seed[5]) / 360); q[3] -= 360 * round((q[3] - seed[3]) / 360)
    F = frames(q)[-1]; c = F[:3, 3] + F[:3, :3] @ CAM_IN_FLANGE
    err = np.linalg.norm(c - cam_pos); ang = math.degrees(math.acos(np.clip(F[:3, 2] @ axis, -1, 1)))
    lim = all(lo <= v <= hi for v, (lo, hi) in zip(q, JOINT_LIMITS))
    return [round(float(v), 2) for v in q], err, ang, lim

def static_clear(q):
    bp = body_points(q, holding=False)
    worst = (1e9, "")
    for name, (c, d) in OBS:
        c, h = np.array(c, float), np.array(d, float) / 2
        for p, r in bp:
            qq = np.abs(p - c) - h
            cl = np.linalg.norm(np.maximum(qq, 0)) + min(qq.max(), 0) - r
            if cl < worst[0]: worst = (cl, name)
    return worst

def oblique(x, y, yaw, phi, d, seed):
    A = np.array([math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0])
    n = np.array([-A[1], A[0], 0])
    part = np.array([x, y, SURF + 5])
    dirv = math.cos(math.radians(phi)) * np.array([0, 0, 1]) + math.sin(math.radians(phi)) * n
    cam = part + d * dirv
    best = None
    for s in (1, -1):                       # flange y along +-A: claws spread along the part, horizontal
        q, err, ang, lim = pose_ik(cam, -dirv, s * A, np.array(seed, float))
        if err > 2 or ang > 1 or not lim: continue
        cl, where = static_clear(q)
        cand = (cl, q, where)
        if best is None or cl > best[0]: best = cand
    return best

if __name__ == "__main__":
    import itertools
    xs, ys = np.linspace(170, 380, 4), np.linspace(220, 480, 4)
    for d in (190, 230):
        for phi in (45, 60):
            ok = tot = 0; worst = []
            for x, y, yaw in itertools.product(xs, ys, (0, 45, 90, 135)):
                top = ik(np.array([x, y, SURF + 5 + d + 20]), seed=WATCH_J)[0]
                good = True
                for sgn in (1, -1):
                    tot += 1
                    r = oblique(x, y, yaw, sgn * phi, d, top)
                    if r is None: good = False; worst.append((x, y, yaw, sgn * phi, "ik")); continue
                    cl, q, where = r
                    pok, pc, pw = check_path(top, q, OBS, holding=False, margin=10)
                    if cl >= 10 and pok: ok += 1
                    else: worst.append((x, y, yaw, sgn * phi, round(min(cl, pc), 1), where if cl < 10 else pw[:30]))
            print(f"d={d} phi=±{phi}: {ok}/{tot} poses reachable & clear")
            for w in worst[:6]: print("   fail", w)
