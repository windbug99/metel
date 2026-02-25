import asyncio

from agent.executor import execute_agent_plan
from agent.pipeline_error_codes import PipelineErrorCode
from agent.types import AgentPlan, AgentRequirement, AgentTask


def _build_dag_plan(pipeline: dict) -> AgentPlan:
    return AgentPlan(
        user_text="dag 실행",
        requirements=[AgentRequirement(summary="dag_run")],
        target_services=["notion"],
        selected_tools=["notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag",
                title="pipeline dag",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )


def test_execute_agent_plan_runs_pipeline_dag_task(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        return {"ok": True, "data": {"id": "page-1"}}

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor.persist_pipeline_links", lambda *, links: True)

    pipeline = {
        "pipeline_id": "p1",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {
                "id": "n1",
                "type": "skill",
                "name": "notion.page_create",
                "depends_on": [],
                "input": {"title": "회의록"},
                "timeout_sec": 20,
            }
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))

    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    assert result.artifacts.get("router_mode") == "PIPELINE_DAG"
    assert result.artifacts.get("pipeline_run_id")
    assert "dag_node_runs_json" in result.artifacts
    assert calls[0][0] == "notion_create_page"


def test_execute_agent_plan_pipeline_dag_failure_contract(monkeypatch):
    persisted_failure: dict[str, object] = {}

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = (user_id, tool_name, payload)
        return {"ok": True, "data": {"events": [{"id": "evt-1"}]}}

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor.persist_pipeline_links", lambda *, links: True)
    monkeypatch.setattr("agent.executor.persist_pipeline_failure_link", lambda **kwargs: persisted_failure.update(kwargs) or True)

    pipeline = {
        "pipeline_id": "p2",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {
                "id": "n1",
                "type": "skill",
                "name": "notion.page_search",
                "depends_on": [],
                "input": {},
                "timeout_sec": 20,
            },
            {
                "id": "n2",
                "type": "verify",
                "name": "verify",
                "depends_on": ["n1"],
                "input": {},
                "rules": ["$n1.events[0].id == \"evt-2\""],
                "timeout_sec": 20,
            },
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))

    assert result.success is False
    assert result.artifacts.get("error_code") == "VERIFY_COUNT_MISMATCH"
    assert "failed_step" in result.artifacts
    assert "reason" in result.artifacts
    assert "retry_hint" in result.artifacts
    assert "compensation_status" in result.artifacts
    assert result.artifacts.get("pipeline_links_failure_persisted") == "1"
    assert result.artifacts.get("pipeline_links_failure_status") == "failed"
    assert persisted_failure.get("error_code") == "VERIFY_COUNT_MISMATCH"
    assert persisted_failure.get("compensation_status") == "not_required"


def test_execute_agent_plan_pipeline_dag_sets_compensation_status_completed(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "linear_create_issue":
            return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "linear_fail"}
        if tool_name == "notion_update_page":
            return {"ok": True, "data": {"id": "page-1", "archived": True}}
        raise AssertionError(f"unexpected tool {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor.persist_pipeline_links", lambda *, links: True)
    monkeypatch.setattr("agent.executor.persist_pipeline_failure_link", lambda **kwargs: True)

    pipeline = {
        "pipeline_id": "p3",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
            {
                "id": "n2",
                "type": "for_each",
                "name": "loop",
                "depends_on": ["n1"],
                "input": {},
                "source_ref": "$n1.events",
                "item_node_ids": ["n2_1", "n2_2"],
                "timeout_sec": 20,
            },
            {"id": "n2_1", "type": "skill", "name": "notion.page_create", "depends_on": ["n2"], "input": {"title": "$item.title"}, "timeout_sec": 20},
            {"id": "n2_2", "type": "skill", "name": "linear.issue_create", "depends_on": ["n2_1"], "input": {"title": "$item.title"}, "timeout_sec": 20},
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))

    assert result.success is False
    assert result.artifacts.get("compensation_status") == "completed"
    assert result.artifacts.get("pipeline_links_failure_status") == "failed"
    assert [name for name, _ in calls].count("notion_update_page") == 1


def test_execute_agent_plan_pipeline_persists_pipeline_links(monkeypatch):
    calls: list[tuple[str, dict]] = []
    persisted: dict[str, object] = {"count": 0, "rows": []}

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "linear_create_issue":
            return {"ok": True, "data": {"issueCreate": {"issue": {"id": "issue-1"}}}}
        raise AssertionError(f"unexpected tool {tool_name}")

    def _fake_persist(*, links):
        persisted["count"] = len(links)
        persisted["rows"] = links
        return True

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor.persist_pipeline_links", _fake_persist)
    monkeypatch.setattr("agent.executor.persist_pipeline_failure_link", lambda **kwargs: True)

    pipeline = {
        "pipeline_id": "p4",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
            {"id": "n2", "type": "for_each", "name": "loop", "depends_on": ["n1"], "input": {}, "source_ref": "$n1.events", "item_node_ids": ["n2_1", "n2_2", "n2_3"], "timeout_sec": 20},
            {"id": "n2_1", "type": "llm_transform", "name": "tf", "depends_on": ["n2"], "input": {"event_id": "$item.id", "notion_title": "$item.title", "linear_title": "$item.title"}, "output_schema": {"type": "object", "required": ["event_id", "notion_title", "linear_title"]}, "timeout_sec": 20},
            {"id": "n2_2", "type": "skill", "name": "notion.page_create", "depends_on": ["n2_1"], "input": {"title": "$n2_1.notion_title"}, "timeout_sec": 20},
            {"id": "n2_3", "type": "skill", "name": "linear.issue_create", "depends_on": ["n2_1", "n2_2"], "input": {"title": "$n2_1.linear_title"}, "timeout_sec": 20},
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))

    assert result.success is True
    assert persisted["count"] == 1
    assert result.artifacts.get("pipeline_links_count") == "1"
    assert result.artifacts.get("pipeline_links_persisted") == "1"


def test_execute_agent_plan_pipeline_dag_marks_manual_required_failure_status(monkeypatch):
    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        if tool_name == "google_calendar_list_events":
            return {"ok": True, "data": {"events": [{"id": "evt-1", "title": "회의"}]}}
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "linear_create_issue":
            return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "linear_fail"}
        if tool_name == "notion_update_page":
            return {"ok": False, "error_code": "TOOL_TIMEOUT", "detail": "comp_fail"}
        raise AssertionError(f"unexpected tool {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor.persist_pipeline_links", lambda *, links: True)
    monkeypatch.setattr("agent.executor.persist_pipeline_failure_link", lambda **kwargs: True)

    pipeline = {
        "pipeline_id": "p5",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {"id": "n1", "type": "skill", "name": "google.list_today", "depends_on": [], "input": {}, "timeout_sec": 20},
            {"id": "n2", "type": "for_each", "name": "loop", "depends_on": ["n1"], "input": {}, "source_ref": "$n1.events", "item_node_ids": ["n2_1", "n2_2"], "timeout_sec": 20},
            {"id": "n2_1", "type": "skill", "name": "notion.page_create", "depends_on": ["n2"], "input": {"title": "$item.title"}, "timeout_sec": 20},
            {"id": "n2_2", "type": "skill", "name": "linear.issue_create", "depends_on": ["n2_1"], "input": {"title": "$item.title"}, "timeout_sec": 20},
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))
    assert result.success is False
    assert result.artifacts.get("compensation_status") == "failed"
    assert result.artifacts.get("pipeline_links_failure_status") == "manual_required"


def test_execute_agent_plan_pipeline_dag_policy_guard_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "agent.executor._validate_dag_policy_guards",
        lambda **kwargs: (False, "oauth_scope_missing:notion", "n1", PipelineErrorCode.TOOL_AUTH_ERROR),
    )

    pipeline = {
        "pipeline_id": "p6",
        "version": "1.0",
        "limits": {"max_nodes": 6, "max_fanout": 50, "max_tool_calls": 200, "pipeline_timeout_sec": 300},
        "nodes": [
            {"id": "n1", "type": "skill", "name": "notion.page_create", "depends_on": [], "input": {"title": "회의록"}, "timeout_sec": 20}
        ],
    }
    result = asyncio.run(execute_agent_plan("u1", _build_dag_plan(pipeline)))
    assert result.success is False
    assert result.artifacts.get("error_code") == "TOOL_AUTH_ERROR"
    assert result.artifacts.get("failed_step") == "n1"
