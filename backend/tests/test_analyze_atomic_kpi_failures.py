from scripts.analyze_atomic_kpi_failures import _classify_failure_bucket, _is_atomic_plan_source


def test_is_atomic_plan_source_variants():
    assert _is_atomic_plan_source("atomic_overhaul_v1")
    assert _is_atomic_plan_source("atomic_overhaul_v1_clarification2")
    assert not _is_atomic_plan_source("stepwise_template")


def test_classify_failure_bucket_success():
    assert _classify_failure_bucket("success", None, None) == "success"


def test_classify_failure_bucket_oauth_auth():
    assert _classify_failure_bucket("error", "auth_error", "") == "oauth_auth"


def test_classify_failure_bucket_needs_input():
    assert _classify_failure_bucket("error", "clarification_needed", "") == "needs_input_or_policy"


def test_classify_failure_bucket_tool_execution():
    assert _classify_failure_bucket("error", "tool_failed", "services=linear") == "tool_execution"


def test_classify_failure_bucket_tool_failed_auth_hint():
    assert _classify_failure_bucket("error", "tool_failed", "message=unauthorized") == "oauth_auth"
