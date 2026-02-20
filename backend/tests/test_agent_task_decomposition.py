import asyncio

from agent.executor import execute_agent_plan
from agent.planner import build_agent_plan
from agent.types import AgentPlan, AgentRequirement, AgentTask


def test_build_agent_plan_includes_llm_task_for_cross_service_summary_flow():
    plan = build_agent_plan(
        "Linear의 기획관련 이슈를 찾아서 3문장으로 요약해 Notion의 새로운 페이지에 생성해서 저장하세요",
        connected_services=["linear", "notion"],
    )

    task_types = [task.task_type for task in plan.tasks]
    assert "LLM" in task_types
    assert task_types.count("TOOL") >= 2

    linear_task = next((task for task in plan.tasks if task.service == "linear"), None)
    notion_task = next((task for task in plan.tasks if task.service == "notion"), None)
    llm_task = next((task for task in plan.tasks if task.task_type == "LLM"), None)

    assert linear_task is not None
    assert notion_task is not None
    assert llm_task is not None
    assert llm_task.payload.get("sentences") == 3


def test_build_agent_plan_maps_register_intent_to_linear_create_issue():
    plan = build_agent_plan(
        "노션의 구글로그인 구현 페이지를 linear의 새로운 이슈로 등록하세요.",
        connected_services=["notion", "linear"],
    )

    assert any("생성" in req.summary for req in plan.requirements)
    assert any(task.tool_name == "linear_create_issue" for task in plan.tasks)
    assert not any(task.tool_name == "notion_create_page" for task in plan.tasks)


def test_execute_agent_plan_runs_linear_llm_notion_bridge(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "linear_search_issues":
            return {
                "ok": True,
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "i-1",
                                "identifier": "MET-101",
                                "title": "기획 요구사항 정리",
                                "url": "https://linear.app/issue/MET-101",
                                "state": {"name": "Todo"},
                            },
                            {
                                "id": "i-2",
                                "identifier": "MET-102",
                                "title": "기획 리뷰 일정 조율",
                                "url": "https://linear.app/issue/MET-102",
                                "state": {"name": "In Progress"},
                            },
                        ]
                    }
                },
            }
        if tool_name == "notion_create_page":
            assert payload.get("children")
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_summarize_text_with_llm(text: str, user_text: str):
        _ = (text, user_text)
        return "기획 이슈가 정리되었습니다. 우선순위와 리뷰 일정이 포함됩니다. 다음 액션이 명확합니다.", "mock"

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._summarize_text_with_llm", _fake_summarize_text_with_llm)

    plan = AgentPlan(
        user_text="Linear의 기획관련 이슈를 찾아서 3문장으로 요약해 Notion 페이지에 저장",
        requirements=[
            AgentRequirement(summary="대상 데이터 조회"),
            AgentRequirement(summary="대상 콘텐츠 요약", quantity=3),
            AgentRequirement(summary="결과물 생성", quantity=1),
        ],
        target_services=["linear", "notion"],
        selected_tools=["linear_search_issues", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_linear_issues",
                title="Linear 이슈 조회",
                task_type="TOOL",
                service="linear",
                tool_name="linear_search_issues",
                payload={"query": "기획", "first": 5},
            ),
            AgentTask(
                id="task_llm_summary",
                title="3문장 요약",
                task_type="LLM",
                depends_on=["task_linear_issues"],
                payload={"sentences": 3},
                instruction="3문장 요약",
            ),
            AgentTask(
                id="task_notion_create_page",
                title="Notion 저장",
                task_type="TOOL",
                service="notion",
                tool_name="notion_create_page",
                depends_on=["task_llm_summary"],
                payload={"title_hint": "기획 이슈 요약"},
            ),
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "오케스트레이션" in result.summary
    assert calls[0][0] == "linear_search_issues"
    assert calls[1][0] == "notion_create_page"
    assert result.artifacts.get("created_page_url") == "https://notion.so/page-1"


def test_build_agent_plan_includes_notion_data_source_task_for_summary_creation():
    plan = build_agent_plan(
        "노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 5개를 요약해서 새 페이지로 저장",
        connected_services=["notion"],
    )

    task_ids = [task.id for task in plan.tasks]
    assert "task_notion_data_source_query" in task_ids
    assert "task_llm_summary" in task_ids
    assert "task_notion_create_page" in task_ids

    query_task = next(task for task in plan.tasks if task.id == "task_notion_data_source_query")
    assert query_task.tool_name == "notion_query_data_source"
    assert query_task.payload["data_source_id"] == "12345678-1234-1234-1234-1234567890ab"


def test_execute_agent_plan_runs_notion_data_source_llm_notion_bridge(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_query_data_source":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "page-a",
                            "url": "https://notion.so/page-a",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "요구사항 정리"}]}},
                        },
                        {
                            "id": "page-b",
                            "url": "https://notion.so/page-b",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "일정 계획"}]}},
                        },
                    ]
                },
            }
        if tool_name == "notion_create_page":
            assert payload.get("children")
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_summarize_text_with_llm(text: str, user_text: str):
        _ = (text, user_text)
        return "핵심 항목이 정리되었습니다. 일정과 우선순위가 포함됩니다. 다음 액션이 명확합니다.", "mock"

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._summarize_text_with_llm", _fake_summarize_text_with_llm)

    plan = AgentPlan(
        user_text="노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 5개 요약 후 페이지 생성",
        requirements=[
            AgentRequirement(summary="데이터소스 질의", quantity=5),
            AgentRequirement(summary="대상 콘텐츠 요약", quantity=3),
            AgentRequirement(summary="결과물 생성", quantity=1),
        ],
        target_services=["notion"],
        selected_tools=["notion_query_data_source", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_notion_data_source_query",
                title="Notion 데이터소스 조회",
                task_type="TOOL",
                service="notion",
                tool_name="notion_query_data_source",
                payload={"data_source_id": "12345678-1234-1234-1234-1234567890ab", "page_size": 5},
            ),
            AgentTask(
                id="task_llm_summary",
                title="3문장 요약",
                task_type="LLM",
                depends_on=["task_notion_data_source_query"],
                payload={"sentences": 3},
            ),
            AgentTask(
                id="task_notion_create_page",
                title="Notion 저장",
                task_type="TOOL",
                service="notion",
                tool_name="notion_create_page",
                depends_on=["task_llm_summary"],
                payload={"title_hint": "데이터소스 요약"},
            ),
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "오케스트레이션" in result.summary
    assert calls[0][0] == "notion_query_data_source"
    assert calls[1][0] == "notion_create_page"
    assert result.artifacts.get("created_page_url") == "https://notion.so/page-1"
