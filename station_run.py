"""Run sort.py ON the Intel station (data lands in the station's shared runs/, model inference on the station).
The laptop only shows the dashboard (UDP telemetry to --dash-host). Moves the arm only via sort.py on the station.

    python station_run.py start -- --mode collect --background cardboard --label good --type socket_thin_long --reps 30
    python station_run.py status            # last log lines + whether it is running
    python station_run.py stop              # SIGTERM, then verifies the process is gone (SIGKILL after 5 s)

One loop at a time: start refuses while any sort.py runs on the station (or on this laptop).
"""
import argparse
import asyncio
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from station import connect                     # noqa: E402
from station_shell import execute               # noqa: E402

BASE = "/opt/viam/sorter-ali"
LOG = f"{BASE}/station_run.log"
PIDF = f"{BASE}/station_run.pid"


def laptop_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("172.16.0.182", 1))
        return s.getsockname()[0]


async def main(a):
    async with await connect() as m:
        if a.cmd == "start":
            if subprocess.run(["pgrep", "-f", "sort.py --mode"], capture_output=True).returncode == 0:
                raise SystemExit("a sort.py loop runs on this laptop; stop it first")
            rc, out = await execute(m, "pgrep -f 'python3.12 -u sort.py' || true")
            if out.strip():
                raise SystemExit(f"sort.py already running on the station: {out.strip()}")
            args = " ".join(shlex.quote(x) for x in a.rest)
            # setsid: fully detach, or the shell stream stays open until the run ends (19:15: start timed out)
            cmd = (f"cd {BASE}/current && setsid nohup {BASE}/.venv/bin/python3.12 -u sort.py {args} "
                   f"--dash-host {laptop_ip()} > {LOG} 2>&1 < /dev/null & echo $! > {PIDF}; sleep 1; cat {PIDF}")
            try:
                rc, out = await execute(m, cmd, 30)
                print("started on station, pid", out.strip())
            except TimeoutError:
                print("start command timed out on the shell stream; checking status")
            time.sleep(6)
        if a.cmd == "stop":
            # by process match, not the pid file: setsid forks, so the file held the wrapper's pid (19:36 stop missed it)
            q = "pgrep -f 'python3.12 -u sort.py'"
            rc, out = await execute(m, f"P=$({q}); [ -n \"$P\" ] && kill -TERM $P; for i in 1 2 3 4 5; do {q} >/dev/null || break; "
                                       f"sleep 1; done; {q} >/dev/null && kill -9 $({q}); sleep 1; {q} && echo STILL RUNNING || echo stopped", 30)
            print(out.strip())
            return
        rc, out = await execute(m, f"grep -v rpc.dial {LOG} | tail -n {a.lines}; "
                                   "pgrep -f 'python3.12 -u sort.py' >/dev/null && echo '== RUNNING' || echo '== NOT RUNNING'", 30)
        print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["start", "status", "stop"])
    ap.add_argument("--lines", type=int, default=12)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    a.rest = [x for x in a.rest if x != "--"]
    asyncio.run(main(a))
