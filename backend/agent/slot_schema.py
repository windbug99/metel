from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings


logger = logging.getLogger("metel-backend.slot_schema")

@dataclass(frozen=True)
class ActionSlotSchema:
    action: str
    required_slots: tuple[str, ...]
    optional_slots: tuple[str, ...]
    auto_fill_slots: tuple[str, ...]
    ask_order: tuple[str, ...]
    aliases: dict[str, tuple[str, ...]]
    validation_rules: dict[str, dict[str, Any]]

    @property
    def all_slots(self) -> tuple[str, ...]:
        return self.required_slots + self.optional_slots


NOTION_ID_PATTERN = r"^[0-9a-fA-F-]{32,36}$"
UUID_PATTERN = r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
LINEAR_ID_PATTERN = r"^[A-Za-z0-9_-]{2,64}$"


ACTION_SLOT_SCHEMAS: dict[str, ActionSlotSchema] = {
    "notion_search": ActionSlotSchema(
        action="notion_search",
        required_slots=(),
        optional_slots=("query", "page_size"),
        auto_fill_slots=("query",),
        ask_order=(),
        aliases={
            "query": ("검색어", "키워드", "title"),
            "page_size": ("개수", "수", "limit", "top"),
        },
        validation_rules={
            "query": {"type": "string", "min_length": 1, "max_length": 200},
            "page_size": {"type": "integer", "min": 1, "max": 20},
        },
    ),
    "notion_create_page": ActionSlotSchema(
        action="notion_create_page",
        required_slots=(),
        optional_slots=("title", "title_hint", "parent_page_id", "properties"),
        auto_fill_slots=("parent_page_id",),
        ask_order=("title",),
        aliases={
            "title": ("제목", "name"),
            "title_hint": ("title_hint", "제목힌트"),
            "parent_page_id": ("상위페이지", "parent_page_id"),
        },
        validation_rules={
            "title": {"type": "string", "min_length": 1, "max_length": 100},
            "title_hint": {"type": "string", "min_length": 1, "max_length": 100},
            "parent_page_id": {"type": "string", "pattern": NOTION_ID_PATTERN},
        },
    ),
    "notion_append_block_children": ActionSlotSchema(
        action="notion_append_block_children",
        required_slots=("block_id",),
        optional_slots=("children", "content", "content_type"),
        auto_fill_slots=("block_id",),
        ask_order=("block_id", "content"),
        aliases={
            "block_id": ("페이지", "page", "대상페이지", "target_page", "page_id", "block_id"),
            "children": ("children", "블록목록"),
            "content": ("본문", "내용", "text"),
            "content_type": ("형식", "타입", "type"),
        },
        validation_rules={
            "block_id": {"type": "string", "pattern": NOTION_ID_PATTERN},
            "content": {"type": "string", "min_length": 1, "max_length": 4000},
            "content_type": {"type": "string", "enum": ("paragraph", "bulleted_list_item", "to_do")},
        },
    ),
    "notion_update_page": ActionSlotSchema(
        action="notion_update_page",
        required_slots=("page_id",),
        optional_slots=("title", "archived", "parent_page_id"),
        auto_fill_slots=("page_id",),
        ask_order=("page_id", "title", "parent_page_id"),
        aliases={
            "page_id": ("페이지", "page", "target_page"),
            "title": ("제목", "새제목", "new_title"),
            "archived": ("삭제", "아카이브", "archive"),
            "parent_page_id": ("상위페이지", "이동할페이지", "parent"),
        },
        validation_rules={
            "page_id": {"type": "string", "pattern": NOTION_ID_PATTERN},
            "title": {"type": "string", "min_length": 1, "max_length": 100},
            "archived": {"type": "boolean"},
            "parent_page_id": {"type": "string", "pattern": NOTION_ID_PATTERN},
        },
    ),
    "notion_query_data_source": ActionSlotSchema(
        action="notion_query_data_source",
        required_slots=("data_source_id",),
        optional_slots=("page_size", "query"),
        auto_fill_slots=("data_source_id",),
        ask_order=("data_source_id",),
        aliases={
            "data_source_id": ("데이터소스", "datasource", "data_source"),
            "page_size": ("개수", "수", "limit"),
            "query": ("검색어", "키워드"),
        },
        validation_rules={
            "data_source_id": {"type": "string", "pattern": UUID_PATTERN},
            "page_size": {"type": "integer", "min": 1, "max": 50},
            "query": {"type": "string", "min_length": 1, "max_length": 200},
        },
    ),
    "linear_search_issues": ActionSlotSchema(
        action="linear_search_issues",
        required_slots=(),
        optional_slots=("query", "first", "team_id"),
        auto_fill_slots=("query", "team_id"),
        ask_order=(),
        aliases={
            "query": ("검색어", "키워드", "이슈"),
            "first": ("개수", "수", "limit"),
            "team_id": ("팀", "team"),
        },
        validation_rules={
            "query": {"type": "string", "min_length": 1, "max_length": 200},
            "first": {"type": "integer", "min": 1, "max": 20},
            "team_id": {"type": "string", "pattern": LINEAR_ID_PATTERN},
        },
    ),
    "linear_create_issue": ActionSlotSchema(
        action="linear_create_issue",
        required_slots=("title", "team_id"),
        optional_slots=("description", "priority"),
        auto_fill_slots=("team_id",),
        ask_order=("title", "team_id", "description"),
        aliases={
            "title": ("제목", "name"),
            "team_id": ("팀", "team"),
            "description": ("본문", "설명", "내용"),
            "priority": ("우선순위", "priority"),
        },
        validation_rules={
            "title": {"type": "string", "min_length": 1, "max_length": 200},
            "team_id": {"type": "string", "pattern": LINEAR_ID_PATTERN},
            "description": {"type": "string", "max_length": 8000},
            "priority": {"type": "integer", "enum": (0, 1, 2, 3, 4)},
        },
    ),
    "linear_update_issue": ActionSlotSchema(
        action="linear_update_issue",
        required_slots=("issue_id",),
        optional_slots=("title", "description", "state_id", "priority"),
        auto_fill_slots=("issue_id",),
        ask_order=("issue_id", "description", "title"),
        aliases={
            "issue_id": ("이슈", "issue", "이슈ID"),
            "title": ("제목", "name"),
            "description": ("본문", "설명", "내용"),
            "state_id": ("상태", "state"),
            "priority": ("우선순위", "priority"),
        },
        validation_rules={
            "issue_id": {"type": "string", "pattern": LINEAR_ID_PATTERN},
            "title": {"type": "string", "min_length": 1, "max_length": 200},
            "description": {"type": "string", "max_length": 8000},
            "state_id": {"type": "string", "pattern": LINEAR_ID_PATTERN},
            "priority": {"type": "integer", "enum": (0, 1, 2, 3, 4)},
        },
    ),
    "linear_create_comment": ActionSlotSchema(
        action="linear_create_comment",
        required_slots=("issue_id", "body"),
        optional_slots=(),
        auto_fill_slots=("issue_id",),
        ask_order=("issue_id", "body"),
        aliases={
            "issue_id": ("이슈", "issue", "이슈ID"),
            "body": ("코멘트", "댓글", "내용", "본문"),
        },
        validation_rules={
            "issue_id": {"type": "string", "pattern": LINEAR_ID_PATTERN},
            "body": {"type": "string", "min_length": 1, "max_length": 4000},
        },
    ),
}


def _to_string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def _to_alias_map(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for key, aliases in value.items():
        slot_name = str(key or "").strip()
        if not slot_name:
            continue
        out[slot_name] = _to_string_tuple(aliases)
    return out


def _to_validation_rules(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, rule in value.items():
        slot_name = str(key or "").strip()
        if not slot_name or not isinstance(rule, dict):
            continue
        out[slot_name] = dict(rule)
    return out


def _parse_external_schema(action: str, payload: Any) -> ActionSlotSchema | None:
    if not isinstance(payload, dict):
        return None
    action_name = str(payload.get("action") or action).strip()
    if not action_name:
        return None
    return ActionSlotSchema(
        action=action_name,
        required_slots=_to_string_tuple(payload.get("required_slots")),
        optional_slots=_to_string_tuple(payload.get("optional_slots")),
        auto_fill_slots=_to_string_tuple(payload.get("auto_fill_slots")),
        ask_order=_to_string_tuple(payload.get("ask_order")),
        aliases=_to_alias_map(payload.get("aliases")),
        validation_rules=_to_validation_rules(payload.get("validation_rules")),
    )


def _load_external_action_slot_schemas(path: str) -> dict[str, ActionSlotSchema]:
    text_path = str(path or "").strip()
    if not text_path:
        return {}
    try:
        payload = json.loads(Path(text_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("slot_schema_path_not_found path=%s", text_path)
        return {}
    except Exception as exc:
        logger.warning("slot_schema_path_load_failed path=%s err=%s", text_path, exc)
        return {}
    if not isinstance(payload, dict):
        return {}

    external: dict[str, ActionSlotSchema] = {}
    for action, schema_payload in payload.items():
        action_name = str(action or "").strip()
        if not action_name:
            continue
        parsed = _parse_external_schema(action_name, schema_payload)
        if not parsed:
            continue
        external[action_name] = parsed
    return external


@lru_cache(maxsize=1)
def _merged_action_slot_schemas() -> dict[str, ActionSlotSchema]:
    merged = dict(ACTION_SLOT_SCHEMAS)
    slot_schema_path = str(getattr(get_settings(), "slot_schema_path", "") or "").strip()
    if slot_schema_path:
        merged.update(_load_external_action_slot_schemas(slot_schema_path))
    return merged


def get_action_slot_schema(action: str) -> ActionSlotSchema | None:
    return _merged_action_slot_schemas().get((action or "").strip())


def list_action_slot_schemas() -> list[ActionSlotSchema]:
    return list(_merged_action_slot_schemas().values())


def normalize_slots(action: str, collected_slots: dict[str, Any]) -> dict[str, Any]:
    schema = get_action_slot_schema(action)
    if not schema:
        return dict(collected_slots)

    alias_to_slot: dict[str, str] = {}
    for slot_name, aliases in schema.aliases.items():
        for alias in aliases:
            alias_to_slot[alias.strip().lower()] = slot_name

    normalized: dict[str, Any] = {}
    for key, value in (collected_slots or {}).items():
        raw_key = str(key).strip()
        canonical = alias_to_slot.get(raw_key.lower(), raw_key)
        # explicit canonical key has precedence over alias values
        if canonical in normalized and raw_key != canonical:
            continue
        normalized[canonical] = value
    return normalized


def validate_slots(action: str, collected_slots: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    schema = get_action_slot_schema(action)
    normalized = normalize_slots(action, collected_slots)
    if not schema:
        return normalized, [], []

    missing = [name for name in schema.required_slots if _is_missing(normalized.get(name))]
    if missing and schema.ask_order:
        priority = {slot: idx for idx, slot in enumerate(schema.ask_order)}
        missing.sort(key=lambda slot: priority.get(slot, 999))
    errors: list[str] = []
    for slot_name, rule in schema.validation_rules.items():
        value = normalized.get(slot_name)
        if _is_missing(value):
            continue
        error = _validate_single_slot(slot_name=slot_name, value=value, rule=rule)
        if error:
            errors.append(error)
    return normalized, missing, errors


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _validate_single_slot(*, slot_name: str, value: Any, rule: dict[str, Any]) -> str | None:
    value_type = str(rule.get("type", "")).strip().lower()

    if value_type == "string":
        if not isinstance(value, str):
            return f"{slot_name}:type:string"
        min_length = rule.get("min_length")
        if isinstance(min_length, int) and len(value) < min_length:
            return f"{slot_name}:min_length:{min_length}"
        max_length = rule.get("max_length")
        if isinstance(max_length, int) and len(value) > max_length:
            return f"{slot_name}:max_length:{max_length}"
        pattern = rule.get("pattern")
        if isinstance(pattern, str) and not re.match(pattern, value):
            return f"{slot_name}:pattern"
    elif value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{slot_name}:type:integer"
        min_value = rule.get("min")
        if isinstance(min_value, int) and value < min_value:
            return f"{slot_name}:min:{min_value}"
        max_value = rule.get("max")
        if isinstance(max_value, int) and value > max_value:
            return f"{slot_name}:max:{max_value}"
    elif value_type == "boolean":
        if not isinstance(value, bool):
            return f"{slot_name}:type:boolean"

    enum_values = rule.get("enum")
    if isinstance(enum_values, (tuple, list)) and value not in enum_values:
        return f"{slot_name}:enum"

    return None
