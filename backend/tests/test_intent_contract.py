import pytest

from agent.intent_contract import (
    ERROR_INVALID_INTENT_JSON,
    INTENT_MODE_LLM_ONLY,
    INTENT_MODE_LLM_THEN_SKILL,
    INTENT_SCHEMA_V1,
    IntentValidationError,
    parse_intent_json,
    validate_intent_json,
)


def test_parse_intent_json_parses_object():
    payload = parse_intent_json(
        '{"mode":"LLM_ONLY","skill_name":null,"arguments":{},"missing_fields":[],"confidence":0.8,"decision_reason":"ok"}'
    )
    assert payload["mode"] == "LLM_ONLY"


def test_validate_intent_json_llm_only():
    intent = validate_intent_json(
        {
            "mode": "LLM_ONLY",
            "skill_name": None,
            "arguments": {},
            "missing_fields": [],
            "confidence": 0.7,
            "decision_reason": "general_chat",
        },
        connected_services=["linear", "notion"],
    )
    assert intent.mode == INTENT_MODE_LLM_ONLY
    assert intent.skill_name is None
    assert intent.decision_reason == "general_chat"
    assert intent.schema_version == "v0"
    assert intent.event_filter == {"keyword_include": [], "keyword_exclude": []}


def test_validate_intent_json_accepts_v1_extended_fields():
    intent = validate_intent_json(
        {
            "schema_version": INTENT_SCHEMA_V1,
            "mode": "LLM_THEN_SKILL",
            "skill_name": "linear.issue_create",
            "arguments": {"title": "회의 액션 아이템 정리"},
            "missing_fields": [],
            "confidence": 0.91,
            "decision_reason": "calendar_to_linear",
            "time_scope": "today",
            "event_filter": {
                "keyword_include": ["회의"],
                "keyword_exclude": ["점심"],
            },
            "target_scope": "linear_only",
            "result_limit": 12,
        },
        connected_services=["linear"],
    )
    assert intent.schema_version == "v1"
    assert intent.time_scope == "today"
    assert intent.target_scope == "linear_only"
    assert intent.event_filter["keyword_include"] == ["회의"]
    assert intent.event_filter["keyword_exclude"] == ["점심"]
    assert intent.result_limit == 12


def test_validate_intent_json_rejects_invalid_extended_fields():
    with pytest.raises(IntentValidationError):
        validate_intent_json(
            {
                "schema_version": "v3",
                "mode": "LLM_ONLY",
                "skill_name": None,
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.7,
                "decision_reason": "x",
            }
        )
    with pytest.raises(IntentValidationError):
        validate_intent_json(
            {
                "schema_version": "v1",
                "mode": "LLM_ONLY",
                "skill_name": None,
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.7,
                "decision_reason": "x",
                "time_scope": "yesterday",
            }
        )
    with pytest.raises(IntentValidationError):
        validate_intent_json(
            {
                "schema_version": "v1",
                "mode": "LLM_ONLY",
                "skill_name": None,
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.7,
                "decision_reason": "x",
                "target_scope": "google_only",
            }
        )
    with pytest.raises(IntentValidationError):
        validate_intent_json(
            {
                "schema_version": "v1",
                "mode": "LLM_ONLY",
                "skill_name": None,
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.7,
                "decision_reason": "x",
                "event_filter": {"keyword_include": "회의"},
            }
        )


def test_validate_intent_json_requires_skill_for_non_llm_only():
    with pytest.raises(IntentValidationError) as exc:
        validate_intent_json(
            {
                "mode": "LLM_THEN_SKILL",
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.9,
                "decision_reason": "mutation",
            }
        )
    assert exc.value.code == ERROR_INVALID_INTENT_JSON
    assert "requires_skill" in str(exc.value)


def test_validate_intent_json_rejects_skill_for_llm_only():
    with pytest.raises(IntentValidationError) as exc:
        validate_intent_json(
            {
                "mode": "LLM_ONLY",
                "skill_name": "linear.issue_update",
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.8,
                "decision_reason": "x",
            }
        )
    assert exc.value.code == ERROR_INVALID_INTENT_JSON


def test_validate_intent_json_rejects_invalid_mode():
    with pytest.raises(IntentValidationError) as exc:
        validate_intent_json(
            {
                "mode": "UNKNOWN",
                "skill_name": None,
                "arguments": {},
                "missing_fields": [],
                "confidence": 0.8,
                "decision_reason": "x",
            }
        )
    assert exc.value.code == ERROR_INVALID_INTENT_JSON


def test_validate_intent_json_rejects_non_object_arguments():
    with pytest.raises(IntentValidationError) as exc:
        validate_intent_json(
            {
                "mode": "LLM_THEN_SKILL",
                "skill_name": "linear.issue_update",
                "arguments": "bad",
                "missing_fields": [],
                "confidence": 0.8,
                "decision_reason": "x",
            }
        )
    assert exc.value.code == ERROR_INVALID_INTENT_JSON


def test_validate_intent_json_rejects_when_skill_service_not_connected():
    with pytest.raises(IntentValidationError) as exc:
        validate_intent_json(
            {
                "mode": INTENT_MODE_LLM_THEN_SKILL,
                "skill_name": "linear.issue_update",
                "arguments": {"linear_issue_ref": "OPT-46"},
                "missing_fields": [],
                "confidence": 0.95,
                "decision_reason": "linear_mutation",
            },
            connected_services=["notion"],
        )
    assert exc.value.code == ERROR_INVALID_INTENT_JSON


def test_validate_intent_json_accepts_connected_skill():
    intent = validate_intent_json(
        {
            "mode": INTENT_MODE_LLM_THEN_SKILL,
            "skill_name": "linear.issue_update",
            "arguments": {"linear_issue_ref": "OPT-46"},
            "missing_fields": [],
            "confidence": 1.0,
            "decision_reason": "linear_mutation",
        },
        connected_services=["linear", "notion"],
    )
    assert intent.skill_name == "linear.issue_update"
    assert intent.arguments["linear_issue_ref"] == "OPT-46"
