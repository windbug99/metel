import asyncio

from agent.executor import execute_agent_plan
from agent.pipeline_fixtures import build_google_calendar_to_notion_linear_pipeline
from agent.types import AgentPlan, AgentRequirement, AgentTask


def _build_plan_from_fixture(user_text: str) -> AgentPlan:
    pipeline = build_google_calendar_to_notion_linear_pipeline(user_text=user_text)
    return AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary="calendar_notion_linear_fixture")],
        target_services=["google", "notion", "linear"],
        selected_tools=["google_calendar_list_events", "notion_create_page", "linear_create_issue"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_fixture",
                title="fixture dag",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )


def test_google_calendar_to_notion_linear_fixture_e2e(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "Daily Standup", "description": "팀 상태 공유"},
                        {"id": "evt-2", "title": "Sprint Planning", "description": "다음 스프린트 계획"},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": f"page-{payload.get('title', '').lower().replace(' ', '-')}"}}
        if tool_name == "linear_create_issue":
            return {"ok": True, "data": {"issueCreate": {"success": True}}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    plan = _build_plan_from_fixture("구글캘린더 오늘 회의를 notion/linear로 등록")
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 2
    assert tool_names.count("linear_create_issue") == 2
