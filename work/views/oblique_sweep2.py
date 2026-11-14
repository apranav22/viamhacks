import sys, itertools; sys.path.insert(0, "work/views")
from oblique import *
xs, ys = np.linspace(170, 380, 4), np.linspace(220, 480, 4)
for d, phi in ((230, 45), (260, 45), (260, 50), (300, 45)):
    fails = []; ok = tot = 0
    for x, y, yaw in itertools.product(xs, ys, (0, 45, 90, 135)):
        top = ik(np.array([x, y, SURF + 5 + 210]), seed=WATCH_J)[0]
        for sgn in (1, -1):
            tot += 1
            r = oblique(x, y, yaw, sgn * phi, d, top)
            if r is None:
                # retry seeded from the flipped wrist
                fails.append((int(x), int(y), yaw, sgn * phi, "ik")); continue
            cl, q, where = r
            pok, pc, pw = check_path(top, q, OBS, holding=False, margin=10)
            if cl >= 10 and pok: ok += 1
            else: fails.append((int(x), int(y), yaw, sgn * phi, round(min(cl, pc)), (where if cl < 10 else pw).split(" ")[0]))
    print(f"d={d} phi=±{phi}: {ok}/{tot}")
    if d == 230: [print("  ", f) for f in fails]
