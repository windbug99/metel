import asyncio
from types import SimpleNamespace

from agent.autonomous import run_autonomous_loop
from agent.types import AgentPlan, AgentRequirement


def _plan(user_text: str) -> AgentPlan:
    return AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary="대상 데이터 조회")],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=[],
        notes=[],
    )


def _settings():
    return SimpleNamespace(
        llm_autonomous_enabled=True,
        llm_autonomous_max_turns=4,
        llm_autonomous_max_tool_calls=4,
        llm_autonomous_timeout_sec=30,
        llm_autonomous_replan_limit=0,
    )


def _registry():
    notion_search = SimpleNamespace(
        tool_name="notion_search",
        description="search",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    notion_create = SimpleNamespace(
        tool_name="notion_create_page",
        description="create page",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )
    notion_append = SimpleNamespace(
        tool_name="notion_append_block_children",
        description="append block children",
        input_schema={
            "type": "object",
            "properties": {"block_id": {"type": "string"}, "children": {"type": "array"}},
        },
    )
    tools = [notion_search, notion_create, notion_append]
    return SimpleNamespace(
        list_tools=lambda service: tools if service == "notion" else [],
        get_tool=lambda name: next(item for item in tools if item.tool_name == name),
    )


def test_autonomous_verify_fails_when_no_tool_for_lookup(monkeypatch):
    async def _fake_choose(**kwargs):
        return {"action": "final", "final_response": "완료"}, None

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"


def test_autonomous_succeeds_after_tool_then_final(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "metel"}}, None),
            ({"action": "final", "final_response": "최근 페이지 3건을 조회했습니다."}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert tool_name == "notion_search"
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is True
    assert result.artifacts.get("autonomous") == "true"
    assert any(step.name.endswith("_verify") and step.status == "success" for step in result.steps)


def test_autonomous_creation_requires_artifact_reference(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "t1"}}, None),
            ({"action": "final", "final_response": "생성 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert tool_name == "notion_create_page"
        return {"ok": True, "data": {"object": "page"}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션 페이지 만들어줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"


def test_autonomous_creation_passes_with_artifact_reference(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "t1"}}, None),
            ({"action": "final", "final_response": "생성 완료: https://notion.so/page-1"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert tool_name == "notion_create_page"
        return {"ok": True, "data": {"id": "page-1", "url": "https://notion.so/page-1"}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션 페이지 만들어줘")))

    assert result.success is True
    assert result.artifacts.get("autonomous") == "true"


def test_autonomous_move_requires_update_page_tool(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "0219"}}, None),
            ({"action": "final", "final_response": "페이지 이동을 완료했습니다."}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert tool_name == "notion_search"
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("0219 페이지를 Metel test page 하위로 이동시켜줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert any(step.name.endswith("_verify") and step.detail == "move_requires_update_page" for step in result.steps)


def test_autonomous_append_requires_append_block_children_tool(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "0219"}}, None),
            ({"action": "final", "final_response": "페이지에 내용을 추가했습니다."}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert tool_name == "notion_search"
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("0219 페이지에 액션 아이템 추가해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert any(
        step.name.endswith("_verify") and step.detail == "append_requires_append_block_children"
        for step in result.steps
    )


def test_autonomous_blocks_duplicate_mutation_tool_call(monkeypatch):
    def _settings_dup():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=5,
            llm_autonomous_max_tool_calls=5,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=1,
        )

    sequence = iter(
        [
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_append_block_children",
                    "tool_input": {"block_id": "p1", "children": [{"object": "block"}]},
                },
                None,
            ),
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_append_block_children",
                    "tool_input": {"block_id": "p1", "children": [{"object": "block"}]},
                },
                None,
            ),
            ({"action": "final", "final_response": "추가를 완료했습니다."}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        return {"ok": True, "data": {"id": "p1"}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_dup)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("0219 페이지에 액션 아이템 추가해줘")))

    assert result.success is True
    assert len(calls) == 1
    assert any(step.detail == "duplicate_mutation_call_blocked" for step in result.steps)
