from vh.confidence import decision_confidence

LIM = dict(tape_limit_top=0.01, tape_limit_web=0.04)


def ok(score, thr, tape=None):
    return {"status": "ok", "score": score, "threshold": thr, "tape": tape}


def test_tape_reject_far_over_line_is_confident():
    rec = {"decision": "reject", "decided_at_view": "top", "scores": {"top": ok(16.6, 14.5, tape=0.048)}}
    assert decision_confidence(rec, **LIM) > 0.99


def test_anomaly_reject_just_over_line_is_near_half():
    rec = {"decision": "reject", "decided_at_view": "top", "scores": {"top": ok(10.2, 10.0, tape=0.0)}}
    assert 0.5 < decision_confidence(rec, **LIM) < 0.6


def test_good_far_below_line_is_confident_and_uses_closest_view():
    far = {"decision": "good", "scores": {"top": ok(4.0, 10.0, tape=0.0), "front": ok(5.0, 10.0, tape=0.0)}}
    close = {"decision": "good", "scores": {"top": ok(4.0, 10.0, tape=0.0), "front": ok(9.5, 10.0, tape=0.0)}}
    assert decision_confidence(far, **LIM) > 0.9
    assert decision_confidence(close, **LIM) < decision_confidence(far, **LIM)


def test_decide_top_ignores_webcam_anomaly_but_not_webcam_tape():
    rec = {"decision": "good", "scores": {"top": ok(3.0, 10.0, tape=0.0), "front": ok(20.0, 10.0, tape=0.0)}}
    assert decision_confidence(rec, decide="top", **LIM) > 0.9
    assert decision_confidence(rec, decide="all", **LIM) == 0.5


def test_no_decision_and_missing_results():
    assert decision_confidence({"decision": "none"}, **LIM) is None
    assert decision_confidence({"decision": "dropped", "scores": {"top": ok(1, 2)}}, **LIM) is None
    rec = {"decision": "reject", "decided_at_view": "fusion", "scores": {"top": {"status": "missing", "tape": None}}}
    assert decision_confidence(rec, **LIM) == 0.5
