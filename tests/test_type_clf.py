import numpy as np
import pytest

from vh.type_clf import head_probs

HEAD = {"classes": ["a", "b", "c"], "scaler_mean": [0.0, 0.0], "scaler_scale": [1.0, 1.0],
        "coef": [[2.0, 0.0], [0.0, 2.0], [-1.0, -1.0]], "intercept": [0.0, 0.0, 0.0]}


def test_probabilities_sum_to_one_and_pick_the_largest_logit():
    p = head_probs([1.0, 0.0], HEAD)
    assert abs(sum(p.values()) - 1) < 1e-9
    assert max(p, key=p.get) == "a"


def test_allowed_restricts_to_loaded_types():
    p = head_probs([1.0, 0.0], HEAD, allowed={"b", "c"})
    assert p["a"] == 0.0
    assert max(p, key=p.get) == "b"


def test_no_allowed_class_is_an_error():
    with pytest.raises(ValueError):
        head_probs([1.0, 0.0], HEAD, allowed={"z"})
