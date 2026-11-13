"""Dashboard telemetry for Pranav's motion_probe.py / pipeline.py, via the same fire-and-forget UDP
as vh/telemetry.py (tens of µs per event, nothing blocks if the dashboard is down).

motion_probe.Probe calls: start() once, before_step()/after_step() around every step, scan() after a
scan, end() at the end. Everything is wrapped so a telemetry bug can never break a motion run.
"""

import math
import time

import numpy as np

from . import config as C
from .telemetry import Telemetry

# step name (prefix match, first wins) -> phase shown in the dashboard's cycle chain
PHASES = [("survey", "SURVEY"), ("scan", "SCAN"), ("re-look", "RELOOK"), ("hover correction", "RELOOK"),
          ("re-aim", "RELOOK"), ("hover", "HOVER"), ("wait until", "RELOOK"), ("align", "RELOOK"),
          ("open", "DESCEND"), ("descend", "DESCEND"), ("grab", "GRAB"), ("lift", "LIFT"),
          ("to present", "PRESENT"), ("view", "PRESENT"), ("point down", "PRESENT"),
          ("over destination", "PLACE"), ("lower", "PLACE"), ("release", "PLACE"), ("retreat", "PLACE"),
          ("home", "HOME")]
STATES = ["SURVEY", "SCAN", "HOVER", "RELOOK", "DESCEND", "GRAB", "LIFT", "PRESENT", "PLACE", "HOME"]


def phase_of(name):
    n = name.lower()
    return next((p for k, p in PHASES if n.startswith(k)), name.upper()[:10])


def _safe(fn):
    def w(self, *a, **k):
        try:
            return fn(self, *a, **k)
        except Exception as e:                       # telemetry must never break a motion run
            try:
                self.tel.emit("error", msg=f"telemetry {fn.__name__}: {type(e).__name__}: {e}")
            except Exception:
                pass
    return w


class ProbeTel:
    def __init__(self, run_id=None):
        self.tel = Telemetry(C.TELEMETRY_HOST, C.TELEMETRY_PORT, enabled=C.TELEMETRY, run_id=run_id)
        self.item = 1
        self.t_scan0 = None
        self.latency_sent = False
        self._t0 = {}

    @_safe
    def start(self, live, args):
        self.tel.emit("run", cmd="motion_probe", live=live, step=bool(args.get("step")), release=args.get("dest"),
                      states=STATES, config={"MASK_RECTS": []})

    @_safe
    def before_step(self, n, name):
        ph = phase_of(name)
        self._t0[n] = (time.time(), time.perf_counter())
        if ph == "SCAN" and self.t_scan0 is None:
            self.t_scan0 = time.time()
        if ph == "HOVER" and not self.latency_sent and self.t_scan0:
            # first motion command after the item was first looked for (scan start); dry runs too
            t = time.time()
            ms = round((t - self.t_scan0) * 1000)
            self.tel.emit("latency", n=self.item, t_appeared=self.t_scan0, t_stable=self.t_scan0, t_cmd=t, t_moving=t,
                          ms_to_stable=0, ms_to_cmd=ms, ms_to_motion=ms, basis="scan start -> hover command")
            self.latency_sent = True
        self.tel.state(ph, item=self.item, step=name)

    @_safe
    def after_step(self, n, name, ok, ms, err, snap, frames):
        t_wall, _ = self._t0.pop(n, (time.time() - ms / 1000, 0))
        self.tel.emit("span", name=name, t0=t_wall, ms=round(ms, 1), error=err, item=self.item, phase=phase_of(name))
        if snap and isinstance(snap.get("gripper_pos"), (int, float)):
            self.tel.emit("gripper", pos=snap["gripper_pos"], holding=snap.get("holding"))
            if phase_of(name) in ("GRAB", "LIFT"):
                self.tel.emit("grasp_result", n=self.item, pos=snap["gripper_pos"], holding=snap.get("holding"),
                              ok=bool(snap["gripper_pos"] > 15), grabbed=None, expected_pos=None, after=name)
        tcp = (snap or {}).get("tcp")
        if isinstance(tcp, dict):
            self.tel.emit("move", label=name, component="gripper", dry_run=False,
                          target={k: tcp[k] for k in ("x", "y", "z", "o_x", "o_y", "o_z", "theta")})
        for cam, data in (frames or {}).items():
            self.tel.emit("snap", frame=data, cam=cam, step=name, n=n)

    @_safe
    def scan(self, s, item, label, theta=None, grasp_z=None, jaw=None, g=None, table_z=None):
        """A scan result as a dashboard 'look': frame + every item's box, the chosen item's axis and
        the jaw line the commanded theta implies (from JawFrame's model)."""
        rot, t, k = getattr(s, "rot", None), getattr(s, "t", None), getattr(s, "k", None)
        table_z = s.table_z if table_z is None else table_z

        def px(pts):
            if rot is None:
                return None
            c = (np.atleast_2d(np.asarray(pts, float)) - t) @ rot
            return [[round(float(k.focal_x_px * x / z + k.center_x_px), 1),
                     round(float(k.focal_y_px * y / z + k.center_y_px), 1)] for x, y, z in c]

        ev = {"n": self.item, "label": label, "table_z": round(table_z, 1),
              "others": [{"bbox": list(o.bbox), "xy": [round(o.x), round(o.y)]} for o in s.items if o is not item]}
        if item is None:
            self.tel.emit("look", frame=getattr(s, "jpeg", None), item=None, **ev)
            return
        x0, y0, x1, y1 = item.bbox
        r = math.radians(item.yaw_deg)
        ends = px([[item.x - 25 * math.cos(r), item.y - 25 * math.sin(r), item.top_z],
                   [item.x + 25 * math.cos(r), item.y + 25 * math.sin(r), item.top_z]])
        c = px([[item.x, item.y, item.top_z]])
        ov = {"bbox": [x0, y0, x1, y1], "c": c[0] if c else [(x0 + x1) / 2, (y0 + y1) / 2],
              "axis": (ends[0] + ends[1]) if ends else [x0, y0, x1, y1], "area": item.pixels, "border": False,
              "xy": [round(item.x, 1), round(item.y, 1)]}
        height = item.top_z - table_z
        m = {"x": round(item.x, 1), "y": round(item.y, 1), "height": round(height, 1), "yaw_long": round(item.yaw_deg, 1),
             "length": None, "width": None, "depth_frac": None, "top_z": round(item.top_z, 1)}
        grasp, jaw_px = None, None
        if theta is not None and jaw is not None:
            close = jaw.close0 + jaw.s_close * jaw.s_theta * (theta - jaw.theta0)    # inverse of JawFrame.theta_for
            close = (close + 90) % 180 - 90
            tips = (grasp_z - g["tcp_to_tip_mm"]) if (grasp_z is not None and g) else item.top_z
            grasp = {"shape": "item", "x": round(item.x, 1), "y": round(item.y, 1), "tip_z": round(tips, 1),
                     "jaw_heading": round(close, 1), "expected_width": None, "ok": True, "theta": round(theta, 1),
                     "intended": round(((item.yaw_deg + (g or {}).get("jaw_offset_deg", 90)) + 90) % 180 - 90, 1)}
            cr = math.radians(close)
            jaw_px = px([[item.x - 40 * math.cos(cr), item.y - 40 * math.sin(cr), item.top_z],
                         [item.x + 40 * math.cos(cr), item.y + 40 * math.sin(cr), item.top_z]])
        self.tel.emit("look", frame=getattr(s, "jpeg", None), item=ov, shape="item",
                      shape_note=f"{label}: height {height:.1f} mm, yaw {item.yaw_deg:.0f}°, {len(s.items)} in view",
                      m=m, grasp=grasp, jaw_px=jaw_px, center_px=c[0] if c else None, **ev)

    @_safe
    def note(self, **kw):
        self.tel.emit("note", **{k: v for k, v in kw.items() if isinstance(v, (int, float, str, bool, type(None), list))})

    @_safe
    def end(self, n_steps, failures):
        self.tel.emit("cycle", item=self.item, result=f"{n_steps} steps, {failures} failed", shape="item",
                      latency_ms=None, recoveries=0, events=[], t_first_motion=None, decision="–", dry_run=None)
        self.tel.report()
        self.tel.state("IDLE")
