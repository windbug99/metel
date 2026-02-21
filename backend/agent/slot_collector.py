from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent.slot_schema import get_action_slot_schema, normalize_slots, validate_slots


@dataclass
class SlotCollectionResult:
    collected_slots: dict[str, Any]
    missing_slots: list[str]
    validation_errors: list[str]
    ask_next_slot: str | None = None
    confidence_by_slot: dict[str, float] = field(default_factory=dict)


def slot_prompt_example(action: str, slot_name: str) -> str:
    schema = get_action_slot_schema(action)
    if not schema:
        return f"{slot_name}: <값>"
    aliases = schema.aliases.get(slot_name) or ()
    key = aliases[0] if aliases else slot_name
    rule = schema.validation_rules.get(slot_name) or {}
    value_type = str(rule.get("type", "")).strip().lower()
    if value_type == "integer":
        return f"{key}: 5"
    if value_type == "boolean":
        return f"{key}: true"
    return f'{key}: "값"'


def collect_slots_from_user_reply(
    *,
    action: str,
    user_text: str,
    collected_slots: dict[str, Any],
    preferred_slot: str | None = None,
) -> SlotCollectionResult:
    schema = get_action_slot_schema(action)
    merged = dict(collected_slots or {})
    confidence: dict[str, float] = {}
    raw = (user_text or "").strip()

    if raw:
        # keyed form: "제목: foo", "issue_id=OPT-36"
        keyed_updates = _extract_keyed_slot_values(action=action, text=raw)
        for key, value in keyed_updates.items():
            merged[key] = value
            confidence[key] = 0.95

        # If no keyed update matched, treat the whole answer as preferred slot value.
        if preferred_slot and preferred_slot not in keyed_updates:
            parsed = _parse_slot_value(action=action, slot_name=preferred_slot, text=raw)
            if parsed not in (None, ""):
                merged[preferred_slot] = parsed
                confidence[preferred_slot] = 0.75

    normalized = normalize_slots(action, merged)
    normalized, missing_slots, validation_errors = validate_slots(action, normalized)
    ask_next_slot = missing_slots[0] if missing_slots else None
    return SlotCollectionResult(
        collected_slots=normalized,
        missing_slots=missing_slots,
        validation_errors=validation_errors,
        ask_next_slot=ask_next_slot,
        confidence_by_slot=confidence,
    )


def _extract_keyed_slot_values(*, action: str, text: str) -> dict[str, Any]:
    schema = get_action_slot_schema(action)
    if not schema:
        return {}
    alias_map: dict[str, str] = {}
    for slot_name, aliases in schema.aliases.items():
        alias_map[slot_name.lower()] = slot_name
        for alias in aliases:
            alias_map[str(alias).strip().lower()] = slot_name

    updates: dict[str, Any] = {}
    # Parse chained keyed values like "이슈: OPT-36 본문: 로그인 오류".
    key_marks = list(re.finditer(r"([0-9A-Za-z가-힣_]+)\s*[:=]\s*", text))
    for idx, mark in enumerate(key_marks):
        raw_key = mark.group(1).strip().lower()
        value_start = mark.end()
        value_end = key_marks[idx + 1].start() if idx + 1 < len(key_marks) else len(text)
        raw_value = text[value_start:value_end].strip().strip(",")
        slot_name = alias_map.get(raw_key)
        if not slot_name:
            continue
        parsed = _parse_slot_value(action=action, slot_name=slot_name, text=raw_value)
        if parsed in (None, ""):
            continue
        updates[slot_name] = parsed
    return updates


def _parse_slot_value(*, action: str, slot_name: str, text: str):
    schema = get_action_slot_schema(action)
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = raw.strip(" \"'`")
    if not schema:
        return raw
    rule = schema.validation_rules.get(slot_name) or {}
    value_type = str(rule.get("type", "")).strip().lower()

    if value_type == "integer":
        digits = re.search(r"-?\d+", raw)
        if digits:
            try:
                return int(digits.group(0))
            except Exception:
                return raw
    if value_type == "boolean":
        lowered = raw.lower()
        if lowered in {"true", "yes", "y", "1", "네", "예"}:
            return True
        if lowered in {"false", "no", "n", "0", "아니오", "아니요"}:
            return False
    return raw
