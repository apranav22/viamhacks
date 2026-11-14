"""Offline tests (no robot): python tests/test_motion.py"""

import asyncio
import json
import math
import socket
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vh.geometry import jaw_heading_for_theta, ov_to_R, theta_for_jaw_heading, Transform  # noqa: E402
from vh.telemetry import Telemetry  # noqa: E402

IMG = ROOT / "site" / "img" / "home_color.jpg"


def test_orientation_convention():
    # values read from the station: gripper th 177.4 -> x-axis heading 2.6°, cam th 87.4 -> y-axis heading 2.6°
    R = ov_to_R(0, 0, -1, 177.4)
    assert abs(math.degrees(math.atan2(R[1, 0], R[0, 0])) - 2.6) < 1e-6
    R = ov_to_R(0, 0, -1, 87.4)
    assert abs(math.degrees(math.atan2(R[1, 1], R[0, 1])) - 2.6) < 1e-6
    for h in (-170, -45, 0, 30, 89, 135):
        for axis in ("x", "y"):
            th = theta_for_jaw_heading(h, axis, near_theta=10)
            got = jaw_heading_for_theta(th, axis)
            assert abs(((got - h) + 90) % 180 - 90) < 1e-6, (h, axis, th, got)
            assert abs(th - 10) <= 90 + 1e-6            # never more than a quarter turn of the wrist


def test_ray_plane():
    T = Transform(ov_to_R(0, 0, -1, -90), np.array([368.0, 23.0, 636.0]))
    p = T.ray_to_plane(np.array([0.0, 0.0, 1.0]), -4.0)
    assert np.allclose(p, [368, 23, -4])


def test_telemetry_cost_and_delivery():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(1)
    tel = Telemetry(port=rx.getsockname()[1])
    jpg = IMG.read_bytes()
    tel.emit("watch", frame=jpg, item=None)
    chunks, ev = [], None
    while ev is None:
        d, _ = rx.recvfrom(65535)
        if d[:1] == b"F":
            chunks.append(d[9:])
        else:
            ev = json.loads(d[1:])
    assert b"".join(chunks) == jpg and ev["frame"]["len"] == len(jpg)
    t0 = time.perf_counter()
    for _ in range(500):
        tel.emit("state", state="WATCH")
    assert (time.perf_counter() - t0) / 500 < 300e-6     # far below a millisecond per event
    off = Telemetry(port=9)                              # nobody listening: never raises, never blocks
    off.emit("watch", frame=jpg)


def load_tests(loader, tests, pattern):
    """unittest (python3 -m unittest discover tests) runs the plain test_ functions too; no pytest in .venv."""
    import unittest
    return unittest.TestSuite(unittest.FunctionTestCase(fn) for name, fn in sorted(globals().items())
                              if name.startswith("test_") and callable(fn))


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            t = time.perf_counter()
            try:
                fn()
                print(f"ok    {name}  ({1000 * (time.perf_counter() - t):.0f} ms)")
            except Exception as e:
                fails += 1
                print(f"FAIL  {name}: {type(e).__name__}: {e}")
    sys.exit(1 if fails else 0)
