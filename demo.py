"""Demo quickstart: one command to run the live sort on the station (OpenVINO models live there).

    python demo.py check            # read-only: nobody else driving, arm still at the watch pose, nothing running
    python demo.py start            # check, then start the demo sort on the station (MOVES THE ARM)
    python demo.py start --items 10
    python demo.py status           # last log lines on the station
    python demo.py stop             # stop the run (the arm finishes its move; speed is restored)

Before `start`: a person at the E-stop, ONE part lying flat on the cardboard pad. Add the next part when the arm is
back at the watch pose. Watch it live on the station dashboard: http://172.16.0.182:8775 (preview) or :8765.

Runs the station's current release unchanged (scripts: station_run.py) with the demo settings below. --assume-lying
skips the depth upright check: in release 20261114_120758 a part judged upright in sort mode crashes the run
('Sorter' object has no attribute 'pose', 12:31), and the depth look sometimes reads a lying part as 36-48 mm. So
lay every part flat: a standing part would be grasped like a lying one (its top can reach the wrist sensor).
"""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from station import connect                     # noqa: E402
from station_shell import execute               # noqa: E402
from vh.config import CHECKPOINT as CP          # noqa: E402

DEMO = ["--mode", "sort", "--background", "cardboard", "--views", "coverage",
        "--anomaly-bundle", "models/each_cardboard_v4/bundle_m103.json", "--type", "auto", "--decide", "top",
        "--assume-lying", "--dash-host", "127.0.0.1", "--dash-port", "8776"]


async def check():
    """Problems that block a start (empty list: clear to go)."""
    from viam.components.arm import Arm
    from viam.services.generic import Generic
    problems = []
    async with await connect() as m:
        if (await Generic.from_robot(m, "teleop").do_command({"command": "status"})).get("running"):
            problems.append("teleop is running")
        arm = Arm.from_robot(m, "arm")
        j0 = list((await arm.get_joint_positions()).values)
        await asyncio.sleep(2)
        j1 = list((await arm.get_joint_positions()).values)
        if max(abs(a - b) for a, b in zip(j0, j1)) > 0.2:
            problems.append("the arm is moving: someone else is driving")
        far = max(abs(a - b) for a, b in zip(j1, CP["watch_pose"]["joints_deg"]))
        rc, out = await execute(m, "pgrep -af 'python3.12 -u sort.py' | grep -v pgrep || true", 30)
        if out.strip():
            problems.append(f"sort.py already runs on the station: {out.strip()}")
    if subprocess.run(["pgrep", "-f", "sort.py --mode"], capture_output=True).returncode == 0:
        problems.append("sort.py runs on this laptop")
    print(f"arm {far:.1f} deg from the watch pose (the run starts by moving there)")
    return problems


def station_run(*args):
    return subprocess.call([sys.executable, str(ROOT / "station_run.py"), *args])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "start", "status", "stop"])
    ap.add_argument("--items", type=int, default=6)
    a = ap.parse_args()
    if a.cmd in ("status", "stop"):
        sys.exit(station_run(a.cmd, "--lines", "25"))
    problems = asyncio.run(check())
    for p in problems:
        print("NOT READY:", p)
    if problems or a.cmd == "check":
        sys.exit(1 if problems else 0)
    print("READY. Person at the E-stop? One part lying flat on the pad? Starting the demo sort on the station.")
    sys.exit(station_run("start", "--", *DEMO, "--items", str(a.items)))


if __name__ == "__main__":
    main()
