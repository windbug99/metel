from scripts.eval_stepwise_vs_legacy_quality import (
    _classify_mode,
    _compute_mode_metrics,
)


def test_classify_mode_stepwise_dag_legacy():
    assert _classify_mode({"detail": 'pipeline_json={"router_mode":"STEPWISE_PIPELINE"}'}) == "stepwise"
    assert _classify_mode({"detail": 'pipeline_json={"composed_pipeline":true}'}) == "dag"
    assert _classify_mode({"detail": "services=google;dag_pipeline=1", "plan_source": "dag_template"}) == "dag"
    assert _classify_mode({"detail": "services=notion", "plan_source": "stepwise_template"}) == "stepwise"
    assert _classify_mode({"detail": "services=notion"}) == "legacy"


def test_compute_mode_metrics_basic_rates():
    rows = [
        {
            "status": "success",
            "final_status": "success",
            "error_code": "",
            "detail": 'analysis_latency_ms=100;pipeline_json={"router_mode":"STEPWISE_PIPELINE"}',
        },
        {
            "status": "error",
            "final_status": "error",
            "error_code": "validation_error",
            "detail": 'analysis_latency_ms=300;pipeline_json={"router_mode":"STEPWISE_PIPELINE"}',
        },
        {
            "status": "success",
            "final_status": "success",
            "error_code": "",
            "detail": 'analysis_latency_ms=200;pipeline_json={"composed_pipeline":true}',
        },
        {
            "status": "error",
            "final_status": "error",
            "error_code": "tool_failed",
            "detail": "analysis_latency_ms=400",
        },
    ]
    metrics = _compute_mode_metrics(rows)
    stepwise = metrics["stepwise"]
    assert stepwise["run_count"] == 2
    assert stepwise["success_rate_pct"] == 50.0
    assert stepwise["error_rate_pct"] == 50.0
    assert stepwise["validation_fail_rate_pct"] == 50.0
    assert stepwise["p95_latency_ms"] == 300

    dag = metrics["dag"]
    assert dag["run_count"] == 1
    assert dag["success_rate_pct"] == 100.0
    assert dag["error_rate_pct"] == 0.0

    legacy = metrics["legacy"]
    assert legacy["run_count"] == 1
    assert legacy["success_rate_pct"] == 0.0
    assert legacy["error_rate_pct"] == 100.0
