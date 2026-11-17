import sys, itertools, math; sys.path.insert(0, '.')
import numpy as np
import sort as S
from vh import coverage
from vh.kinematics import check_path, ik, load_obstacles, body_points, tcp, frames, TCP_MM
TZ = 6.5
OBS = load_obstacles(table_z=TZ)
LENS = 190.0
def part_box(x, y, yaw, L=65, w=18, h=18):
    a = math.radians(yaw); ex = abs(math.cos(a)) * L / 2 + abs(math.sin(a)) * w / 2; ey = abs(math.sin(a)) * L / 2 + abs(math.cos(a)) * w / 2
    return ("part", ((x, y, TZ + h / 2), (2 * ex + 10, 2 * ey + 10, h + 4)))
def look_q(x, y):   # wrist lens straight above the part at LENS (camera offset from flange as measured)
    cam = np.array([x, y, TZ + LENS]); ray = np.array([0, 0, 1.0])
    def res(q, reg):
        F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]
        return list((t + R @ coverage.CAM_IN_FLANGE - cam) / 5) + list((R[:, 2] + ray) * 50) + list((np.asarray(q) - S.WATCH_J) * reg)
    return [float(v) for v in coverage._lsq(res, np.array(S.WATCH_J, float))]
def raised(q, along_mm):
    """same orientation, lens backed off along its own axis"""
    F = frames(q)[-1]; R, t = F[:3, :3], F[:3, 3]; tgt = t - R[:, 2] * along_mm
    def res(v, reg):
        G = frames(v)[-1]; return list((G[:3, 3] - tgt) / 5) + list((G[:3, :3] - R).ravel() * 50) + list((np.asarray(v) - q) * reg)
    return [float(v) for v in coverage._lsq(res, np.array(q, float))]
stats = {}
for x, y, yaw in itertools.product(np.linspace(170, 380, 5), np.linspace(230, 470, 5), (0, 45, 90, 135)):
    obs = OBS + [part_box(x, y, yaw)]
    lq = look_q(x, y)
    for phi in (45, -45):
        cands = coverage.oblique_candidates(x, y, yaw, phi, TZ, lq, OBS)
        res = "none"
        for d, q in cands:
            static_part = check_path(q, q, obs, holding=False, margin=0, steps=1)
            if not static_part[0]:
                res = res if res != "none" else "pose hits part"; continue
            if check_path(lq, q, obs, holding=False, margin=0)[0]:
                res = "direct"; break
            w = raised(q, 120)
            if check_path(lq, w, obs, holding=False, margin=0)[0] and check_path(w, q, obs, holding=False, margin=0)[0]:
                res = "via raised"; break
        stats[(phi, res)] = stats.get((phi, res), 0) + 1
for k in sorted(stats): print(k, stats[k])
