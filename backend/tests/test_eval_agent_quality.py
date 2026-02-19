from scripts.eval_agent_quality import (
    _evaluate_gate,
    _build_markdown_report,
    _build_policy_recommendations,
    _build_tuning_hints,
    _top_items,
)


def test_top_items_sorts_descending():
    items = {"b": 1, "a": 3, "c": 2}
    top = _top_items(items, limit=2)
    assert top == [("a", 3), ("c", 2)]


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
        autonomous_attempt_rate=0.75,
        min_autonomous_attempt_rate=0.5,
        autonomous_success_over_attempt_rate=0.8,
        min_autonomous_success_over_attempt_rate=0.7,
    )
    assert verdict == "PASS"
    assert passed is True
    assert reasons == []
