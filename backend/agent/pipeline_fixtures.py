from __future__ import annotations

from agent import intent_normalizer


def build_google_calendar_to_notion_linear_pipeline(*, user_text: str) -> dict:
    linear_team_ref = intent_normalizer.extract_linear_team_reference(user_text)
    return {
        "pipeline_id": "google_calendar_to_notion_linear_v1",
        "version": "1.0",
        "limits": {
            "max_nodes": 6,
            "max_fanout": 50,
            "max_tool_calls": 200,
            "pipeline_timeout_sec": 300,
        },
        "nodes": [
            {
                "id": "n1",
                "type": "skill",
                "name": "google.list_today",
                "depends_on": [],
                "input": {"calendar_id": "primary", "max_results": 50},
                "when": "$ctx.enabled == true",
                "retry": {"max_attempts": 2, "backoff_ms": 500},
                "timeout_sec": 45,
            },
            {
                "id": "n2",
                "type": "for_each",
                "name": "fanout_events",
                "depends_on": ["n1"],
                "input": {},
                "source_ref": "$n1.events",
                "item_node_ids": ["n2_1", "n2_2", "n2_3"],
                "timeout_sec": 60,
            },
            {
                "id": "n2_1",
                "type": "llm_transform",
                "name": "event_to_payload",
                "depends_on": ["n2"],
                "input": {
                    "event_id": "$item.id",
                    "notion_title": "$item.title",
                    "notion_body": "$item.description",
                    "linear_title": "$item.title",
                    "linear_description": "$item.description",
                },
                "output_schema": {
                    "type": "object",
                    "required": ["event_id", "notion_title", "linear_title"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "notion_title": {"type": "string"},
                        "notion_body": {"type": ["string", "null"]},
                        "linear_title": {"type": "string"},
                        "linear_description": {"type": ["string", "null"]},
                    },
                    "additionalProperties": True,
                },
                "retry": {"max_attempts": 2, "backoff_ms": 200},
                "timeout_sec": 30,
            },
            {
                "id": "n2_2",
                "type": "skill",
                "name": "notion.page_create",
                "depends_on": ["n2_1"],
                "input": {
                    "title": "$n2_1.notion_title",
                    "body": "$n2_1.notion_body",
                },
                "retry": {"max_attempts": 2, "backoff_ms": 500},
                "timeout_sec": 45,
            },
            {
                "id": "n2_3",
                "type": "skill",
                "name": "linear.issue_create",
                "depends_on": ["n2_1", "n2_2"],
                "input": {
                    "team_ref": linear_team_ref or "",
                    "title": "$n2_1.linear_title",
                    "description": "$n2_1.linear_description",
                },
                "retry": {"max_attempts": 2, "backoff_ms": 500},
                "timeout_sec": 45,
            },
            {
                "id": "n3",
                "type": "verify",
                "name": "verify_counts",
                "depends_on": ["n2"],
                "input": {},
                "rules": ["$n2.item_count >= 0"],
                "timeout_sec": 30,
            },
        ],
    }


def build_google_calendar_to_notion_todo_pipeline(*, user_text: str) -> dict:
    _ = user_text
    return {
        "pipeline_id": "google_calendar_to_notion_todo_v1",
        "version": "1.0",
        "limits": {
            "max_nodes": 5,
            "max_fanout": 50,
            "max_tool_calls": 120,
            "pipeline_timeout_sec": 240,
        },
        "nodes": [
            {
                "id": "n1",
                "type": "skill",
                "name": "google.list_today",
                "depends_on": [],
                "input": {"calendar_id": "primary", "max_results": 50},
                "when": "$ctx.enabled == true",
                "retry": {"max_attempts": 2, "backoff_ms": 500},
                "timeout_sec": 45,
            },
            {
                "id": "n2",
                "type": "aggregate",
                "name": "aggregate_calendar_events_to_todo",
                "depends_on": ["n1"],
                "input": {"mode": "calendar_todo", "page_title_suffix": " 일정 할일 목록"},
                "source_ref": "$n1.events",
                "timeout_sec": 60,
            },
            {
                "id": "n3",
                "type": "skill",
                "name": "notion.page_create",
                "depends_on": ["n2"],
                "input": {
                    "title": "$n2.page_title",
                    "body": "$n2.body",
                    "todo_items": "$n2.todo_items",
                    "todo_intro": "Google Calendar 오늘 일정 기반 체크리스트",
                },
                "retry": {"max_attempts": 2, "backoff_ms": 500},
                "timeout_sec": 45,
            },
            {
                "id": "n4",
                "type": "verify",
                "name": "verify_counts",
                "depends_on": ["n2", "n3"],
                "input": {},
                "rules": ["$n2.todo_count == $n1.event_count"],
                "timeout_sec": 30,
            },
        ],
    }
