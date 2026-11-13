"""Live dashboard for the pipeline. A separate process: the robot loop only sends UDP datagrams to it.

    python dashboard/server.py                      # UDP :8766 in, http://localhost:8765 out
    python dashboard/server.py --host 0.0.0.0       # on the station; open http://<station>:8765 from a laptop
    python dashboard/server.py --replay runs/<run>/dash   # replay a recorded run (pitch / debugging)
    python dashboard/server.py --no-preview         # don't connect to the robot at all

Idle preview: when no run is active the server itself polls both cameras (~4 fps) and the arm/gripper
state (~2 Hz), so the feeds are live between runs. It pauses the moment a run sends telemetry and
stays paused until the run ends (or goes silent for 3 s), so it never competes with the run's camera calls.

It reassembles frames, keeps the recent history in memory, streams events to browsers (SSE), and
records the run (events.jsonl + key frames) under runs/<run>/dash. Stdlib only.
"""

import argparse
import os
import sys
import asyncio
import itertools
import json
import socket
import struct
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
KEEP_FRAMES = 400                          # ~10 MB of JPEGs
PREVIEW_BASE = 1 << 31                     # preview frame ids start here; kept apart so they never evict run frames
KEEP_PREVIEW = 24
SAVE_FRAMES_FOR = {"look", "reference", "depth", "view"}


class Hub:
    def __init__(self, record_root):
        self.lock = threading.Condition()
        self.events = deque(maxlen=20000)      # (seq, json_str, event)
        self.seq = 0
        self.frames = OrderedDict()            # fid -> (mime, bytes)
        self.partial = {}                      # fid -> [chunks]
        self.pframes = OrderedDict()           # idle-preview frames, separate small store
        self.record_root = Path(record_root) if record_root else None
        self.rec_run, self.rec_fh = None, None
        self.last_packet = 0.0
        self.stats = {"packets": 0, "events": 0, "frames": 0, "incomplete": 0}
        self.run_state, self.run_last = "IDLE", 0.0
        self.latest = {}                       # newest idle-preview frame/detection per camera + arm state

    def run_active(self):
        """A run is active while it keeps sending telemetry and hasn't said IDLE."""
        return self.run_state != "IDLE" and time.time() - self.run_last < 3.0

    # --- ingest -----------------------------------------------------------------------------
    def packet(self, data):
        self.last_packet = time.time()
        self.stats["packets"] += 1
        if data[:1] == b"F":
            fid, i, n = struct.unpack("!IHH", data[1:9])
            parts = self.partial.setdefault(fid, [None] * n)
            if i < n:
                parts[i] = data[9:]
            if all(p is not None for p in parts):
                self.partial.pop(fid)
                self._store_frame(fid, b"".join(parts))
            if len(self.partial) > 64:           # chunks lost in transit: forget the oldest
                self.partial.pop(next(iter(self.partial)))
                self.stats["incomplete"] += 1
        elif data[:1] == b"E":
            try:
                ev = json.loads(data[1:])
            except ValueError:
                return
            self.run_last = time.time()
            if ev.get("k") == "state":
                self.run_state = ev.get("state", "IDLE")
            elif ev.get("k") == "run":
                self.run_state = "RUN"
            self.event(ev)

    def get_frame(self, fid):
        with self.lock:
            return (self.pframes if fid >= PREVIEW_BASE else self.frames).get(fid)

    def _store_frame(self, fid, blob, mime=None):
        if fid >= PREVIEW_BASE:
            with self.lock:
                self.pframes[fid] = (mime, blob)
                while len(self.pframes) > KEEP_PREVIEW:
                    self.pframes.popitem(last=False)
            return
        with self.lock:
            self.frames[fid] = (mime, blob)
            while len(self.frames) > KEEP_FRAMES:
                self.frames.popitem(last=False)
        self.stats["frames"] += 1

    def event(self, ev):
        fr = ev.get("frame")
        if fr:
            got = self.get_frame(fr["id"])
            if got and fr["id"] < PREVIEW_BASE:
                with self.lock:
                    self.frames[fr["id"]] = (fr.get("mime"), got[1])
            fr["ok"] = bool(got)
        self._record(ev)
        with self.lock:
            self.seq += 1
            ev["_q"] = self.seq
            self.events.append((self.seq, json.dumps(ev, separators=(",", ":")), ev))
            self.lock.notify_all()
        self.stats["events"] += 1

    def _record(self, ev):
        if not self.record_root or ev.get("_replay") or ev.get("k") in ("preview", "arm_state", "preview_status"):
            return
        run = ev.get("run")
        if run and run != self.rec_run:
            if self.rec_fh:
                self.rec_fh.close()
            d = self.record_root / run / "dash"
            (d / "frames").mkdir(parents=True, exist_ok=True)
            self.rec_run, self.rec_fh, self.rec_dir = run, (d / "events.jsonl").open("a", buffering=1), d
        if not self.rec_fh:
            return
        fr = ev.get("frame")
        if fr and fr.get("ok") and (ev["k"] in SAVE_FRAMES_FOR or (ev["k"] == "watch" and ev.get("placed"))):
            mime, blob = self.frames[fr["id"]]
            (self.rec_dir / "frames" / f"{fr['id']}.bin").write_bytes(blob)
        self.rec_fh.write(json.dumps(ev, separators=(",", ":")) + "\n")

    # --- read side --------------------------------------------------------------------------
    def backlog(self):
        """Events a newly connected browser needs: the current run, minus all but the latest watch frame."""
        with self.lock:
            evs = list(self.events)
        start = 0
        for i in range(len(evs) - 1, -1, -1):
            if evs[i][2].get("k") == "run":
                start = i
                break
        out, latest = [], {}
        for item in evs[start:]:
            k = item[2].get("k")
            if k == "watch":
                latest["watch"] = item
            elif k == "preview":
                latest["preview:" + item[2].get("cam", "")] = item
            elif k in ("arm_state", "preview_status"):
                latest[k] = item
            else:
                out.append(item)
        for item in evs[:start]:                      # previews from before the run started still matter
            k = item[2].get("k")
            if k == "preview":
                latest.setdefault("preview:" + item[2].get("cam", ""), item)
        return sorted(out + list(latest.values()), key=lambda x: x[0])

    def wait(self, after, timeout=15.0):
        with self.lock:
            if not self.events or self.events[-1][0] <= after:
                self.lock.wait(timeout)
            return [e for e in self.events if e[0] > after]


def udp_loop(hub, host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    s.bind((host, port))
    while True:
        data, _ = s.recvfrom(65535)
        hub.packet(data)


def replay(hub, folder, speed):
    folder = Path(folder)
    evs = [json.loads(l) for l in (folder / "events.jsonl").read_text().splitlines() if l.strip()]
    while True:
        t_prev = None
        for ev in evs:
            if t_prev is not None:
                time.sleep(max(0.0, min((ev["t"] - t_prev) / speed, 2.0)))
            t_prev = ev["t"]
            fr = ev.get("frame")
            if fr:
                f = folder / "frames" / f"{fr['id']}.bin"
                if f.exists():
                    hub._store_frame(fr["id"], f.read_bytes(), fr.get("mime"))
            ev["_replay"] = True
            ev.pop("_q", None)
            hub.event(ev)
        time.sleep(3)


PREVIEW_IDS = itertools.count(PREVIEW_BASE)          # never collides with the run's frame ids


def load_creds(key_file):
    """api-key.json, else VIAM_ADDRESS / VIAM_API_KEY / VIAM_API_KEY_ID from the environment or .env."""
    if Path(key_file).exists():
        return json.loads(Path(key_file).read_text())
    env = dict(os.environ)
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return {"address": env["VIAM_ADDRESS"], "api_key": env["VIAM_API_KEY"], "api_key_id": env["VIAM_API_KEY_ID"]}


async def preview_loop(hub, key_file, cams, fps):
    """Idle preview: poll cameras + arm/gripper state while no run is active, and run the cheap live
    detectors on the frames (vh/live_detect.py) in this process. Read-only on the robot."""
    import viam.components.arm  # noqa: F401
    import viam.components.camera  # noqa: F401
    import viam.components.gripper  # noqa: F401
    from viam.components.arm import Arm
    from viam.components.camera import Camera
    from viam.components.gripper import Gripper
    from viam.proto.common import Pose, PoseInFrame
    from viam.robot.client import RobotClient
    from vh import live_detect
    from vh.geometry import Intrinsics, frame_to_world

    def status(state, **kw):
        hub.event({"k": "preview_status", "t": time.time(), "state": state, **kw})

    while True:
        m = None
        try:
            creds = load_creds(key_file)
            m = await RobotClient.at_address(creds["address"], RobotClient.Options.with_api_key(
                api_key=creds["api_key"], api_key_id=creds["api_key_id"]))
            arm, grip = Arm.from_robot(m, "arm"), Gripper.from_robot(m, "gripper")
            handles = {c: Camera.from_robot(m, c) for c in cams}
            intr = await Intrinsics.from_camera(handles["cam"]) if "cam" in handles else None
            status("live", fps=fps)
            tick, paused = 0, False
            T, T_tcp, T_time = None, None, 0.0
            while True:
                if hub.run_active():
                    if not paused:
                        status("paused", reason="run active")
                        paused = True
                    await asyncio.sleep(0.25)
                    continue
                if paused:
                    status("live", fps=fps)
                    paused = False
                t0 = time.perf_counter()
                for name, cam in handles.items():
                    if hub.run_active():                # a run started mid-poll: yield the cameras at once
                        break
                    tc = time.perf_counter()
                    imgs, _ = await cam.get_images(filter_source_names=["color"] if name == "cam" else None)
                    img = next((i for i in imgs if "jpeg" in i.mime_type), imgs[0])
                    rpc = round(1000 * (time.perf_counter() - tc))
                    td = time.perf_counter()
                    try:
                        if name == "cam":
                            det = await asyncio.to_thread(live_detect.wrist, img.data, T, intr)
                        elif name == "overview-cam":
                            det = await asyncio.to_thread(live_detect.overhead, img.data)
                        else:
                            det = None
                    except Exception as e:
                        det = {"error": f"{type(e).__name__}: {e}"[:160]}
                    det_ms = round(1000 * (time.perf_counter() - td), 1)
                    fid = next(PREVIEW_IDS)
                    hub._store_frame(fid, img.data, img.mime_type)
                    hub.latest[name] = (img.data, det)
                    hub.event({"k": "preview", "t": time.time(), "cam": name, "rpc_ms": rpc, "det_ms": det_ms, "det": det,
                               "frame": {"id": fid, "len": len(img.data), "mime": img.mime_type, "ok": True}})
                if tick % 2 == 0:
                    tcp, joints, gpos, holding = await asyncio.gather(
                        m.transform_pose(PoseInFrame(reference_frame="gripper", pose=Pose(o_z=1)), "world"),
                        arm.get_joint_positions(), grip.do_command({"get": True}), grip.is_holding_something())
                    p = tcp.pose
                    ev = {"k": "arm_state", "t": time.time(),
                          "tcp": [round(p.x, 1), round(p.y, 1), round(p.z, 1), round(p.o_x, 3), round(p.o_y, 3), round(p.o_z, 3), round(p.theta, 1)],
                          "joints": [round(v, 1) for v in joints.values], "pos": gpos.get("pos"),
                          "holding": holding.is_holding_something}
                    hub.latest["arm_state"] = ev
                    hub.event(dict(ev))
                    # cam -> world for the wrist detections: refresh when the arm moved or every 5 s
                    now_tcp = ev["tcp"]
                    if intr and (T_tcp is None or max(abs(a - b) for a, b in zip(now_tcp, T_tcp)) > 0.5
                                 or time.time() - T_time > 5):
                        T, _ = await frame_to_world(m, "cam")
                        T_tcp, T_time = now_tcp, time.time()
                tick += 1
                await asyncio.sleep(max(0.0, 1.0 / fps - (time.perf_counter() - t0)))
        except Exception as e:
            status("error", error=f"{type(e).__name__}: {e}"[:200])
            try:
                if m:
                    await m.close()
            except Exception:
                pass
            await asyncio.sleep(5)


def save_candidate(hub, note=""):
    """Snapshot the current arm pose + overhead frame + its metrics as a secondary-capture candidate."""
    arm = hub.latest.get("arm_state")
    ov = hub.latest.get("overview-cam")
    if not arm or not ov:
        return {"error": "no live arm state / overhead frame yet (is the preview running and idle?)"}
    d = ROOT / "runs" / "present_candidates"
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    (d / f"{stamp}-overhead.jpg").write_bytes(ov[0])
    if hub.latest.get("cam"):
        (d / f"{stamp}-wrist.jpg").write_bytes(hub.latest["cam"][0])
    rec = {"id": stamp, "t": time.time(), "note": note, "tcp": arm["tcp"], "joints_deg": arm["joints"],
           "gripper_pos": arm["pos"], "holding": arm["holding"], "overhead": ov[1]}
    with (d / "candidates.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    hub.event({"k": "candidate", **rec})
    return rec


def list_candidates():
    f = ROOT / "runs" / "present_candidates" / "candidates.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []


def make_handler(hub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/frame/"):
                try:
                    fid = int(path.rsplit("/", 1)[1])
                except ValueError:
                    return self._send(400, b"bad id", "text/plain")
                got = hub.get_frame(fid)
                if not got:
                    return self._send(404, b"gone", "text/plain")
                mime, blob = got
                return self._send(200, blob, "application/octet-stream" if not mime or not mime.startswith("image/") else mime)
            if path == "/candidates":
                return self._send(200, json.dumps(list_candidates()).encode(), "application/json")
            if path.startswith("/cand/"):
                name = path.rsplit("/", 1)[1]
                f = ROOT / "runs" / "present_candidates" / name
                if not name.replace("-", "").replace(".", "").isalnum() or not f.exists():
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, f.read_bytes(), "image/jpeg")
            if path == "/health":
                body = dict(hub.stats, last_packet_age=round(time.time() - hub.last_packet, 2) if hub.last_packet else None)
                return self._send(200, json.dumps(body).encode(), "application/json")
            if path == "/events":
                return self.sse()
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path.split("?")[0] == "/mark":
                n = int(self.headers.get("Content-Length") or 0)
                note = ""
                if n:
                    try:
                        note = str(json.loads(self.rfile.read(n)).get("note", ""))[:200]
                    except ValueError:
                        pass
                rec = save_candidate(hub, note)
                return self._send(200 if "error" not in rec else 409, json.dumps(rec).encode(), "application/json")
            return self._send(404, b"not found", "text/plain")

        def sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                last = 0
                for q, js, _ in hub.backlog():
                    self.wfile.write(f"data: {js}\n\n".encode())
                    last = q
                self.wfile.write(b"data: {\"k\":\"backlog_done\"}\n\n")
                self.wfile.flush()
                while True:
                    batch = hub.wait(last)
                    if not batch:
                        age = round(time.time() - hub.last_packet, 1) if hub.last_packet else -1
                        self.wfile.write(f"data: {{\"k\":\"ping\",\"age\":{age}}}\n\n".encode())
                    newest = {}
                    for q, _, ev in batch:            # slow browser: only the newest frame per feed
                        if ev.get("k") in ("watch", "preview", "arm_state"):
                            newest[(ev["k"], ev.get("cam"))] = q
                    for q, js, ev in batch:
                        if ev.get("k") in ("watch", "preview", "arm_state") and newest[(ev["k"], ev.get("cam"))] != q:
                            continue
                        self.wfile.write(f"data: {js}\n\n".encode())
                    if batch:
                        last = batch[-1][0]
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="HTTP bind address (0.0.0.0 to view from another machine)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--udp-host", default="0.0.0.0")
    ap.add_argument("--udp-port", type=int, default=8766)
    ap.add_argument("--record", default=str(ROOT / "runs"), help="'' to disable recording")
    ap.add_argument("--replay", default=None, help="a runs/<run>/dash folder to replay")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--no-preview", action="store_true", help="never connect to the robot (telemetry only)")
    ap.add_argument("--preview-fps", type=float, default=4.0)
    ap.add_argument("--preview-cams", default="cam,overview-cam")
    ap.add_argument("--key", default=str(ROOT / "api-key.json"))
    a = ap.parse_args()
    hub = Hub(a.record or None if not a.replay else None)
    if a.replay:
        threading.Thread(target=replay, args=(hub, a.replay, a.speed), daemon=True).start()
    else:
        threading.Thread(target=udp_loop, args=(hub, a.udp_host, a.udp_port), daemon=True).start()
        if not a.no_preview:
            threading.Thread(target=lambda: asyncio.run(preview_loop(hub, a.key, a.preview_cams.split(","), a.preview_fps)),
                             daemon=True).start()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(hub))
    srv.daemon_threads = True
    print(f"dashboard: http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}  "
          f"({'replaying ' + a.replay if a.replay else f'telemetry on udp :{a.udp_port}'})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
