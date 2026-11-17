"""Offline check of Sorter.oblique_looks / score_oblique / fusion with stubbed robot calls (no connection)."""
import asyncio, sys, types, io
from pathlib import Path
sys.path.insert(0, '.')
import numpy as np
from PIL import Image
import sort as S
from vh.anomaly import Score
from vh.kinematics import load_obstacles

class FakeTel:
    def __init__(self): self.ev = []
    def emit(self, k, **kw): self.ev.append((k, kw.get("view"), kw.get("what") or kw.get("msg")))

class Stub(S.Sorter):
    def __init__(self, blocked=()):
        self.args = types.SimpleNamespace(mode="sort", type="hex_bolt_partial", background="cardboard", decide="all")
        self.obs = load_obstacles(table_z=6.5); self.tel = FakeTel(); self.meta = {}; self.n = 1
        self.idir = Path("/private/tmp/claude-501/-Users-alirizwan-Projects-Misc-viamhacks/ca4c01d6-01aa-4cb3-b823-5133698a584f/scratchpad/stub"); self.idir.mkdir(exist_ok=True)
        self.q = None; self.moves = []; self.blocked = blocked; self.anomaly = None
        self.cam = types.SimpleNamespace(get_properties=self._props); self.m = None
        self.oblique_scores, self.early = {}, None
    async def _props(self):
        return types.SimpleNamespace(intrinsic_parameters=types.SimpleNamespace(focal_x_px=908.2, focal_y_px=907.3, center_x_px=666.3, center_y_px=371.1))
    async def jmove(self, q, label, holding):
        if any(b in label for b in self.blocked) and "approach" not in label and "retreat" not in label and "back" not in label:
            raise RuntimeError("blocked (stub)")
        self.moves.append(label); self.q = list(q)
    async def wrist_jpeg(self):
        b = io.BytesIO(); Image.fromarray(np.full((720, 1280, 3), 120, np.uint8)).save(b, "JPEG"); return b.getvalue()
    def emit_crop(self, *a): pass

async def fake_cam_to_world(m): return np.array([[0,-1,0],[-1,0,0],[0,0,-1.0]]), np.array([300.0, 330.0, 200.0])
S.cam_to_world = fake_cam_to_world

async def main():
    for blocked in ((), ("oblique-45",)):
        s = Stub(blocked); s.part_ends = [(270.0, 330.0), (330.0, 330.0)]
        look = S.ik(np.array([300., 330., 250.]), seed=S.WATCH_J)[0]; s.q = list(look)
        await s.oblique_looks((300.0, 330.0, 3000, 0.0, None), look)
        print("blocked", blocked, "->", s.moves, "skipped", s.meta.get("skipped"), "scores", {k: v["status"] for k, v in s.oblique_scores.items()})
    # fusion rule: missing models are evidence only
    from vh.anomaly import reject_reason
    scores = {"top": {"status": "ok", "anomalous": False, "score": 1, "threshold": 2}, "oblique+45": {"status": "missing"}, "under": {"status": "missing"}}
    required = ["top"] + [v for v in ["oblique+45", "under"] if scores[v].get("status") != "missing"]
    print("fusion ->", reject_reason(scores, required) or "good")
asyncio.run(main())
