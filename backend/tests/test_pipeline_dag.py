import asyncio

import pytest

from agent.pipeline_dag import (
    PipelineExecutionError,
    evaluate_when,
    execute_pipeline_dag,
    resolve_ref,
    validate_pipeline_dsl,
)
from agent.pipeline_error_codes import PipelineErrorCode


def _base_pipeline() -> dict:
    return {
        "pipeline_id": "p1",
        "version": "1.0",
        "limits": {
            "max_nodes": 6,
            "max_fanout": 50,
            "max_tool_calls": 200,
            "pipeline_timeout_sec": 300,
        },
        "nodes": [],
    }


def test_validate_pipeline_dsl_rejects_cycle():
    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": ["n2"], "input": {}, "timeout_sec": 20},
        {"id": "n2", "type": "skill", "name": "notion.page_create", "depends_on": ["n1"], "input": {}, "timeout_sec": 20},
    ]
    errors = validate_pipeline_dsl(pipeline)
    assert "cycle_detected" in errors


def test_resolve_ref_supports_node_item_ctx_paths():
    artifacts = {"n1": {"events": [{"id": "evt-1"}]}}
    assert resolve_ref("$n1.events[0].id", artifacts=artifacts) == "evt-1"
    assert resolve_ref("$item.title", artifacts=artifacts, item={"title": "회의"}) == "회의"
    assert resolve_ref("$ctx.enabled", artifacts=artifacts, ctx={"enabled": True}) is True


def test_evaluate_when_supports_in_operator():
    artifacts = {"n1": {"state": "todo"}}
    assert evaluate_when('$n1.state in ["todo","in_progress"]', artifacts=artifacts) is True
    assert evaluate_when('$n1.state == "done"', artifacts=artifacts) is False


def test_evaluate_when_supports_right_hand_ref():
    artifacts = {"n1": {"count": 2}, "n2": {"count": 2}}
    assert evaluate_when("$n1.count == $n2.count", artifacts=artifacts) is True
    artifacts["n2"]["count"] = 3
    assert evaluate_when("$n1.count == $n2.count", artifacts=artifacts) is False


def test_execute_pipeline_dag_skill_chain():
    calls: list[tuple[str, dict]] = []

    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        calls.append((skill_name, payload))
        if skill_name == "google_calendar.list_today":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "daily"}]}}
        if skill_name == "notion.page_create":
            assert payload["title"] == "daily"
            return {"ok": True, "data": {"page_id": "pg-1"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, output_schema)
        return {"title": payload["title"]}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "llm_transform",
            "name": "transform",
            "depends_on": ["n1"],
            "input": {"title": "$n1.events[0].title"},
            "output_schema": {"type": "object"},
            "timeout_sec": 20,
        },
        {
            "id": "n3",
            "type": "skill",
            "name": "notion.page_create",
            "depends_on": ["n2"],
            "input": {"title": "$n2.title"},
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={"enabled": True},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert calls[0][0] == "google_calendar.list_today"
    assert calls[1][0] == "notion.page_create"
    assert result["artifacts"]["n3"]["page_id"] == "pg-1"


def test_execute_pipeline_dag_for_each_with_verify():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = user_id
        if skill_name == "google_calendar.list_today":
            return {
                "ok": True,
                "data": {"events": [{"id": "evt-1", "title": "daily"}, {"id": "evt-2", "title": "retro"}]},
            }
        if skill_name == "notion.page_create":
            return {"ok": True, "data": {"page_id": f"pg-{payload['title']}"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, output_schema)
        return {"title": payload["event_title"]}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "for_each",
            "name": "loop_events",
            "depends_on": ["n1"],
            "input": {},
            "source_ref": "$n1.events",
            "item_node_ids": ["n2_1", "n2_2"],
            "timeout_sec": 20,
        },
        {
            "id": "n2_1",
            "type": "llm_transform",
            "name": "transform",
            "depends_on": ["n2"],
            "input": {"event_title": "$item.title"},
            "output_schema": {"type": "object"},
            "timeout_sec": 20,
        },
        {
            "id": "n2_2",
            "type": "skill",
            "name": "notion.page_create",
            "depends_on": ["n2_1"],
            "input": {"title": "$n2_1.title"},
            "timeout_sec": 20,
        },
        {
            "id": "n3",
            "type": "verify",
            "name": "count_verify",
            "depends_on": ["n2"],
            "input": {},
            "rules": ["$n2.item_count == 2"],
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert result["artifacts"]["n2"]["item_count"] == 2
    assert len(result["artifacts"]["n2"]["item_results"]) == 2


def test_execute_pipeline_dag_aggregate_calendar_todo():
    calls: list[tuple[str, dict]] = []

    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((skill_name, payload))
        if skill_name == "google_calendar.list_today":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "Daily Standup", "description": "팀 상태 공유"},
                        {"id": "evt-2", "title": "Sprint Planning", "description": "스프린트 계획"},
                    ],
                    "event_count": 2,
                },
            }
        if skill_name == "notion.page_create":
            assert "todo_items" in payload
            assert payload["todo_items"] == ["Daily Standup", "Sprint Planning"]
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "aggregate",
            "name": "aggregate_calendar_events_to_todo",
            "depends_on": ["n1"],
            "input": {"mode": "calendar_todo"},
            "source_ref": "$n1.events",
            "timeout_sec": 20,
        },
        {
            "id": "n3",
            "type": "skill",
            "name": "notion.page_create",
            "depends_on": ["n2"],
            "input": {"title": "$n2.page_title", "todo_items": "$n2.todo_items"},
            "timeout_sec": 20,
        },
        {
            "id": "n4",
            "type": "verify",
            "name": "count_verify",
            "depends_on": ["n2", "n3"],
            "input": {},
            "rules": ["$n2.todo_count == $n1.event_count"],
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={"user_timezone": "Asia/Seoul"},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert result["artifacts"]["n2"]["todo_count"] == 2
    assert calls[1][0] == "notion.page_create"


def test_execute_pipeline_dag_retries_llm_transform_autofill_failure():
    llm_calls = {"count": 0}

    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, skill_name, payload)
        return {"ok": True, "data": {"title": "회의"}}

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        llm_calls["count"] += 1
        if llm_calls["count"] < 3:
            return {}
        return {"title": "회의"}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "notion.page_search", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "llm_transform",
            "name": "transform",
            "depends_on": ["n1"],
            "input": {"title": "$n1.title"},
            "output_schema": {"type": "object", "required": ["title"]},
            "retry": {"max_attempts": 3, "backoff_ms": 0},
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert llm_calls["count"] == 3


def test_execute_pipeline_dag_raises_verify_mismatch():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, payload)
        if skill_name == "google_calendar.list_today":
            return {"ok": True, "data": {"events": [{"id": "evt-1"}]}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "verify",
            "name": "count_verify",
            "depends_on": ["n1"],
            "input": {},
            "rules": ["$n1.events[0].id == \"evt-2\""],
            "timeout_sec": 20,
        },
    ]

    with pytest.raises(PipelineExecutionError) as exc:
        asyncio.run(
            execute_pipeline_dag(
                user_id="u1",
                pipeline=pipeline,
                ctx={},
                execute_skill=_fake_skill,
                execute_llm_transform=_fake_transform,
            )
        )
    assert exc.value.code == PipelineErrorCode.VERIFY_COUNT_MISMATCH


def test_execute_pipeline_dag_reuses_duplicate_write_mutation():
    calls: list[tuple[str, dict]] = []

    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((skill_name, payload))
        if skill_name == "notion.page_create":
            return {"ok": True, "data": {"id": "page-1"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "notion.page_create", "depends_on": [], "input": {"title": "중복"}, "timeout_sec": 20},
        {"id": "n2", "type": "skill", "name": "notion.page_create", "depends_on": ["n1"], "input": {"title": "중복"}, "timeout_sec": 20},
    ]
    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert result["idempotent_success_reuse_count"] == 1
    write_runs = [row for row in result["node_runs"] if row["node_type"] == "skill"]
    assert write_runs
    assert write_runs[0].get("idempotency_key")


def test_execute_pipeline_dag_runs_compensation_on_item_failure():
    compensation_calls: list[tuple[str, str]] = []

    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = user_id
        if skill_name == "google.list_today":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if skill_name == "notion.page_create":
            return {"ok": True, "data": {"id": "page-1"}}
        if skill_name == "linear.issue_create":
            return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "linear_fail"}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, output_schema)
        return {"title": payload.get("title") or "회의"}

    async def _fake_comp(node_id: str, skill_name: str, output: dict, item: dict | None) -> bool:
        _ = (output, item)
        compensation_calls.append((node_id, skill_name))
        return True

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {"id": "n2", "type": "for_each", "name": "loop", "depends_on": ["n1"], "input": {}, "source_ref": "$n1.events", "item_node_ids": ["n2_1", "n2_2"], "timeout_sec": 20},
        {"id": "n2_1", "type": "skill", "name": "notion.page_create", "depends_on": ["n2"], "input": {"title": "$item.title"}, "timeout_sec": 20},
        {"id": "n2_2", "type": "skill", "name": "linear.issue_create", "depends_on": ["n2_1"], "input": {"title": "$item.title"}, "timeout_sec": 20},
    ]

    with pytest.raises(PipelineExecutionError) as exc:
        asyncio.run(
            execute_pipeline_dag(
                user_id="u1",
                pipeline=pipeline,
                ctx={},
                execute_skill=_fake_skill,
                execute_llm_transform=_fake_transform,
                execute_compensation=_fake_comp,
            )
        )
    assert exc.value.code == PipelineErrorCode.TOOL_TIMEOUT
    assert exc.value.compensation_status == "completed"
    assert compensation_calls == [("n2_1", "notion.page_create")]
    assert exc.value.pipeline_run_id


def test_execute_pipeline_dag_marks_compensation_failed():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, payload)
        if skill_name == "google.list_today":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if skill_name == "notion.page_create":
            return {"ok": True, "data": {"id": "page-1"}}
        if skill_name == "linear.issue_create":
            return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "linear_fail"}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    async def _fake_comp(node_id: str, skill_name: str, output: dict, item: dict | None) -> bool:
        _ = (node_id, skill_name, output, item)
        return False

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {"id": "n2", "type": "for_each", "name": "loop", "depends_on": ["n1"], "input": {}, "source_ref": "$n1.events", "item_node_ids": ["n2_1", "n2_2"], "timeout_sec": 20},
        {"id": "n2_1", "type": "skill", "name": "notion.page_create", "depends_on": ["n2"], "input": {"title": "$item.title"}, "timeout_sec": 20},
        {"id": "n2_2", "type": "skill", "name": "linear.issue_create", "depends_on": ["n2_1"], "input": {"title": "$item.title"}, "timeout_sec": 20},
    ]

    with pytest.raises(PipelineExecutionError) as exc:
        asyncio.run(
            execute_pipeline_dag(
                user_id="u1",
                pipeline=pipeline,
                ctx={},
                execute_skill=_fake_skill,
                execute_llm_transform=_fake_transform,
                execute_compensation=_fake_comp,
            )
        )
    assert exc.value.code == PipelineErrorCode.COMPENSATION_FAILED
    assert exc.value.compensation_status == "failed"
    assert exc.value.pipeline_run_id


def test_execute_pipeline_dag_maps_auth_required_to_tool_auth_error():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, skill_name, payload)
        return {
            "ok": False,
            "error_code": "AUTH_REQUIRED",
            "detail": "google_calendar_list_events:AUTH_REQUIRED",
        }

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
    ]

    with pytest.raises(PipelineExecutionError) as exc:
        asyncio.run(
            execute_pipeline_dag(
                user_id="u1",
                pipeline=pipeline,
                ctx={},
                execute_skill=_fake_skill,
                execute_llm_transform=_fake_transform,
            )
        )
    assert exc.value.code == PipelineErrorCode.TOOL_AUTH_ERROR


def test_execute_pipeline_dag_verify_on_fail_fallback_does_not_raise():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, skill_name, payload)
        return {"ok": True, "data": {"count": 1}}

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, payload, output_schema)
        return {}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "verify",
            "name": "verify_non_blocking",
            "depends_on": ["n1"],
            "input": {},
            "rules": ["$n1.count == 2"],
            "on_fail": "fallback",
            "timeout_sec": 20,
        },
    ]
    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert result["artifacts"]["n2"]["action"] == "fallback"


def test_execute_pipeline_dag_for_each_supports_items_ref_alias():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = (user_id, payload)
        if skill_name == "google_calendar.list_today":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if skill_name == "notion.page_create":
            return {"ok": True, "data": {"page_id": "pg-1"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, output_schema)
        return {"title": payload["event_title"]}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "for_each",
            "name": "loop_events",
            "depends_on": ["n1"],
            "input": {},
            "items_ref": "$n1.events",
            "item_node_ids": ["n2_1", "n2_2"],
            "timeout_sec": 20,
        },
        {
            "id": "n2_1",
            "type": "llm_transform",
            "name": "transform",
            "depends_on": ["n2"],
            "input": {"event_title": "$item.title"},
            "output_schema": {"type": "object"},
            "timeout_sec": 20,
        },
        {
            "id": "n2_2",
            "type": "skill",
            "name": "notion.page_create",
            "depends_on": ["n2_1"],
            "input": {"title": "$n2_1.title"},
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert result["artifacts"]["n2"]["item_count"] == 1


def test_execute_pipeline_dag_for_each_skip_item_failure():
    async def _fake_skill(user_id: str, skill_name: str, payload: dict) -> dict:
        _ = user_id
        if skill_name == "google_calendar.list_today":
            return {
                "ok": True,
                "data": {"events": [{"id": "evt-1", "title": "ok"}, {"id": "evt-2", "title": "fail"}]},
            }
        if skill_name == "notion.page_create":
            if payload.get("title") == "fail":
                return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "forced_failure"}
            return {"ok": True, "data": {"id": f"page-{payload['title']}"}}
        raise AssertionError(f"unexpected skill {skill_name}")

    async def _fake_transform(user_id: str, payload: dict, output_schema: dict) -> dict:
        _ = (user_id, output_schema)
        return {"title": payload["event_title"]}

    pipeline = _base_pipeline()
    pipeline["nodes"] = [
        {"id": "n1", "type": "skill", "name": "google_calendar.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
        {
            "id": "n2",
            "type": "for_each",
            "name": "loop_events",
            "depends_on": ["n1"],
            "input": {},
            "source_ref": "$n1.events",
            "item_node_ids": ["n2_1", "n2_2"],
            "on_item_fail": "skip",
            "timeout_sec": 20,
        },
        {
            "id": "n2_1",
            "type": "llm_transform",
            "name": "transform",
            "depends_on": ["n2"],
            "input": {"event_title": "$item.title"},
            "output_schema": {"type": "object", "required": ["title"]},
            "timeout_sec": 20,
        },
        {
            "id": "n2_2",
            "type": "skill",
            "name": "notion.page_create",
            "depends_on": ["n2_1"],
            "input": {"title": "$n2_1.title"},
            "timeout_sec": 20,
        },
    ]

    result = asyncio.run(
        execute_pipeline_dag(
            user_id="u1",
            pipeline=pipeline,
            ctx={},
            execute_skill=_fake_skill,
            execute_llm_transform=_fake_transform,
        )
    )
    assert result["status"] == "succeeded"
    assert result["artifacts"]["n2"]["item_count"] == 2
    assert result["artifacts"]["n2"]["item_error_count"] == 1
