from scripts.decide_skill_v2_rollout import _recommend


def _report(*, verdict="PASS", sample=100, min_sample=30, shadow_ok=0.9, shadow_count=100, v2_selected=20):
    return {
        "verdict": verdict,
        "sample_size": sample,
        "min_sample": min_sample,
        "shadow_ok_rate": shadow_ok,
        "shadow_count": shadow_count,
        "v2_selected_count": v2_selected,
    }


def test_recommend_promote_from_zero_when_pass_and_shadow_ok():
    action, next_percent, reasons = _recommend(
        report=_report(),
        current_percent=0,
        require_shadow_ok_for_promote=True,
    )
    assert action == "promote"
    assert next_percent == 10


def test_recommend_hold_when_shadow_not_ok():
    action, next_percent, reasons = _recommend(
        report=_report(shadow_ok=0.6),
        current_percent=0,
        require_shadow_ok_for_promote=True,
    )
    assert action == "hold"
    assert next_percent == 0


def test_recommend_hold_when_shadow_count_below_minimum():
    action, next_percent, reasons = _recommend(
        report=_report(sample=100, min_sample=30, shadow_ok=0.9, shadow_count=10),
        current_percent=0,
        require_shadow_ok_for_promote=True,
    )
    assert action == "hold"
    assert next_percent == 0


def test_recommend_rollback_on_fail():
    action, next_percent, reasons = _recommend(
        report=_report(verdict="FAIL"),
        current_percent=30,
        require_shadow_ok_for_promote=False,
    )
    assert action == "rollback"
    assert next_percent == 10


def test_recommend_hold_when_no_v2_samples_in_canary():
    action, next_percent, reasons = _recommend(
        report=_report(v2_selected=0),
        current_percent=10,
        require_shadow_ok_for_promote=False,
    )
    assert action == "hold"
    assert next_percent == 10
