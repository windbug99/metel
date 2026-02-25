from datetime import datetime, timezone

from scripts.eval_agent_quality import (
    _evaluate_gate,
    _build_markdown_report,
    _build_policy_recommendations,
    _dedupe_rows_by_request_id,
    _parse_detail_pairs,
    _window_start_iso_utc,
    _build_tuning_hints,
    _top_items,
)


def test_top_items_sorts_descending():
    items = {"b": 1, "a": 3, "c": 2}
    top = _top_items(items, limit=2)
    assert top == [("a", 3), ("c", 2)]


def test_window_start_iso_utc_with_fixed_now():
    now = datetime(2026, 2, 26, 12, 34, 56, tzinfo=timezone.utc)
    assert _window_start_iso_utc(3, now=now) == "2026-02-23T12:34:56Z"
    assert _window_start_iso_utc(0, now=now) == ""


def test_parse_detail_pairs_reads_structured_fields():
    parsed = _parse_detail_pairs(
        "services=notion;request_id=tg_update:1;intent_json={\"target_scope\":\"notion_only\"};autonomous_json={\"attempted\":true}"
    )
    assert parsed["services"] == "notion"
    assert parsed["request_id"] == "tg_update:1"
    assert "target_scope" in parsed["intent_json"]


def test_dedupe_rows_by_request_id_prefers_success_over_failed():
    rows = [
        {
            "status": "error",
            "execution_mode": "rule",
            "autonomous_fallback_reason": "verification_failed",
            "verification_reason": "x",
            "error_code": "verification_failed",
            "detail": "request_id=tg_update:10;autonomous_json={\"attempted\":true,\"fallback\":true}",
            "created_at": "2026-02-25T10:00:00Z",
        },
        {
            "status": "success",
            "execution_mode": "autonomous",
            "autonomous_fallback_reason": "",
            "verification_reason": "",
            "error_code": "",
            "detail": "request_id=tg_update:10;autonomous_json={\"attempted\":true,\"success\":true}",
            "created_at": "2026-02-25T10:00:01Z",
        },
    ]
    deduped = _dedupe_rows_by_request_id(rows)
    assert len(deduped) == 1
    assert deduped[0]["status"] == "success"


def test_build_tuning_hints_maps_known_reasons():
    hints = _build_tuning_hints(
        top_fallback=[("turn_limit", 5), ("append_requires_multiple_targets", 2)],
        top_verification=[("verification_failed", 4)],
        top_error_codes=[("llm_planner_failed", 1)],
    )
    assert any("turn_limit" in hint for hint in hints)
    assert any("복수 대상 append" in hint or "각각" in hint for hint in hints)


def test_build_policy_recommendations_outputs_env_actions():
    recs = _build_policy_recommendations(
        top_fallback=[("turn_limit", 5), ("tool_call_limit", 3)],
        top_verification=[("append_requires_multiple_targets", 2)],
        top_error_codes=[("llm_planner_failed", 1)],
    )
    keys = {item["env_key"] for item in recs}
    assert "LLM_AUTONOMOUS_MAX_TURNS" in keys
    assert "LLM_AUTONOMOUS_MAX_TOOL_CALLS" in keys
    assert "LLM_AUTONOMOUS_LIMIT_RETRY_ONCE" in keys
    assert "LLM_PLANNER_RULE_FALLBACK_ENABLED" in keys


def test_build_markdown_report_includes_new_sections():
    report = _build_markdown_report(
        total=30,
        min_sample=20,
        autonomous_success=18,
        autonomous_count=20,
        autonomous_success_rate=0.9,
        target_autonomous_success=0.8,
        fallback_count=4,
        fallback_rate=0.1333,
        max_fallback_rate=0.2,
        top_fallback=[("turn_limit", 2)],
        top_verification=[("verification_failed", 1)],
        top_error_codes=[("llm_planner_failed", 1)],
        autonomous_attempt_count=24,
        autonomous_attempt_rate=0.8,
        autonomous_success_over_attempt_rate=0.75,
        planner_failed_count=1,
        planner_failed_rate=0.033,
        max_planner_failed_rate=0.2,
        verification_failed_count=2,
        verification_failed_rate=0.066,
        max_verification_failed_rate=0.25,
        guardrail_degrade_count=3,
        guardrail_degrade_rate=0.10,
        max_guardrail_degrade_rate=0.40,
        top_guardrail_degrade=[("tool_error_rate", 2)],
        top_plan_source=[("llm", 18), ("rule", 12)],
        top_execution_mode=[("autonomous", 20), ("rule", 10)],
        tuning_hints=["turn_limit 비중이 높습니다."],
        policy_recommendations=[
            {
                "env_key": "LLM_AUTONOMOUS_MAX_TURNS",
                "suggested_value": "8",
                "reason": "turn_limit 비중이 높습니다.",
            }
        ],
        gate_reasons=["autonomous_success_rate_below_target: 0.700 < 0.800"],
        verdict="PASS",
    )
    assert "## Plan Source Distribution" in report
    assert "## Execution Mode Distribution" in report
    assert "## Top Guardrail Degrade Reasons" in report
    assert "## Tuning Hints" in report
    assert "## Policy Recommendations" in report
    assert "## Gate Reasons" in report


def test_evaluate_gate_fail_on_insufficient_sample():
    verdict, reasons, passed = _evaluate_gate(
        total=5,
        min_sample=20,
        fail_on_insufficient_sample=True,
        autonomous_success_rate=1.0,
        target_autonomous_success=0.8,
        fallback_rate=0.0,
        max_fallback_rate=0.2,
        planner_failed_rate=0.0,
        max_planner_failed_rate=0.2,
        verification_failed_rate=0.0,
        max_verification_failed_rate=0.25,
        guardrail_degrade_rate=0.0,
        max_guardrail_degrade_rate=0.4,
        autonomous_attempt_rate=1.0,
        min_autonomous_attempt_rate=0.5,
        autonomous_success_over_attempt_rate=1.0,
        min_autonomous_success_over_attempt_rate=0.7,
    )
    assert verdict == "FAIL"
    assert passed is False
    assert any("insufficient_sample" in reason for reason in reasons)


def test_evaluate_gate_pass_when_all_thresholds_met():
    verdict, reasons, passed = _evaluate_gate(
        total=30,
        min_sample=20,
        fail_on_insufficient_sample=True,
        autonomous_success_rate=0.85,
        target_autonomous_success=0.8,
        fallback_rate=0.1,
        max_fallback_rate=0.2,
        planner_failed_rate=0.05,
        max_planner_failed_rate=0.2,
        verification_failed_rate=0.05,
        max_verification_failed_rate=0.25,
        guardrail_degrade_rate=0.10,
        max_guardrail_degrade_rate=0.4,
        autonomous_attempt_rate=0.75,
        min_autonomous_attempt_rate=0.5,
        autonomous_success_over_attempt_rate=0.8,
        min_autonomous_success_over_attempt_rate=0.7,
    )
    assert verdict == "PASS"
    assert passed is True
    assert reasons == []


def test_evaluate_gate_fail_on_guardrail_degrade_rate():
    verdict, reasons, passed = _evaluate_gate(
        total=30,
        min_sample=20,
        fail_on_insufficient_sample=True,
        autonomous_success_rate=0.9,
        target_autonomous_success=0.8,
        fallback_rate=0.1,
        max_fallback_rate=0.2,
        planner_failed_rate=0.05,
        max_planner_failed_rate=0.2,
        verification_failed_rate=0.1,
        max_verification_failed_rate=0.25,
        guardrail_degrade_rate=0.5,
        max_guardrail_degrade_rate=0.4,
        autonomous_attempt_rate=0.75,
        min_autonomous_attempt_rate=0.5,
        autonomous_success_over_attempt_rate=0.8,
        min_autonomous_success_over_attempt_rate=0.7,
    )
    assert verdict == "FAIL"
    assert passed is False
    assert any("guardrail_degrade_rate_above_target" in reason for reason in reasons)
