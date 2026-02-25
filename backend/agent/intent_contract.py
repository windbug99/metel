from __future__ import annotations

import json
from dataclasses import dataclass, field


INTENT_SCHEMA_V0 = "v0"
INTENT_SCHEMA_V1 = "v1"
ALLOWED_INTENT_SCHEMA_VERSIONS = {
    INTENT_SCHEMA_V0,
    INTENT_SCHEMA_V1,
}

INTENT_MODE_LLM_ONLY = "LLM_ONLY"
INTENT_MODE_LLM_THEN_SKILL = "LLM_THEN_SKILL"
INTENT_MODE_SKILL_THEN_LLM = "SKILL_THEN_LLM"

ALLOWED_INTENT_MODES = {
    INTENT_MODE_LLM_ONLY,
    INTENT_MODE_LLM_THEN_SKILL,
    INTENT_MODE_SKILL_THEN_LLM,
}

ERROR_INVALID_INTENT_JSON = "invalid_intent_json"
ALLOWED_TIME_SCOPES = {"today", "date_range", "explicit_date"}
ALLOWED_TARGET_SCOPES = {"linear_only", "notion_only", "notion_and_linear"}


class IntentValidationError(ValueError):
    def __init__(self, message: str, *, code: str = ERROR_INVALID_INTENT_JSON) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class IntentPayload:
    mode: str
    skill_name: str | None
    schema_version: str = INTENT_SCHEMA_V0
    arguments: dict = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    decision_reason: str = ""
    time_scope: str | None = None
    event_filter: dict[str, list[str]] = field(
        default_factory=lambda: {"keyword_include": [], "keyword_exclude": []}
    )
    target_scope: str | None = None
    result_limit: int | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "skill_name": self.skill_name,
            "arguments": dict(self.arguments),
            "missing_fields": list(self.missing_fields),
            "confidence": float(self.confidence),
            "decision_reason": self.decision_reason,
            "time_scope": self.time_scope,
            "event_filter": {
                "keyword_include": list((self.event_filter or {}).get("keyword_include", [])),
                "keyword_exclude": list((self.event_filter or {}).get("keyword_exclude", [])),
            },
            "target_scope": self.target_scope,
            "result_limit": self.result_limit,
        }


def parse_intent_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise IntentValidationError("empty_intent_json")
    try:
        payload = json.loads(text)
    except Exception as exc:  # pragma: no cover
        raise IntentValidationError("invalid_json_syntax") from exc
    if not isinstance(payload, dict):
        raise IntentValidationError("intent_json_must_be_object")
    return payload


def _service_for_skill_name(skill_name: str) -> str | None:
    token = (skill_name or "").strip().lower()
    if token.startswith("linear."):
        return "linear"
    if token.startswith("notion."):
        return "notion"
    return None


def validate_intent_json(payload: dict, *, connected_services: list[str] | None = None) -> IntentPayload:
    if not isinstance(payload, dict):
        raise IntentValidationError("intent_json_must_be_object")

    schema_version = str(payload.get("schema_version") or "").strip().lower() or INTENT_SCHEMA_V0
    if schema_version not in ALLOWED_INTENT_SCHEMA_VERSIONS:
        raise IntentValidationError("intent_schema_version_invalid")

    mode = str(payload.get("mode") or "").strip()
    if mode not in ALLOWED_INTENT_MODES:
        raise IntentValidationError("intent_mode_invalid")

    skill_raw = payload.get("skill_name")
    skill_name = str(skill_raw).strip() if skill_raw is not None else ""
    skill_name = skill_name or None

    if mode == INTENT_MODE_LLM_ONLY and skill_name:
        raise IntentValidationError("llm_only_must_not_have_skill")
    if mode != INTENT_MODE_LLM_ONLY and not skill_name:
        raise IntentValidationError("non_llm_only_requires_skill")

    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        raise IntentValidationError("intent_arguments_must_be_object")

    missing_fields_raw = payload.get("missing_fields", [])
    if not isinstance(missing_fields_raw, list):
        raise IntentValidationError("intent_missing_fields_must_be_array")
    missing_fields: list[str] = []
    for item in missing_fields_raw:
        value = str(item).strip()
        if value:
            missing_fields.append(value)

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except Exception as exc:
        raise IntentValidationError("intent_confidence_must_be_number") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise IntentValidationError("intent_confidence_out_of_range")

    decision_reason = str(payload.get("decision_reason") or "").strip()
    if not decision_reason:
        raise IntentValidationError("intent_decision_reason_required")

    time_scope_raw = payload.get("time_scope")
    time_scope = str(time_scope_raw or "").strip().lower() or None
    if time_scope and time_scope not in ALLOWED_TIME_SCOPES:
        raise IntentValidationError("intent_time_scope_invalid")

    event_filter_raw = payload.get("event_filter") or {}
    if not isinstance(event_filter_raw, dict):
        raise IntentValidationError("intent_event_filter_must_be_object")
    include_raw = event_filter_raw.get("keyword_include") or []
    exclude_raw = event_filter_raw.get("keyword_exclude") or []
    if not isinstance(include_raw, list) or not isinstance(exclude_raw, list):
        raise IntentValidationError("intent_event_filter_keywords_must_be_array")
    keyword_include = [str(item).strip() for item in include_raw if str(item).strip()]
    keyword_exclude = [str(item).strip() for item in exclude_raw if str(item).strip()]

    target_scope_raw = payload.get("target_scope")
    target_scope = str(target_scope_raw or "").strip().lower() or None
    if target_scope and target_scope not in ALLOWED_TARGET_SCOPES:
        raise IntentValidationError("intent_target_scope_invalid")

    result_limit_raw = payload.get("result_limit")
    result_limit: int | None = None
    if result_limit_raw is not None:
        try:
            result_limit = int(str(result_limit_raw).strip())
        except Exception as exc:
            raise IntentValidationError("intent_result_limit_must_be_integer") from exc
        if result_limit < 1:
            raise IntentValidationError("intent_result_limit_out_of_range")

    if connected_services is not None and skill_name:
        connected = {str(item).strip().lower() for item in connected_services if str(item).strip()}
        service = _service_for_skill_name(skill_name)
        if service and service not in connected:
            raise IntentValidationError("intent_skill_service_not_connected")

    return IntentPayload(
        schema_version=schema_version,
        mode=mode,
        skill_name=skill_name,
        arguments=dict(arguments),
        missing_fields=missing_fields,
        confidence=confidence,
        decision_reason=decision_reason,
        time_scope=time_scope,
        event_filter={
            "keyword_include": keyword_include,
            "keyword_exclude": keyword_exclude,
        },
        target_scope=target_scope,
        result_limit=result_limit,
    )
