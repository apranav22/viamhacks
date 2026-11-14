"""Fire-and-forget telemetry for the dashboard, designed to cost the control loop microseconds.

The loop never renders, encodes, writes files for, or waits on the dashboard:
- Events are small JSON dicts sent as one non-blocking UDP datagram each.
- Frames are the camera's own JPEG bytes (no re-encoding), sent in <= 8 KB chunks (macOS caps a
  datagram at 9216 bytes) *before* the event that references them. Overlays travel as numbers
  (boxes, axes, grasp lines) and are drawn by the browser.
- If the dashboard is down or slow, the kernel drops datagrams; `sendto` never blocks.
- The cost of every emit is measured and reported (`telemetry` events), so the claim is checkable.

Wire format: b"E" + JSON  |  b"F" + !IHH (frame id, chunk index, chunk count) + bytes
"""

import itertools
import json
import socket
import struct
import time
from contextlib import contextmanager

CHUNK = 8000          # loopback only
# Over the network a datagram larger than the MTU (~1500 B) is IP-fragmented, and the station -> laptop path drops the
# fragments: 2026-11-14 run 20261114_084057 lost 63/65 frames (events, < 1500 B, all arrived). One fragment-free
# datagram per chunk off-host.
NET_CHUNK = 1200


class Telemetry:
    def __init__(self, host="127.0.0.1", port=8766, enabled=True, run_id=None, log_path=None,
                 log_kinds=("span", "move", "error", "recovery", "still")):
        self.addr = (host, port)
        self.chunk = CHUNK if host in ("127.0.0.1", "localhost", "::1") else NET_CHUNK
        # timing kept on disk (no frames): UDP to the dashboard is lost when nothing listens
        self.log = open(log_path, "a", buffering=1) if log_path else None
        self.log_kinds = set(log_kinds)
        self.enabled = enabled
        self.run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
        self.sock = None
        if enabled:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
            except OSError:
                pass
        self._seq = itertools.count(1)
        self._fid = itertools.count(1)
        self.n = 0
        self.ns = 0
        self.max_ns = 0
        self.dropped = 0
        self.bytes = 0

    def _send(self, pkt):
        try:
            self.sock.sendto(pkt, self.addr)
            self.bytes += len(pkt)
        except (BlockingIOError, InterruptedError, OSError):   # full buffer / nobody listening: drop
            self.dropped += 1

    def emit(self, kind, frame=None, mime="image/jpeg", **fields):
        """Send one event. `frame` = raw bytes (e.g. the camera's JPEG) attached to it."""
        if not self.enabled and not self.log:
            return
        t0 = time.perf_counter_ns()
        ev = {"k": kind, "t": time.time(), "s": next(self._seq), "run": self.run_id}
        ev.update(fields)
        if self.log and kind in self.log_kinds:
            self.log.write(json.dumps(ev, separators=(",", ":"), default=_jsonable) + "\n")
        if not self.enabled:
            return
        if frame:
            fid = next(self._fid) & 0xFFFFFFFF
            n = (len(frame) + self.chunk - 1) // self.chunk
            if n <= 0xFFFF:
                for i in range(n):
                    self._send(b"F" + struct.pack("!IHH", fid, i, n) + frame[i * self.chunk:(i + 1) * self.chunk])
                ev["frame"] = {"id": fid, "len": len(frame), "mime": mime}
        self._send(b"E" + json.dumps(ev, separators=(",", ":"), default=_jsonable).encode())
        dt = time.perf_counter_ns() - t0
        self.n += 1
        self.ns += dt
        self.max_ns = max(self.max_ns, dt)

    def state(self, name, **fields):
        self.emit("state", state=name, **fields)

    @contextmanager
    def span(self, name, **attrs):
        """Times a stage; one 'span' event at the end (start, duration, ok/error)."""
        t_wall, t0 = time.time(), time.perf_counter()
        err = None
        try:
            yield attrs                       # callers may add attrs inside the block
        except BaseException as e:
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            self.emit("span", name=name, t0=t_wall, ms=round((time.perf_counter() - t0) * 1000, 2), error=err, **attrs)

    def report(self):
        """Send (and return) the measured overhead of telemetry itself."""
        s = {"emits": self.n, "mean_us": round(self.ns / max(self.n, 1) / 1000, 1),
             "max_us": round(self.max_ns / 1000, 1), "dropped": self.dropped, "mb": round(self.bytes / 1e6, 2)}
        self.emit("telemetry", **s)
        return s


def _jsonable(o):
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
    return str(o)
