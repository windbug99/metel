from __future__ import annotations

import json
from dataclasses import dataclass, field


INTENT_MODE_LLM_ONLY = "LLM_ONLY"
INTENT_MODE_LLM_THEN_SKILL = "LLM_THEN_SKILL"
INTENT_MODE_SKILL_THEN_LLM = "SKILL_THEN_LLM"

ALLOWED_INTENT_MODES = {
    INTENT_MODE_LLM_ONLY,
    INTENT_MODE_LLM_THEN_SKILL,
    INTENT_MODE_SKILL_THEN_LLM,
}

ERROR_INVALID_INTENT_JSON = "invalid_intent_json"


class IntentValidationError(ValueError):
    def __init__(self, message: str, *, code: str = ERROR_INVALID_INTENT_JSON) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class IntentPayload:
    mode: str
    skill_name: str | None
    arguments: dict = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    decision_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "skill_name": self.skill_name,
            "arguments": dict(self.arguments),
            "missing_fields": list(self.missing_fields),
            "confidence": float(self.confidence),
            "decision_reason": self.decision_reason,
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

    if connected_services is not None and skill_name:
        connected = {str(item).strip().lower() for item in connected_services if str(item).strip()}
        service = _service_for_skill_name(skill_name)
        if service and service not in connected:
            raise IntentValidationError("intent_skill_service_not_connected")

    return IntentPayload(
        mode=mode,
        skill_name=skill_name,
        arguments=dict(arguments),
        missing_fields=missing_fields,
        confidence=confidence,
        decision_reason=decision_reason,
    )
