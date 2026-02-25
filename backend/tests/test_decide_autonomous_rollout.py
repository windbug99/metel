from scripts.decide_autonomous_rollout import _recommend


def _report(
    *,
    verdict: str = "PASS",
    sample_size: int = 100,
    min_sample: int = 30,
    fallback_rate: float = 0.05,
    success_over_attempt: float = 0.9,
    auth_error_count: int = 1,
) -> dict:
    return {
        "verdict": verdict,
        "sample_size": sample_size,
        "min_sample": min_sample,
        "fallback_rate": fallback_rate,
        "autonomous_success_over_attempt_rate": success_over_attempt,
        "error_code_counts": {"auth_error": auth_error_count},
    }


def test_recommend_promote_when_pass():
    action, next_percent, reasons = _recommend(
        report=_report(),
        current_percent=0,
        previous_report=None,
        max_fallback_rate_kill=0.20,
        min_success_over_attempt_kill=0.75,
        auth_error_surge_ratio=2.0,
    )
    assert action == "promote"
    assert next_percent == 10


def test_recommend_rollback_on_kill_fallback_rate():
    action, next_percent, reasons = _recommend(
        report=_report(fallback_rate=0.25),
        current_percent=30,
        previous_report=None,
        max_fallback_rate_kill=0.20,
        min_success_over_attempt_kill=0.75,
        auth_error_surge_ratio=2.0,
    )
    assert action == "rollback"
    assert next_percent == 10
    assert any(reason.startswith("kill:fallback_rate_above_threshold") for reason in reasons)


def test_recommend_rollback_on_auth_error_surge():
    prev = _report(auth_error_count=2)
    curr = _report(auth_error_count=6)
    action, next_percent, reasons = _recommend(
        report=curr,
        current_percent=10,
        previous_report=prev,
        max_fallback_rate_kill=0.20,
        min_success_over_attempt_kill=0.75,
        auth_error_surge_ratio=2.0,
    )
    assert action == "rollback"
    assert next_percent == 0
    assert any(reason.startswith("kill:auth_error_surge:") for reason in reasons)
