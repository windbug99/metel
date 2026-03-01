from scripts.check_atomic_cutover_readiness import evaluate_readiness


def test_cutover_readiness_pass():
    ready, reasons = evaluate_readiness(
        report={
            "verdict": "PASS",
            "current_percent": 100,
            "legacy_row_count": 0,
            "sample_size": 40,
            "min_sample": 30,
        },
        required_percent=100,
    )
    assert ready is True
    assert reasons == []


def test_cutover_readiness_fail_on_legacy_rows():
    ready, reasons = evaluate_readiness(
        report={
            "verdict": "PASS",
            "current_percent": 100,
            "legacy_row_count": 3,
            "sample_size": 40,
            "min_sample": 30,
        },
        required_percent=100,
    )
    assert ready is False
    assert any("legacy rows detected" in reason for reason in reasons)


def test_cutover_readiness_fail_on_percent():
    ready, reasons = evaluate_readiness(
        report={
            "verdict": "PASS",
            "current_percent": 30,
            "legacy_row_count": 0,
            "sample_size": 40,
            "min_sample": 30,
        },
        required_percent=100,
    )
    assert ready is False
    assert any("traffic percent below required" in reason for reason in reasons)
