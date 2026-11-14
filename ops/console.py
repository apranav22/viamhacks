"""Local ops console for the demo: one HTTP server on 127.0.0.1 that a browser page and a Stream Deck both drive.

    ..\\.venv\\Scripts\\python.exe ops\\console.py            # http://127.0.0.1:8790

Read-only (any time, any number of presses):
    GET /api/status      station_run.py status equivalent: last log lines + RUNNING / NOT RUNNING
    GET /api/health      hostname, uptime, disk, pgrep sort.py on the station
    GET /api/decisions   last rows of the newest run's decisions.jsonl (the judge log) + counts
    GET /api/snapshot?cam=overview-cam|cam   one JPEG through the Viam SDK
    GET /api/bench       tools/device_bench.py results saved on the station (incoming/device_bench.out)
    GET /api/state       everything above that is cached, plus the arm/confirm state (the page polls this)

Arm motion (only when an operator presses; see AGENTS.md section 2):
    GET /api/arm?preset=judged      step 1: arms that preset for 5 s, asks "person at E-stop?"
    GET /api/confirm?preset=judged  step 2: within 5 s, runs  station_run.py start -- <preset args> --dash-host 127.0.0.1
    GET /api/stop                   always one press: station_run.py stop (SIGTERM, SIGKILL after 5 s). Also disarms.

GET everywhere so the Stream Deck "Website" action (background GET) can call it. Refusals return HTTP 409 so the
Stream Deck key shows its alert triangle. Binds 127.0.0.1 plus any --host given (the Tailscale IP, so the Stream Deck on
the laptop can reach it; anyone on the tailnet can then press these, nobody else). Every start/stop is appended to docs/AGENT_LOG.md.
"""
import argparse
import asyncio
import json
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from station import connect                  # noqa: E402
from station_run import BASE, LOG            # noqa: E402  same paths the tested launcher uses
from station_shell import execute            # noqa: E402

ARM_WINDOW_S = 5.0
SORT_Q = "pgrep -f 'python3.12 -u sort.py'"   # same match station_run.py uses
CAMS = ("overview-cam", "cam")
ACTION_LOG = ROOT / "logs" / "ops_console.log"
AGENT_LOG = ROOT / "docs" / "AGENT_LOG.md"
IDENTITY = "[ops console · op Aayush Poudel (git: Aayush Poudel) · Windows laptop · aayush/streamdeck-ops]"


def now():
    return datetime.now().strftime("%H:%M:%S")


class Station:
    """One persistent Viam connection on a private asyncio loop; reconnects after any failure."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.machine = None
        self.lock = None

    def call(self, fn, timeout=40):
        return asyncio.run_coroutine_threadsafe(self._guarded(fn), self.loop).result(timeout)

    async def _guarded(self, fn):
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:                     # one RPC at a time over the shared WebRTC transport
            try:
                if self.machine is None:
                    self.machine = await asyncio.wait_for(connect(), 30)
                return await fn(self.machine)
            except BaseException:
                m, self.machine = self.machine, None
                if m is not None:
                    try:
                        await asyncio.wait_for(m.close(), 5)
                    except BaseException:
                        pass
                raise

    def sh(self, cmd, timeout=30):
        async def go(m):
            return await execute(m, cmd, timeout)
        return self.call(go, timeout + 10)

    def snapshot(self, name):
        async def go(m):
            import viam.components.camera  # noqa: F401  registers the client
            from viam.components.camera import Camera
            cam = Camera.from_robot(m, name)
            imgs, _ = await asyncio.wait_for(cam.get_images(filter_source_names=["color"] if name == "cam" else None), 15)
            img = next((i for i in imgs if "jpeg" in i.mime_type), imgs[0])
            return bytes(img.data), img.mime_type
        return self.call(go, 30)


class Console:
    def __init__(self, python, presets_path):
        self.st = Station()
        self.python = python
        self.presets = {k: v for k, v in json.loads(Path(presets_path).read_text()).items() if not k.startswith("_")}
        self.lock = threading.Lock()
        self.armed = None                           # (preset, monotonic time)
        self.job = None                             # {"kind": start|stop, "preset", "started", "output", "rc", "ended"}
        self.cache = {}                             # name -> {"t": epoch, "data" | "error"}
        self.snaps = {}                             # cam -> (epoch, bytes, mime)

    # ---- helpers ----------------------------------------------------------------------------
    def log(self, line, agent_log=False):
        ACTION_LOG.parent.mkdir(exist_ok=True)
        with ACTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
        if agent_log:
            try:
                with AGENT_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(f"\n{IDENTITY[:-1]} · {now()}]\n{line}\n")
            except OSError:
                pass

    def cached(self, name, fn):
        try:
            data = fn()
            self.cache[name] = {"t": time.time(), "data": data}
        except Exception as e:
            self.cache[name] = {"t": time.time(), "error": f"{type(e).__name__}: {e}"[:300]}
        return self.cache[name]

    # ---- read-only ----------------------------------------------------------------------------
    def status(self, lines=15):
        def fn():
            rc, out = self.st.sh(f"grep -v rpc.dial {LOG} | tail -n {int(lines)}; "
                                 f"{SORT_Q} >/dev/null && echo '== RUNNING' || echo '== NOT RUNNING'")
            out = out.rstrip()
            return {"running": out.endswith("== RUNNING"), "log": out.rsplit("\n", 1)[0] if "\n" in out else ""}
        return self.cached("status", fn)

    def health(self):
        def fn():
            rc, out = self.st.sh(f"echo \"host=$(hostname)\"; echo \"uptime=$(uptime)\"; "
                                 f"echo \"disk=$(df -h / | tail -1 | awk '{{print $5\" used, \"$4\" free\"}}')\"; "
                                 f"echo \"release=$(readlink -f {BASE}/current)\"; "
                                 f"P=$({SORT_Q} | tr '\\n' ' '); echo \"sort_py=${{P:-none}}\"")
            return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        return self.cached("health", fn)

    def decisions(self, n=10):
        def fn():
            rc, out = self.st.sh(f"D=$(ls -td {BASE}/runs/*/ 2>/dev/null | head -1); echo \"$D\"; "
                                 f"tail -n 300 \"$D/decisions.jsonl\" 2>/dev/null")
            lines = out.splitlines()
            run = lines[0].rstrip("/").rsplit("/", 1)[-1] if lines else ""
            recs = []
            for ln in lines[1:]:
                try:
                    recs.append(json.loads(ln))
                except ValueError:
                    pass
            rows = [{"item": r.get("item"), "decision": r.get("decision"), "reason": (r.get("reason") or "")[:90],
                     "view": r.get("decided_at_view"), "latency_ms": r.get("latency_ms"), "cycle_s": r.get("cycle_s"),
                     "confidence": r.get("confidence"), "t_seen": (r.get("t_seen") or "")[11:19]} for r in recs]
            counts = {}
            for r in recs:
                counts[r.get("decision")] = counts.get(r.get("decision"), 0) + 1
            lat = sorted(r["latency_ms"] for r in recs if isinstance(r.get("latency_ms"), (int, float)))
            return {"run": run, "count": len(recs), "counts": counts,
                    "latency_p50_ms": lat[len(lat) // 2] if lat else None, "rows": rows[-int(n):]}
        return self.cached("decisions", fn)

    def bench(self):
        def fn():
            rc, out = self.st.sh(f"cat {BASE}/incoming/device_bench.out; stat -c %y {BASE}/incoming/device_bench.out")
            rows, when = [], ""
            for ln in out.splitlines():
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    when = ln[:19]
            return {"measured": when, "rows": rows}
        return self.cached("bench", fn)

    def snapshot(self, cam):
        if cam not in CAMS:
            raise ValueError(f"cam must be one of {', '.join(CAMS)}")
        t, data, mime = self.snaps.get(cam, (0, None, None))
        if time.time() - t > 1.0:
            data, mime = self.st.snapshot(cam)
            self.snaps[cam] = (time.time(), data, mime)
        return data, mime

    # ---- motion: arm / confirm / stop -----------------------------------------------------------
    def arm(self, preset):
        if preset not in self.presets:
            return 409, {"error": f"unknown preset {preset!r}", "presets": list(self.presets)}
        with self.lock:
            if self.job and not self.job.get("ended"):
                return 409, {"error": f"{self.job['kind']} still in progress"}
            self.armed = (preset, time.monotonic())
        self.log(f"ARMED {preset} (confirm within {ARM_WINDOW_S:.0f} s)")
        return 200, {"armed": preset, "expires_in_s": ARM_WINDOW_S, "ask": "Person at the E-stop? Then press CONFIRM.",
                     "command": self.command(preset)}

    def command(self, preset):
        return ["station_run.py", "start", "--", *self.presets[preset]["args"], "--dash-host", "127.0.0.1"]

    def confirm(self, preset=None):
        with self.lock:
            armed, self.armed = self.armed, None
            if not armed:
                return 409, {"error": "not armed: press ARM (or a start key) first"}
            name, t = armed
            if time.monotonic() - t > ARM_WINDOW_S:
                return 409, {"error": f"arm expired ({ARM_WINDOW_S:.0f} s): press ARM again"}
            if preset and preset != name:
                return 409, {"error": f"armed {name!r} but confirm was for {preset!r}: press ARM again"}
            if self.job and not self.job.get("ended"):
                return 409, {"error": f"{self.job['kind']} still in progress"}
            self.job = {"kind": "start", "preset": name, "started": time.time(), "output": "", "rc": None, "ended": None}
            job = self.job
        threading.Thread(target=self._start, args=(job, name), daemon=True).start()
        return 200, {"starting": name, "command": self.command(name)}

    def _start(self, job, name):
        args = self.presets[name]["args"]
        try:
            # preflight (read-only): nothing running, and the deployed sort.py knows every flag of the preset
            flags = sorted({a.split("=")[0] for a in args if a.startswith("--")})
            checks = "; ".join(f"grep -q -- '\"{f}\"' {BASE}/current/sort.py || echo MISSING {f}" for f in flags)
            rc, out = self.st.sh(f"{SORT_Q} && echo ALREADY_RUNNING; {checks}; true")
            if "ALREADY_RUNNING" in out or "MISSING" in out:
                job["output"] = "refused before start: " + out.replace("\n", " ").strip()
                job["rc"] = 2
                self.log(f"START {name} refused: {job['output']}")
                return
            cmd = [self.python, "-u", *self.command(name)]
            self.log(f"ARM: taken by the operator via the ops console (Stream Deck / page, two-step confirm, "
                     f"person at E-stop attested), preset {name}: {' '.join(shlex.quote(c) for c in cmd[2:])}",
                     agent_log=True)
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
            job["output"] = (p.stdout + p.stderr).strip()[-3000:]
            job["rc"] = p.returncode
            self.log(f"START {name} rc={p.returncode}: {job['output'][-300:]}")
        except Exception as e:
            job["output"] += f"\nconsole error: {type(e).__name__}: {e}"
            job["rc"] = 1
            self.log(f"START {name} error: {e}")
        finally:
            job["ended"] = time.time()

    def stop(self):
        with self.lock:
            self.armed = None
            job = {"kind": "stop", "preset": None, "started": time.time(), "output": "", "rc": None, "ended": None}
            self.job = job            # a stop always runs, even while a start is still launching
        self.log("STOP pressed")
        threading.Thread(target=self._stop, args=(job,), daemon=True).start()
        return 200, {"stopping": True}

    def _stop(self, job):
        try:
            p = subprocess.run([self.python, "-u", "station_run.py", "stop"], cwd=ROOT, capture_output=True,
                               text=True, timeout=90)
            job["output"] = (p.stdout + p.stderr).strip()[-2000:]
            job["rc"] = p.returncode
            self.log(f"ARM: released (STOP via ops console): {job['output'][-200:]}", agent_log=True)
        except Exception as e:
            job["output"] = f"console error: {type(e).__name__}: {e}"
            job["rc"] = 1
            self.log(f"STOP error: {e}")
        finally:
            job["ended"] = time.time()

    def state(self):
        armed = None
        if self.armed and time.monotonic() - self.armed[1] <= ARM_WINDOW_S:
            armed = {"preset": self.armed[0], "left_s": round(ARM_WINDOW_S - (time.monotonic() - self.armed[1]), 1)}
        return {"now": time.time(), "armed": armed, "job": self.job, "cache": self.cache,
                "presets": {k: {"title": v["title"], "command": self.command(k)} for k, v in self.presets.items()}}


def refresher(c, period):
    """Keep status/decisions/health fresh for the page, so a key press never waits on a cold cache."""
    i = 0
    while True:
        c.status()
        c.decisions()
        if i % 6 == 0:
            c.health()
        if i % 30 == 0:
            c.bench()
        i += 1
        time.sleep(period)


def make_handler(c):
    page = (HERE / "index.html").read_bytes()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            if not isinstance(body, (bytes, bytearray)):
                body = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            path = u.path.rstrip("/") or "/"
            try:
                if path == "/":
                    return self.send(200, page, "text/html; charset=utf-8")
                if path == "/api/state":
                    return self.send(200, c.state())
                if path in ("/api/status", "/api/health", "/api/decisions", "/api/bench"):
                    r = getattr(c, path.rsplit("/", 1)[1])()
                    return self.send(502 if "error" in r else 200, r)
                if path == "/api/snapshot":
                    data, mime = c.snapshot(q.get("cam", "overview-cam"))
                    return self.send(200, data, mime)
                if path == "/api/arm":
                    return self.send(*c.arm(q.get("preset", "judged")))
                if path == "/api/confirm":
                    return self.send(*c.confirm(q.get("preset")))
                if path == "/api/stop":
                    return self.send(*c.stop())
                return self.send(404, {"error": "not found"})
            except Exception as e:
                return self.send(502, {"error": f"{type(e).__name__}: {e}"[:300]})

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--host", action="append", default=None,
                    help="address to bind, repeatable (default 127.0.0.1). Add this PC's Tailscale IP so a Stream Deck "
                         "on another tailnet machine can call it; never 0.0.0.0 (venue/home LAN)")
    ap.add_argument("--presets", default=str(HERE / "presets.json"))
    ap.add_argument("--refresh-s", type=float, default=3.0, help="background refresh of status/decisions")
    a = ap.parse_args()
    c = Console(sys.executable, a.presets)
    threading.Thread(target=refresher, args=(c, a.refresh_s), daemon=True).start()
    hosts = a.host or ["127.0.0.1"]
    if "0.0.0.0" in hosts or "::" in hosts:
        raise SystemExit("refusing to bind every interface; pass 127.0.0.1 and/or the Tailscale IP")
    servers = [ThreadingHTTPServer((h, a.port), make_handler(c)) for h in hosts]
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"ops console on {', '.join(f'http://{h}:{a.port}' for h in hosts)}  (presets: {', '.join(c.presets)})",
          flush=True)
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
