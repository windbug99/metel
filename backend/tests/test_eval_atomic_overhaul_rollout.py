from scripts.eval_atomic_overhaul_rollout import _is_atomic_plan_source, _is_needs_input_outcome, _normalize_since_utc


def test_normalize_since_utc_z_suffix():
    assert _normalize_since_utc("2026-03-01T05:00:00Z") == "2026-03-01T05:00:00Z"


def test_normalize_since_utc_with_offset():
    assert _normalize_since_utc("2026-03-01T14:00:00+09:00") == "2026-03-01T05:00:00Z"


def test_normalize_since_utc_naive_is_utc():
    assert _normalize_since_utc("2026-03-01 05:00:00") == "2026-03-01T05:00:00Z"


def test_is_atomic_plan_source_variants():
    assert _is_atomic_plan_source("atomic_overhaul_v1")
    assert _is_atomic_plan_source("atomic_overhaul_v1_clarification2")
    assert not _is_atomic_plan_source("stepwise_template")


def test_is_needs_input_outcome_for_clarification():
    assert _is_needs_input_outcome("clarification_needed", {}) is True


def test_is_needs_input_outcome_for_validation_missing_slot():
    assert _is_needs_input_outcome("validation_error", {"missing_slot": "title"}) is True


def test_is_needs_input_outcome_for_plain_validation_error():
    assert _is_needs_input_outcome("validation_error", {}) is False
