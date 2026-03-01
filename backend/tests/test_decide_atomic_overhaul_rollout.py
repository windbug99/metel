from scripts.decide_atomic_overhaul_rollout import _recommend


def _report(*, verdict="PASS", sample=100, min_sample=30):
    return {
        "verdict": verdict,
        "sample_size": sample,
        "min_sample": min_sample,
    }


def test_recommend_promote_when_pass_and_enough_sample():
    action, next_percent, _reasons = _recommend(report=_report(), current_percent=10)
    assert action == "promote"
    assert next_percent == 30


def test_recommend_hold_at_max_rollout():
    action, next_percent, _reasons = _recommend(report=_report(), current_percent=100)
    assert action == "hold"
    assert next_percent == 100


def test_recommend_hold_when_sample_insufficient():
    action, next_percent, _reasons = _recommend(report=_report(sample=10, min_sample=30), current_percent=10)
    assert action == "hold"
    assert next_percent == 10


def test_recommend_rollback_on_fail():
    action, next_percent, _reasons = _recommend(report=_report(verdict="FAIL"), current_percent=30)
    assert action == "rollback"
    assert next_percent == 10
