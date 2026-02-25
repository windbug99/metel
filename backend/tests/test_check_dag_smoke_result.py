from scripts.check_dag_smoke_result import (
    _evaluate_smoke,
    _find_latest_dag_row,
    _parse_detail_pairs,
)


def test_parse_detail_pairs():
    out = _parse_detail_pairs("services=google,notion;dag_pipeline=1;pipeline_run_id=prun_123")
    assert out["dag_pipeline"] == "1"
    assert out["pipeline_run_id"] == "prun_123"


def test_find_latest_dag_row():
    rows = [
        {"detail": "services=google;pipeline_run_id=prun_a", "plan_source": "llm"},
        {"detail": "services=google;dag_pipeline=1;pipeline_run_id=prun_b", "plan_source": "dag_template"},
    ]
    row = _find_latest_dag_row(rows)
    assert row is not None
    assert "prun_b" in str(row.get("detail"))


def test_find_latest_dag_row_with_dag_template_without_pipeline_run_id():
    rows = [
        {"detail": "services=google", "plan_source": "llm"},
        {"detail": "services=google,notion,linear", "plan_source": "dag_template"},
    ]
    row = _find_latest_dag_row(rows)
    assert row is not None
    assert row.get("plan_source") == "dag_template"


def test_evaluate_smoke_pass_and_fail():
    passed, reasons = _evaluate_smoke(
        dag_row_found=True,
        pipeline_run_id="prun_ok",
        succeeded_links_count=2,
        dag_quality_verdict="PASS",
    )
    assert passed is True
    assert reasons == []

    passed2, reasons2 = _evaluate_smoke(
        dag_row_found=False,
        pipeline_run_id="",
        succeeded_links_count=0,
        dag_quality_verdict="FAIL",
    )
    assert passed2 is False
    assert "missing_dag_row" in reasons2
    assert "missing_pipeline_run_id" in reasons2
    assert "missing_succeeded_pipeline_links" in reasons2
    assert "dag_quality_not_pass:FAIL" in reasons2
