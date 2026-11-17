"""Per-decision confidence for the judge log (decisions.jsonl).

The rubric asks for a confidence on every item line. Ours is a threshold margin, not a calibrated probability:
each view gives evidence e = score / threshold (anomaly) or tape_fraction / tape_limit (colour rule), where e >= 1
means "over the line". A reject is as confident as its strongest evidence is far above 1; a good is as confident as
its closest evidence is far below 1. 0.5 means "on the line" or "no usable evidence".
"""
import math

BASIS = "threshold margin: 0.5 + 0.5*tanh(3*|e-1|), e = score/threshold or tape/limit; not a calibrated probability"


def _from_margin(e):
    return round(0.5 + 0.5 * math.tanh(3.0 * abs(e - 1.0)), 3)


def view_evidence(name, s, tape_limit_top, tape_limit_web, use_anomaly=True):
    """Largest evidence ratio a view gives, or None when it has nothing usable."""
    out = []
    if use_anomaly and s.get("status") == "ok" and s.get("score") is not None and s.get("threshold"):
        out.append(float(s["score"]) / float(s["threshold"]))
    tape = s.get("tape")
    if tape is not None:
        out.append(float(tape) / (tape_limit_top if name == "top" else tape_limit_web))
    return max(out) if out else None


def decision_confidence(rec, tape_limit_top, tape_limit_web, decide="all"):
    """Confidence in [0.5, 1) for a good/reject line, None for lines with no decision (none, dropped, collect)."""
    decision, scores = rec.get("decision"), rec.get("scores") or {}
    if decision not in ("good", "reject") or not scores:
        return None
    anomaly_views = None if decide == "all" else {"top"}   # --decide top: webcam anomaly is evidence only
    ev = {n: view_evidence(n, s, tape_limit_top, tape_limit_web, anomaly_views is None or n in anomaly_views)
          for n, s in scores.items() if isinstance(s, dict)}
    ev = {n: e for n, e in ev.items() if e is not None}
    if not ev:
        return 0.5
    if decision == "reject":
        at = rec.get("decided_at_view")
        e = ev.get(at) if at in ev else max(ev.values())
        return _from_margin(e) if e >= 1.0 else 0.5   # rejected for missing results, not for evidence over the line
    e = max(ev.values())
    return _from_margin(e) if e < 1.0 else 0.5
