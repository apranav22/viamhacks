"""Following items in world xy (or pixels) across camera looks. Camera-agnostic: feed it detections
as tuples whose first two values are the position."""

import math

import numpy as np
from scipy.optimize import linear_sum_assignment


class Tracker:
    """Follows one item in world xy. Alpha-beta filter; `still_for` is how long it has stayed within
    still_tol_mm of where it settled. `last_det` is the detection it last matched."""

    def __init__(self, x, y, t, gate_mm=40.0, still_tol_mm=4.0, alpha=0.6, beta=0.3):
        self.x, self.y, self.vx, self.vy, self.t = x, y, 0.0, 0.0, t
        self.gate, self.still_tol, self.alpha, self.beta = gate_mm, still_tol_mm, alpha, beta
        self.last_seen = t
        self.last_det = None
        self.anchor, self.anchor_t = (x, y), t

    def predict(self, t) -> tuple:
        dt = t - self.t
        return self.x + self.vx * dt, self.y + self.vy * dt

    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def update(self, dets, t) -> bool:
        """dets: [(x, y, ...)]. False if nothing is close enough to be this item."""
        px, py = self.predict(t)
        # the longer it's unseen, the further it may have gone (a hand moves ~200 mm/s)
        gate = self.gate + 200 * min(t - self.last_seen, 1.0)
        near = [d for d in dets if math.dist((d[0], d[1]), (px, py)) < gate]
        if not near:
            return False
        self.last_det = min(near, key=lambda d: math.dist((d[0], d[1]), (px, py)))
        dx, dy = self.last_det[:2]
        dt = max(t - self.t, 1e-3)
        rx, ry = dx - px, dy - py
        self.x, self.y = px + self.alpha * rx, py + self.alpha * ry
        self.vx += self.beta * rx / dt
        self.vy += self.beta * ry / dt
        self.t = self.last_seen = t
        if math.dist((self.x, self.y), self.anchor) > self.still_tol:
            self.anchor, self.anchor_t = (self.x, self.y), t
        return True

    def still_for(self, t) -> float:
        return t - self.anchor_t if t - self.last_seen < 0.5 else 0.0

    def lost(self, t, timeout=2.0) -> bool:
        return t - self.last_seen > timeout


class MultiTracker:
    """Gives every item an id that stays with it across frames, also while it is moved.
    Each frame: predict every track, match detections to tracks (optimal assignment within a gate),
    update the matched ones, start a tentative track for each unmatched detection, drop tracks
    unseen for lost_s. A track is confirmed after `confirm` hits, so one-frame noise never gets an id."""

    def __init__(self, gate=40.0, still_tol=4.0, lost_s=2.0, confirm=3):
        self.gate, self.still_tol, self.lost_s, self.confirm = gate, still_tol, lost_s, confirm
        self.tracks = {}  # id -> Tracker (with .hits and .det)
        self.next_id = 1

    def update(self, dets, t) -> dict:
        ids = list(self.tracks)
        if ids and dets:
            cost = np.full((len(ids), len(dets)), 1e9)
            for i, tid in enumerate(ids):
                tr = self.tracks[tid]
                px, py = tr.predict(t)
                gate = tr.gate + 200 * min(t - tr.last_seen, 1.0)
                for j, d in enumerate(dets):
                    dist = math.dist((d[0], d[1]), (px, py))
                    if dist < gate:
                        cost[i, j] = dist
            rows, cols = linear_sum_assignment(cost)
            pairs = [(ids[r], c) for r, c in zip(rows, cols) if cost[r, c] < 1e9]
        else:
            pairs = []
        matched = set()
        for tid, j in pairs:
            tr = self.tracks[tid]
            tr.update([dets[j]], t)
            tr.hits += 1
            matched.add(j)
        for j, d in enumerate(dets):
            if j not in matched:
                tr = Tracker(d[0], d[1], t, gate_mm=self.gate, still_tol_mm=self.still_tol)
                tr.hits, tr.last_det = 1, d
                self.tracks[self.next_id] = tr
                self.next_id += 1
        for tid in [k for k, tr in self.tracks.items() if tr.lost(t, self.lost_s)]:
            del self.tracks[tid]
        return self.confirmed()

    def confirmed(self) -> dict:
        return {k: tr for k, tr in self.tracks.items() if tr.hits >= self.confirm}
