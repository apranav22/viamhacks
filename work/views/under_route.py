"""Lift (z 280) -> under: direct vs via a raised waypoint (same tool orientation, TCP up dz), over pick-zone samples."""
import sys, random; sys.path.insert(0, '.')
import numpy as np
from vh.kinematics import check_path, load_obstacles, ik, frames
from vh import coverage
import sort
obs = load_obstacles()
vj = dict(sort.VIEW_J); vj.update(coverage.webcam_views(sort.CP["views"]["front"]["joints_deg"]))
U = vj["under"]
random.seed(1)
res = {}
for dz in (80, 120, 160):
    wp = coverage.raised(U, dz)
    ok_d = ok_w = 0; n = 0
    for _ in range(60):
        x, y = random.uniform(180, 330), random.uniform(250, 420)
        try: L = ik(np.array([x, y, 280.0]), seed=sort.WATCH_J, jaw_heading_deg=random.uniform(0, 180))[0]
        except ValueError: continue
        n += 1
        d = check_path(L, U, obs, True, margin=0)[0]
        w = d or (check_path(L, wp, obs, True, margin=0)[0] and check_path(wp, U, obs, True, margin=0)[0])
        ok_d += d; ok_w += w
    print(f"dz {dz}: wp {wp} direct {ok_d}/{n} with waypoint {ok_w}/{n}  wp->U {check_path(wp,U,obs,True,margin=0)[1]}")
