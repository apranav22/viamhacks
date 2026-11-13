"""Live dashboard for the pipeline. A separate process: the robot loop only sends UDP datagrams to it.

    python dashboard/server.py                      # UDP :8766 in, http://localhost:8765 out
    python dashboard/server.py --host 0.0.0.0       # on the station; open http://<station>:8765 from a laptop
    python dashboard/server.py --replay runs/<run>/dash   # replay a recorded run (pitch / debugging)

It reassembles frames, keeps the recent history in memory, streams events to browsers (SSE), and
records the run (events.jsonl + key frames) under runs/<run>/dash. Stdlib only.
"""

import argparse
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
KEEP_FRAMES = 400                          # ~10 MB of JPEGs
SAVE_FRAMES_FOR = {"look", "reference", "depth"}


class Hub:
    def __init__(self, record_root):
        self.lock = threading.Condition()
        self.events = deque(maxlen=6000)       # (seq, json_str, event)
        self.seq = 0
        self.frames = OrderedDict()            # fid -> (mime, bytes)
        self.partial = {}                      # fid -> [chunks]
        self.record_root = Path(record_root) if record_root else None
        self.rec_run, self.rec_fh = None, None
        self.last_packet = 0.0
        self.stats = {"packets": 0, "events": 0, "frames": 0, "incomplete": 0}

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
            self.event(ev)

    def _store_frame(self, fid, blob, mime=None):
        with self.lock:
            self.frames[fid] = (mime, blob)
            while len(self.frames) > KEEP_FRAMES:
                self.frames.popitem(last=False)
        self.stats["frames"] += 1

    def event(self, ev):
        fr = ev.get("frame")
        if fr:
            with self.lock:
                got = self.frames.get(fr["id"])
                if got:
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
        if not self.record_root or ev.get("_replay"):
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
        out, last_watch = [], None
        for item in evs[start:]:
            if item[2].get("k") == "watch":
                last_watch = item
            else:
                out.append(item)
        if last_watch:
            out.append(last_watch)
        return sorted(out, key=lambda x: x[0])

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
                with hub.lock:
                    got = hub.frames.get(fid)
                if not got:
                    return self._send(404, b"gone", "text/plain")
                mime, blob = got
                return self._send(200, blob, "application/octet-stream" if not mime or not mime.startswith("image/") else mime)
            if path == "/health":
                body = dict(hub.stats, last_packet_age=round(time.time() - hub.last_packet, 2) if hub.last_packet else None)
                return self._send(200, json.dumps(body).encode(), "application/json")
            if path == "/events":
                return self.sse()
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
                    watches = [b for b in batch if b[2].get("k") == "watch"]
                    for q, js, ev in batch:
                        if ev.get("k") == "watch" and watches and q != watches[-1][0]:
                            continue                 # slow browser: only the newest watch frame
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
    a = ap.parse_args()
    hub = Hub(a.record or None if not a.replay else None)
    if a.replay:
        threading.Thread(target=replay, args=(hub, a.replay, a.speed), daemon=True).start()
    else:
        threading.Thread(target=udp_loop, args=(hub, a.udp_host, a.udp_port), daemon=True).start()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(hub))
    srv.daemon_threads = True
    print(f"dashboard: http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}  "
          f"({'replaying ' + a.replay if a.replay else f'telemetry on udp :{a.udp_port}'})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
