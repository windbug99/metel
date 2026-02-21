from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionSlotSchema:
    action: str
    required_slots: tuple[str, ...]
    optional_slots: tuple[str, ...]
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
        required_slots=("query",),
        optional_slots=("page_size",),
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
        required_slots=("query",),
        optional_slots=("first", "team_id"),
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


def get_action_slot_schema(action: str) -> ActionSlotSchema | None:
    return ACTION_SLOT_SCHEMAS.get((action or "").strip())


def list_action_slot_schemas() -> list[ActionSlotSchema]:
    return list(ACTION_SLOT_SCHEMAS.values())


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
