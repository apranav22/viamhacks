"""Start / stop sort.py from the dashboard: a capture run (--mode collect) or live anomaly detection (--mode sort).

The browser sends a small JSON spec; only whitelisted options become sort.py arguments (no free-form command line).
AGENTS.md section 2 still applies. The button press is the operator's go-ahead for this one run, and the request must
confirm that a person is at the E-stop. sort.py itself refuses to move while teleop runs or while the joints are
changing (someone else is driving). Start is also refused while any run is active here or another sort.py runs on
this computer. Every start and end is appended to docs/AGENT_LOG.md as "ARM: taken" / "ARM: released".

Targets: "local" runs sort.py on this computer (telemetry to this dashboard). "station" runs the DEPLOYED release on
the Intel station through station_run.py (telemetry comes back to this computer's address).
"""
import json
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL_RE = re.compile(r"^(good|tape|other:[a-z0-9_+-]{1,32})$")
BUNDLE_RE = re.compile(r"^(active|models/[A-Za-z0-9_.-]+/bundle[A-Za-z0-9_.-]*\.json)$")
DEFAULT_BUNDLE = "models/each_cardboard_v4/bundle_m103.json"


def _git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"


def identity(kind):
    op = _git("config", "user.name")
    return f"[dashboard/{kind}-button · op {op} (git: {op}) · {socket.gethostname()} · {_git('branch', '--show-current')} · {time.strftime('%Y-%m-%d %H:%M')}]"


def part_types(root=ROOT):
    try:
        sizes = json.loads((root / "config" / "part_sizes.json").read_text())
    except (OSError, ValueError):
        return []
    return sorted(k for k in sizes if not k.startswith("_"))


def bundles(root=ROOT):
    out = ["active"] if (root / "models" / "ACTIVE").exists() else []
    out += sorted(str(p.relative_to(root)) for p in (root / "models").glob("*/bundle*.json"))
    return out


def _int(spec, key, default, lo, hi):
    try:
        v = int(spec.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a whole number")
    if not lo <= v <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return v


def _choice(spec, key, default, choices):
    v = spec.get(key, default)
    if v not in choices:
        raise ValueError(f"{key} must be one of {', '.join(choices)}")
    return v


def build_args(spec, types=None):
    """Validated sort.py arguments for a dashboard spec. Raises ValueError with a message for the operator."""
    kind = _choice(spec, "kind", None, ("capture", "detect"))
    args = ["--background", _choice(spec, "background", "cardboard", ("white", "cardboard")),
            "--views", _choice(spec, "views", "classic", ("classic", "coverage")),
            "--watch-timeout", str(_int(spec, "watch_timeout", 300, 10, 3600))]
    if kind == "capture":
        types = part_types() if types is None else types
        part = spec.get("type", "unknown")
        if part != "unknown" and part not in types:
            raise ValueError(f"unknown part type {part!r}")
        label = str(spec.get("label", "good"))
        if not LABEL_RE.match(label):
            raise ValueError("label must be good, tape or other:<what> (lowercase letters, digits, _ + -)")
        args = ["--mode", "collect", "--type", part, "--label", label, "--reps", str(_int(spec, "reps", 10, 1, 200))] + args
        if spec.get("assume_lying"):
            args.append("--assume-lying")
    else:
        bundle = str(spec.get("bundle", DEFAULT_BUNDLE))
        if not BUNDLE_RE.match(bundle):
            raise ValueError("bundle must be 'active' or models/<name>/bundle*.json")
        args = ["--mode", "sort", "--items", str(_int(spec, "items", 6, 1, 200)), "--anomaly-bundle", bundle,
                "--decide", _choice(spec, "decide", "all", ("all", "top")),
                "--anomaly-device", _choice(spec, "device", "CPU", ("CPU", "GPU", "NPU"))] + args
    if spec.get("refs"):
        args.append("--refs")
    return kind, args


class Runner:
    def __init__(self, hub, root=ROOT, log_path=None, python=sys.executable, other_sorter=None):
        self.hub, self.root, self.python = hub, Path(root), python
        self.log_path = Path(log_path) if log_path else self.root / "docs" / "AGENT_LOG.md"
        self.lock = threading.Lock()
        self.proc, self.run = None, None          # launcher/sort.py process; current run record
        self.output = deque(maxlen=300)
        self.other_sorter = other_sorter or self._other_sorter

    # ---- checks --------------------------------------------------------------------------------
    @staticmethod
    def _other_sorter():
        return subprocess.run(["pgrep", "-f", "sort.py --mode"], capture_output=True).returncode == 0

    def _note(self, line):
        try:
            with self.log_path.open("a") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    # ---- API -----------------------------------------------------------------------------------
    def start(self, spec):
        if spec.get("estop_confirmed") is not True:
            raise PermissionError("confirm that a person is at the E-stop")
        target = _choice(spec, "target", "local", ("local", "station"))
        kind, args = build_args(spec)
        with self.lock:
            if self.run and not self.run.get("ended"):
                raise RuntimeError("a run started from this dashboard is still going; stop it first")
            if self.hub is not None and self.hub.run_active():
                raise RuntimeError("another run is sending telemetry right now")
            if self.other_sorter():
                raise RuntimeError("a sort.py loop already runs on this computer")
            if target == "local":
                cmd = [self.python, "-u", "sort.py", *args, "--dash-host", "127.0.0.1"]
            else:
                cmd = [self.python, "-u", "station_run.py", "start", "--", *args]
            self.output.clear()
            self.proc = subprocess.Popen(cmd, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True)
            self.run = {"kind": kind, "target": target, "args": args, "started": time.time(), "pid": self.proc.pid,
                        "ended": None, "rc": None, "seen_telemetry": False}
            who = identity(kind)
            self.run["identity"] = who
            self._note(f"\n{who}\nARM: taken from the dashboard {kind} button ({target}): sort.py {' '.join(args)}. "
                       f"Operator confirmed a person at the E-stop; sort.py checks teleop off and joints steady before moving.")
        threading.Thread(target=self._pump, args=(self.proc, self.run), daemon=True).start()
        return self.status()

    def stop(self):
        with self.lock:
            run, proc = self.run, self.proc
        if not run or run.get("ended"):
            return {"error": "nothing started from this dashboard is running", **self.status()}
        if run["target"] == "local":
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        else:
            r = subprocess.run([self.python, "station_run.py", "stop"], cwd=self.root, capture_output=True, text=True,
                               timeout=60)
            self.output.extend((r.stdout + r.stderr).strip().splitlines()[-5:])
            self._end(run, "stopped from the dashboard")
        return self.status()

    def status(self):
        with self.lock:
            run = dict(self.run) if self.run else None
        return {"run": run, "running": bool(run and not run.get("ended")), "output": list(self.output)[-40:],
                "telemetry_active": bool(self.hub and self.hub.run_active())}

    def options(self):
        return {"types": part_types(self.root), "bundles": bundles(self.root), "default_bundle": DEFAULT_BUNDLE}

    # ---- lifecycle -----------------------------------------------------------------------------
    def _end(self, run, why):
        with self.lock:
            if run.get("ended"):
                return
            self._note(f"{identity(run['kind'])}\nARM: released ({why}). Dashboard {run['kind']} run on {run['target']}.")
            run["why"] = why
            run["ended"] = time.time()

    def _pump(self, proc, run):
        for line in proc.stdout:
            self.output.append(line.rstrip())
        rc = proc.wait()
        run["rc"] = rc
        if run["target"] == "local":
            self._end(run, f"sort.py exited, rc {rc}")
            return
        if rc != 0:
            self._end(run, f"station launcher failed, rc {rc}")
            return
        # station: the launcher returns right away; the run lives until its telemetry goes quiet / IDLE
        t0 = time.time()
        while not run.get("ended"):
            active = self.hub.run_active() if self.hub else False
            run["seen_telemetry"] = run["seen_telemetry"] or active
            if run["seen_telemetry"] and not active:
                quiet_since = run.setdefault("quiet_since", time.time())
                if time.time() - quiet_since > 10:
                    self._end(run, "station run telemetry ended")
            else:
                run.pop("quiet_since", None)
            if not run["seen_telemetry"] and time.time() - t0 > 120 and not run.get("warning"):
                # NOT released: the run may be going on the station with telemetry lost. Stop still works.
                run["warning"] = "no telemetry from the station for 120 s; it may still be running. Use Stop, or check python station_run.py status"
                self.output.append(run["warning"])
            time.sleep(1)
