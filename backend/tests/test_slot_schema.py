import json

import agent.slot_schema as slot_schema_module
from agent.slot_schema import (
    get_action_slot_schema,
    list_action_slot_schemas,
    normalize_slots,
    validate_slots,
)


def test_slot_schema_has_required_sections():
    schemas = list_action_slot_schemas()
    assert schemas
    for schema in schemas:
        assert schema.action
        assert isinstance(schema.required_slots, tuple)
        assert isinstance(schema.optional_slots, tuple)
        assert isinstance(schema.auto_fill_slots, tuple)
        assert isinstance(schema.ask_order, tuple)
        assert isinstance(schema.aliases, dict)
        assert isinstance(schema.validation_rules, dict)


def test_normalize_slots_resolves_alias_and_preserves_canonical_priority():
    normalized = normalize_slots(
        "notion_create_page",
        {
            "제목": "Alias Title",
            "title": "Canonical Title",
            "상위페이지": "123456781234123412341234567890ab",
        },
    )
    assert normalized["title"] == "Canonical Title"
    assert normalized["parent_page_id"] == "123456781234123412341234567890ab"


def test_validate_slots_returns_missing_and_validation_errors():
    normalized, missing, errors = validate_slots("linear_create_issue", {"팀": "team_a"})
    assert normalized["team_id"] == "team_a"
    assert "title" in missing
    assert not errors

    _, _, errors2 = validate_slots(
        "linear_create_issue",
        {"title": "x", "team_id": "team_a", "priority": 9},
    )
    assert "priority:enum" in errors2


def test_validate_slots_handles_unknown_action_as_noop():
    normalized, missing, errors = validate_slots("unknown_action", {"k": "v"})
    assert normalized == {"k": "v"}
    assert missing == []
    assert errors == []


def test_data_source_id_pattern_validation():
    _, missing, errors = validate_slots(
        "notion_query_data_source",
        {"data_source_id": "invalid-id"},
    )
    assert not missing
    assert "data_source_id:pattern" in errors

    _, missing2, errors2 = validate_slots(
        "notion_query_data_source",
        {"data_source_id": "12345678-1234-1234-1234-1234567890ab"},
    )
    assert not missing2
    assert errors2 == []


def test_get_action_slot_schema():
    schema = get_action_slot_schema("notion_search")
    assert schema is not None
    assert "query" in schema.optional_slots


def test_validate_slots_missing_order_follows_ask_order():
    _, missing, _ = validate_slots("linear_create_issue", {})
    assert missing == ["title", "team_id"]


def test_slot_schema_supports_external_override(monkeypatch, tmp_path):
    path = tmp_path / "slot_schemas.json"
    path.write_text(
        json.dumps(
            {
                "mockdocs_list_items": {
                    "required_slots": ["query"],
                    "optional_slots": ["limit"],
                    "auto_fill_slots": [],
                    "ask_order": ["query"],
                    "aliases": {
                        "query": ["검색어"],
                        "limit": ["개수"],
                    },
                    "validation_rules": {
                        "query": {"type": "string", "min_length": 1},
                        "limit": {"type": "integer", "min": 1, "max": 50},
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _Settings:
        slot_schema_path = str(path)

    monkeypatch.setattr("agent.slot_schema.get_settings", lambda: _Settings())
    slot_schema_module._merged_action_slot_schemas.cache_clear()
    schema = get_action_slot_schema("mockdocs_list_items")
    assert schema is not None
    assert schema.required_slots == ("query",)

    normalized, missing, errors = validate_slots("mockdocs_list_items", {"검색어": "hello", "개수": 3})
    assert normalized["query"] == "hello"
    assert normalized["limit"] == 3
    assert missing == []
    assert errors == []
    slot_schema_module._merged_action_slot_schemas.cache_clear()
