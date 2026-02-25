from scripts.eval_dag_quality import _build_policy_recommendations, _compute_metrics, _evaluate_gate


def test_compute_metrics_counts_dag_error_codes_and_reuse():
    rows = [
        {
            "error_code": "",
            "detail": "services=google,notion,linear;dag_pipeline=1;pipeline_run_id=prun_1;idempotent_success_reuse_count=2",
        },
        {
            "error_code": "DSL_REF_NOT_FOUND",
            "detail": "services=google;dag_pipeline=1;pipeline_run_id=prun_2;idempotent_success_reuse_count=0",
        },
        {
            "error_code": "COMPENSATION_FAILED",
            "detail": "services=google;pipeline_run_id=prun_3",
        },
        {
            "error_code": "validation_error",
            "detail": "services=notion",
        },
    ]
    links = [
        {"status": "succeeded", "error_code": ""},
        {"status": "manual_required", "error_code": "COMPENSATION_FAILED"},
        {"status": "failed", "error_code": "VERIFY_COUNT_MISMATCH"},
    ]
    metrics = _compute_metrics(rows, links)
    assert metrics["dag_sample_size"] == 3
    assert metrics["pipeline_links_sample_size"] == 3
    assert metrics["manual_required_count"] == 1
    assert metrics["manual_required_rate"] == 1 / 3
    assert metrics["dsl_ref_not_found_count"] == 1
    assert metrics["compensation_failed_count"] == 1
    assert metrics["idempotent_success_reuse_total"] == 2
    assert metrics["idempotent_success_reuse_rate"] == 2 / 3
    assert metrics["pipeline_links_error_code_counts"]["COMPENSATION_FAILED"] == 1
    assert metrics["pipeline_links_error_code_counts"]["VERIFY_COUNT_MISMATCH"] == 1


def test_evaluate_gate_fails_on_threshold_breach():
    verdict, reasons, passed = _evaluate_gate(
        dag_sample_size=30,
        min_sample=20,
        fail_on_insufficient_sample=True,
        dsl_validation_failed_rate=0.12,
        max_dsl_validation_failed_rate=0.10,
        dsl_ref_not_found_rate=0.03,
        max_dsl_ref_not_found_rate=0.05,
        verify_count_mismatch_rate=0.20,
        max_verify_count_mismatch_rate=0.10,
        compensation_failed_rate=0.01,
        max_compensation_failed_rate=0.02,
        manual_required_rate=0.10,
        max_manual_required_rate=0.05,
        idempotent_success_reuse_rate=0.0,
        min_idempotent_success_reuse_rate=0.0,
    )
    assert verdict == "FAIL"
    assert passed is False
    assert any("dsl_validation_failed_rate_above_target" in item for item in reasons)
    assert any("verify_count_mismatch_rate_above_target" in item for item in reasons)
    assert any("manual_required_rate_above_target" in item for item in reasons)


def test_evaluate_gate_passes_when_within_thresholds():
    verdict, reasons, passed = _evaluate_gate(
        dag_sample_size=30,
        min_sample=20,
        fail_on_insufficient_sample=True,
        dsl_validation_failed_rate=0.01,
        max_dsl_validation_failed_rate=0.10,
        dsl_ref_not_found_rate=0.0,
        max_dsl_ref_not_found_rate=0.05,
        verify_count_mismatch_rate=0.03,
        max_verify_count_mismatch_rate=0.10,
        compensation_failed_rate=0.0,
        max_compensation_failed_rate=0.02,
        manual_required_rate=0.0,
        max_manual_required_rate=0.05,
        idempotent_success_reuse_rate=0.02,
        min_idempotent_success_reuse_rate=0.0,
    )
    assert verdict == "PASS"
    assert passed is True
    assert reasons == []


def test_build_policy_recommendations_returns_allowlisted_actions():
    recs = _build_policy_recommendations(
        dsl_validation_failed_rate=0.2,
        dsl_ref_not_found_rate=0.1,
        verify_count_mismatch_rate=0.2,
        compensation_failed_rate=0.1,
        manual_required_rate=0.1,
        idempotent_success_reuse_rate=0.0,
    )
    keys = {item["env_key"] for item in recs}
    assert "TOOL_SPECS_VALIDATE_ON_STARTUP" in keys
    assert "LLM_HYBRID_EXECUTOR_FIRST" in keys
    assert "LLM_AUTONOMOUS_LIMIT_RETRY_ONCE" in keys
