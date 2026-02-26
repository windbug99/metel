import asyncio

from agent.executor import execute_agent_plan
from agent.pipeline_fixtures import (
    build_google_calendar_to_linear_minutes_pipeline,
    build_google_calendar_to_notion_linear_pipeline,
    build_google_calendar_to_notion_minutes_pipeline,
    build_google_calendar_to_notion_todo_pipeline,
)
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


def test_google_calendar_to_notion_todo_fixture_e2e(monkeypatch):
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
            todo_items = payload.get("todo_items") or []
            assert todo_items == ["Daily Standup", "Sprint Planning"]
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_todo_pipeline(user_text="구글캘린더 오늘 일정을 노션 할일 목록으로 생성")
    plan = AgentPlan(
        user_text="구글캘린더 오늘 일정을 노션 할일 목록으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_todo_fixture")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_todo_fixture",
                title="fixture dag todo",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    assert result.artifacts.get("processed_count") == "2"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 1


def test_google_calendar_to_notion_minutes_fixture_e2e(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-2", "title": "점심 약속", "description": "사내 식당"},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture",
                title="fixture dag minutes",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    assert result.artifacts.get("processed_count") == "1"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 1


def test_google_calendar_to_notion_minutes_fixture_uses_llm_transform_when_available(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_request_autofill_json(*, system_prompt: str, user_prompt: str) -> dict | None:
        _ = (system_prompt, user_prompt)
        return {
            "title": "LLM 회의록 초안 - 주간 회의",
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": "회의 목적: LLM 생성 내용"},
                            }
                        ]
                    },
                }
            ],
        }

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._request_autofill_json", _fake_request_autofill_json)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture_llm_transform")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture_llm",
                title="fixture dag minutes llm",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    notion_payload = next(payload for name, payload in calls if name == "notion_create_page")
    title_node = (((notion_payload.get("properties") or {}).get("title") or {}).get("title") or [{}])[0]
    title_text = (((title_node or {}).get("text") or {}).get("content") or "").strip()
    assert title_text == "LLM 회의록 초안 - 주간 회의"


def test_google_calendar_to_notion_minutes_fixture_normalizes_llm_children_schema(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {"events": [{"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"}]},
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_request_autofill_json(*, system_prompt: str, user_prompt: str) -> dict | None:
        _ = (system_prompt, user_prompt)
        # Deliberately malformed children: not Notion block schema.
        return {
            "title": "LLM 회의록 초안 - 주간 회의",
            "children": [{"type": "paragraph", "text": "회의 목적: 스키마 보정 테스트"}],
        }

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._request_autofill_json", _fake_request_autofill_json)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture_llm_schema_normalize")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture_llm_schema_normalize",
                title="fixture dag minutes llm schema normalize",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    notion_payload = next(payload for name, payload in calls if name == "notion_create_page")
    children = notion_payload.get("children") or []
    assert isinstance(children, list) and children
    assert children[0].get("object") == "block"
    assert children[0].get("type") == "paragraph"
    paragraph = children[0].get("paragraph") or {}
    rich = paragraph.get("rich_text") or []
    assert isinstance(rich, list) and rich
    assert (((rich[0] or {}).get("text") or {}).get("content") or "").strip() != ""


def test_google_calendar_to_notion_minutes_fixture_n_events_create_n_pages(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-2", "title": "분기 회의", "description": "실적 리뷰"},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            idx = len([name for name, _ in calls if name == "notion_create_page"])
            return {"ok": True, "data": {"id": f"page-{idx}", "url": f"https://notion.so/page-{idx}"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture_n_to_n")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture_n_to_n",
                title="fixture dag minutes n_to_n",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.artifacts.get("processed_count") == "2"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 2


def test_google_calendar_to_notion_minutes_fixture_zero_meetings_success(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "점심 약속", "description": "사내 식당"},
                    ]
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture_zero")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture_zero",
                title="fixture dag minutes zero",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.artifacts.get("processed_count") == "0"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 0


def test_google_calendar_to_notion_minutes_fixture_dedupes_duplicate_event_writes(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            # Duplicate event id to simulate upstream duplication.
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-dup", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-dup", "title": "주간 회의", "description": "백로그 점검"},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-dup", "url": "https://notion.so/page-dup"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_notion_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성",
        requirements=[AgentRequirement(summary="calendar_notion_minutes_fixture_dedupe")],
        target_services=["google", "notion"],
        selected_tools=["google_calendar_list_events", "notion_create_page"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_minutes_fixture_dedupe",
                title="fixture dag minutes dedupe",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    tool_names = [name for name, _ in calls]
    # One google read, but duplicate write should be deduped by idempotency key.
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("notion_create_page") == 1


def test_google_calendar_to_linear_minutes_fixture_e2e(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-2", "title": "운동", "description": "헬스장"},
                    ]
                },
            }
        if tool_name == "linear_list_teams":
            return {"ok": True, "data": {"teams": {"nodes": [{"id": "team-1", "name": "Operate"}]}}}
        if tool_name == "linear_create_issue":
            assert "회의 목적:" in str(payload.get("description") or "")
            return {
                "ok": True,
                "data": {"issueCreate": {"issue": {"id": "iss-1", "url": "https://linear.app/issue/ISS-1"}}},
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_linear_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
        requirements=[AgentRequirement(summary="calendar_linear_minutes_fixture")],
        target_services=["google", "linear"],
        selected_tools=["google_calendar_list_events", "linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_linear_minutes_fixture",
                title="fixture dag linear minutes",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    assert result.artifacts.get("processed_count") == "1"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("linear_create_issue") == 1


def test_google_calendar_to_linear_minutes_fixture_zero_meetings_success(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "운동", "description": "헬스장"},
                    ]
                },
            }
        if tool_name == "linear_list_teams":
            return {"ok": True, "data": {"teams": {"nodes": [{"id": "team-1", "name": "Operate"}]}}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_linear_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
        requirements=[AgentRequirement(summary="calendar_linear_minutes_fixture_zero")],
        target_services=["google", "linear"],
        selected_tools=["google_calendar_list_events", "linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_linear_minutes_fixture_zero",
                title="fixture dag linear minutes zero",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert result.summary == "DAG 파이프라인 실행 완료"
    assert result.artifacts.get("processed_count") == "0"
    tool_names = [name for name, _ in calls]
    assert tool_names.count("google_calendar_list_events") == 1
    assert tool_names.count("linear_create_issue") == 0


def test_google_calendar_to_linear_minutes_fixture_passes_user_timezone(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "linear_list_teams":
            return {"ok": True, "data": {"teams": {"nodes": [{"id": "team-1", "name": "Operate"}]}}}
        if tool_name == "google_calendar_list_events":
            assert payload.get("time_zone") == "Asia/Seoul"
            assert str(payload.get("time_min") or "").endswith("Z")
            assert str(payload.get("time_max") or "").endswith("Z")
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                    ]
                },
            }
        if tool_name == "linear_create_issue":
            return {
                "ok": True,
                "data": {"issueCreate": {"issue": {"id": "iss-1", "url": "https://linear.app/issue/ISS-1"}}},
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))
    monkeypatch.setattr("agent.executor._load_user_timezone", lambda _user_id: "Asia/Seoul")

    pipeline = build_google_calendar_to_linear_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
        requirements=[AgentRequirement(summary="calendar_linear_minutes_fixture_tz")],
        target_services=["google", "linear"],
        selected_tools=["google_calendar_list_events", "linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_linear_minutes_fixture_tz",
                title="fixture dag linear minutes timezone",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-seoul", plan))
    assert result.success is True
    assert [name for name, _ in calls].count("google_calendar_list_events") == 1


def test_google_calendar_to_linear_minutes_fixture_partial_failure_stops_pipeline(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "linear_list_teams":
            return {"ok": True, "data": {"teams": {"nodes": [{"id": "team-1", "name": "Operate"}]}}}
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-1", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-2", "title": "분기 회의", "description": "실적 리뷰"},
                    ]
                },
            }
        if tool_name == "linear_create_issue":
            index = len([name for name, _ in calls if name == "linear_create_issue"])
            if index >= 2:
                return {"ok": False, "error_code": "tool_failed", "detail": "boom"}
            return {"ok": True, "data": {"issueCreate": {"issue": {"id": f"iss-{index}"}}}}
        if tool_name == "linear_update_issue":
            return {"ok": True, "data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_linear_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
        requirements=[AgentRequirement(summary="calendar_linear_minutes_fixture_partial_failure")],
        target_services=["google", "linear"],
        selected_tools=["google_calendar_list_events", "linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_linear_minutes_fixture_partial_failure",
                title="fixture dag linear minutes partial failure",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is False
    assert result.summary == "DAG 파이프라인 실행 실패"
    assert [name for name, _ in calls].count("linear_create_issue") >= 2


def test_google_calendar_to_linear_minutes_fixture_dedupes_duplicate_event_writes(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict) -> dict:
        _ = user_id
        calls.append((tool_name, payload))
        if tool_name == "linear_list_teams":
            return {"ok": True, "data": {"teams": {"nodes": [{"id": "team-1", "name": "Operate"}]}}}
        if tool_name == "google_calendar_list_events":
            return {
                "ok": True,
                "data": {
                    "events": [
                        {"id": "evt-dup", "title": "주간 회의", "description": "백로그 점검"},
                        {"id": "evt-dup", "title": "주간 회의", "description": "백로그 점검"},
                    ]
                },
            }
        if tool_name == "linear_create_issue":
            return {"ok": True, "data": {"issueCreate": {"issue": {"id": "iss-dup"}}}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._validate_dag_policy_guards", lambda **kwargs: (True, None, None, None))

    pipeline = build_google_calendar_to_linear_minutes_pipeline(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성"
    )
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
        requirements=[AgentRequirement(summary="calendar_linear_minutes_fixture_dedupe")],
        target_services=["google", "linear"],
        selected_tools=["google_calendar_list_events", "linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        tasks=[
            AgentTask(
                id="task_pipeline_dag_linear_minutes_fixture_dedupe",
                title="fixture dag linear minutes dedupe",
                task_type="PIPELINE_DAG",
                payload={"pipeline": pipeline, "ctx": {"enabled": True}},
            )
        ],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    tool_names = [name for name, _ in calls]
    assert tool_names.count("linear_create_issue") == 1
