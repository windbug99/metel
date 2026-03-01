from scripts.check_atomic_shadow_log_parity import evaluate_parity


def test_evaluate_parity_matches_request_ids():
    command_rows = [
        {
            "status": "success",
            "error_code": None,
            "detail": "services=notion;request_id=tg_update:100;atomic_overhaul_shadow_mode=0",
        },
        {
            "status": "error",
            "error_code": "tool_failed",
            "detail": "services=linear;request_id=tg_update:101;atomic_overhaul_shadow_mode=1",
        },
    ]
    pipeline_rows = [
        {"request_id": "tg_update:100"},
        {"request_id": "tg_update:101"},
    ]
    report = evaluate_parity(command_rows=command_rows, pipeline_rows=pipeline_rows)
    assert report["compare_ready"] is True
    assert report["shadow_compare_ready"] is True
    assert report["matched_count"] == 2
    assert report["shadow_matched_count"] == 1


def test_evaluate_parity_returns_not_ready_when_no_target_rows():
    command_rows = [{"status": "success", "error_code": None, "detail": "services=notion;request_id=tg_update:200"}]
    pipeline_rows = [{"request_id": "tg_update:200"}]
    report = evaluate_parity(command_rows=command_rows, pipeline_rows=pipeline_rows)
    assert report["compare_ready"] is False
    assert report["shadow_compare_ready"] is False
