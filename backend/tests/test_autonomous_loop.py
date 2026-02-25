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
        llm_autonomous_strict_tool_scope=False,
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
            llm_autonomous_strict_tool_scope=False,
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


def test_autonomous_append_multiple_targets_requires_enough_calls(monkeypatch):
    def _settings_multi():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
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
            ({"action": "final", "final_response": "두 페이지에 추가 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"id": payload["block_id"]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_multi)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    plan = _plan('노션에서 "더 코어 3", "사이먼 블로그" 페이지에 핵심 주제를 각각 추가해줘')
    result = asyncio.run(run_autonomous_loop("user-1", plan))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert result.artifacts.get("verification_reason") == "append_requires_multiple_targets"


def test_autonomous_append_multiple_targets_succeeds_with_enough_calls(monkeypatch):
    def _settings_multi():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=6,
            llm_autonomous_max_tool_calls=6,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
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
                    "tool_input": {"block_id": "p2", "children": [{"object": "block"}]},
                },
                None,
            ),
            ({"action": "final", "final_response": "두 페이지에 추가 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"id": payload["block_id"]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_multi)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    plan = _plan('노션에서 "더 코어 3", "사이먼 블로그" 페이지에 핵심 주제를 각각 추가해줘')
    result = asyncio.run(run_autonomous_loop("user-1", plan))

    assert result.success is True


def test_autonomous_records_llm_provider_and_model(monkeypatch):
    sequence = iter(
        [
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_search",
                    "tool_input": {"query": "metel"},
                    "_provider": "openai",
                    "_model": "gpt-4o-mini",
                },
                None,
            ),
            (
                {
                    "action": "final",
                    "final_response": "조회 완료",
                    "_provider": "openai",
                    "_model": "gpt-4o-mini",
                },
                None,
            ),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is True
    assert result.artifacts.get("llm_provider") == "openai"
    assert result.artifacts.get("llm_model") == "gpt-4o-mini"


def test_autonomous_strict_tool_scope_blocks_unplanned_tool(monkeypatch):
    def _settings_strict():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=True,
        )

    sequence = iter(
        [
            (
                {"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "x"}},
                None,
            ),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise AssertionError("disallowed tool must not execute")

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_strict)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert any(step.detail == "tool_not_allowed:notion_create_page" for step in result.steps)


def test_autonomous_replan_cannot_expand_selected_tools(monkeypatch):
    def _settings_replan():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=1,
            llm_autonomous_strict_tool_scope=False,
        )

    sequence = iter(
        [
            (
                {
                    "action": "replan",
                    "reason": "생성 도구를 추가합니다.",
                    "updated_selected_tools": ["notion_search", "notion_create_page"],
                },
                None,
            ),
            (
                {"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "x"}},
                None,
            ),
            ({"action": "final", "final_response": "생성 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise AssertionError("replan expansion-blocked tool must not execute")

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_replan)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션 페이지 만들어줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert any(step.detail == "replan_tool_expansion_blocked:notion_create_page" for step in result.steps)
    assert any(step.detail == "tool_not_allowed:notion_create_page" for step in result.steps)


def test_autonomous_blocks_duplicate_validation_error_call(monkeypatch):
    def _settings_validation():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=5,
            llm_autonomous_max_tool_calls=5,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
        )

    sequence = iter(
        [
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_search",
                    "tool_input": {"query": "metel", "start_cursor": {"bad": "cursor"}},
                },
                None,
            ),
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_search",
                    "tool_input": {"query": "metel", "start_cursor": {"bad": "cursor"}},
                },
                None,
            ),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise HTTPException(status_code=400, detail=f"{tool_name}:VALIDATION_TYPE:start_cursor")

    from fastapi import HTTPException

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_validation)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert any(step.detail == "duplicate_validation_error_call_blocked" for step in result.steps)


def test_autonomous_returns_clarification_required_on_repeated_required_slot(monkeypatch):
    def _settings_validation():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=5,
            llm_autonomous_max_tool_calls=5,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=1,
            llm_autonomous_strict_tool_scope=False,
        )

    sequence = iter(
        [
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_search",
                    "tool_input": {},
                },
                None,
            ),
            (
                {
                    "action": "tool_call",
                    "tool_name": "notion_search",
                    "tool_input": {},
                },
                None,
            ),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise HTTPException(status_code=400, detail=f"{tool_name}:VALIDATION_REQUIRED:query")

    from fastapi import HTTPException

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_validation)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "clarification_required"
    assert result.artifacts.get("slot_action") == "notion_search"
    assert result.artifacts.get("missing_slot") == "query"


def test_autonomous_verifier_blocks_scope_violation(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "회의 노트"}}, None),
            ({"action": "final", "final_response": "완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"id": "page-1", "title": payload.get("title", "")}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    plan = AgentPlan(
        user_text="오늘 일정 중 회의만 리니어 이슈 생성",
        requirements=[AgentRequirement(summary="생성")],
        target_services=["notion"],
        selected_tools=["notion_create_page"],
        workflow_steps=[],
        notes=["target_scope=linear_only"],
    )
    result = asyncio.run(run_autonomous_loop("user-1", plan))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert result.artifacts.get("verifier_failed_rule") == "target_scope_linear_only_violation"
    assert result.artifacts.get("verifier_remediation_type") == "scope_violation"


def test_autonomous_verifier_blocks_include_keyword_violation(monkeypatch):
    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_create_page", "tool_input": {"title": "점심 정리"}}, None),
            ({"action": "final", "final_response": "완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"id": "page-1", "title": payload.get("title", "")}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    plan = AgentPlan(
        user_text="오늘 일정 중 회의만 노션 페이지 생성",
        requirements=[AgentRequirement(summary="생성")],
        target_services=["notion"],
        selected_tools=["notion_create_page"],
        workflow_steps=[],
        notes=["target_scope=notion_only", "event_filter_include=회의"],
    )
    result = asyncio.run(run_autonomous_loop("user-1", plan))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert str(result.artifacts.get("verifier_failed_rule", "")).startswith("include_keyword_not_satisfied:")
    assert result.artifacts.get("verifier_remediation_type") == "filter_include_missing"


def test_autonomous_llm_verifier_rejects_final_response(monkeypatch):
    def _settings_with_verifier():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
            llm_autonomous_verifier_enabled=True,
        )

    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "metel"}}, None),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    async def _fake_llm_verify_completion(**kwargs):
        return "fail", "근거 부족", "openai:gpt-4o-mini"

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_with_verifier)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.autonomous._llm_verify_completion", _fake_llm_verify_completion)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert str(result.artifacts.get("verification_reason", "")).startswith("llm_verifier_rejected:")
    assert any(step.name.endswith("_verify_llm") and step.status == "error" for step in result.steps)


def test_autonomous_llm_verifier_passes_final_response(monkeypatch):
    def _settings_with_verifier():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
            llm_autonomous_verifier_enabled=True,
        )

    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "metel"}}, None),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    async def _fake_llm_verify_completion(**kwargs):
        return "pass", "근거 일치", "openai:gpt-4o-mini"

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_with_verifier)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.autonomous._llm_verify_completion", _fake_llm_verify_completion)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is True
    assert result.artifacts.get("llm_verifier") == "openai:gpt-4o-mini"
    assert any(step.name.endswith("_verify_llm") and step.status == "success" for step in result.steps)


def test_autonomous_llm_verifier_fail_closed_on_unavailable(monkeypatch):
    def _settings_with_verifier_fail_closed():
        return SimpleNamespace(
            llm_autonomous_enabled=True,
            llm_autonomous_max_turns=4,
            llm_autonomous_max_tool_calls=4,
            llm_autonomous_timeout_sec=30,
            llm_autonomous_replan_limit=0,
            llm_autonomous_strict_tool_scope=False,
            llm_autonomous_verifier_enabled=True,
            llm_autonomous_verifier_fail_closed=True,
            llm_autonomous_verifier_max_history=8,
            llm_autonomous_verifier_require_tool_evidence=True,
            llm_planner_provider="openai",
            llm_planner_model="gpt-4o-mini",
            llm_planner_fallback_provider="gemini",
            llm_planner_fallback_model="gemini-2.5-flash-lite",
            openai_api_key="k",
            google_api_key="k",
        )

    sequence = iter(
        [
            ({"action": "tool_call", "tool_name": "notion_search", "tool_input": {"query": "metel"}}, None),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        return {"ok": True, "data": {"results": [{"id": "p1"}]}}

    async def _fake_request_autonomous_action(**kwargs):
        return None, "http_500"

    monkeypatch.setattr("agent.autonomous.get_settings", _settings_with_verifier_fail_closed)
    monkeypatch.setattr("agent.autonomous.load_registry", _registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.autonomous._request_autonomous_action", _fake_request_autonomous_action)

    result = asyncio.run(run_autonomous_loop("user-1", _plan("노션에서 최근 페이지 조회해줘")))

    assert result.success is False
    assert result.artifacts.get("error_code") == "verification_failed"
    assert str(result.artifacts.get("verification_reason", "")).startswith("llm_verifier_rejected:verifier_unavailable_fail_closed")


def test_autonomous_forces_today_range_for_google_calendar_tool(monkeypatch):
    plan = AgentPlan(
        user_text="구글캘린더에서 오늘 일정 조회해주세요",
        requirements=[AgentRequirement(summary="오늘 일정 조회")],
        target_services=["google"],
        selected_tools=["google_calendar_list_events"],
        workflow_steps=[],
        notes=[],
    )

    sequence = iter(
        [
            (
                {
                    "action": "tool_call",
                    "tool_name": "google_calendar_list_events",
                    "tool_input": {
                        "calendar_id": "windbug99@gmail.com",
                        "time_min": "2023-10-10T00:00:00+09:00",
                        "time_max": "2023-10-10T23:59:59+09:00",
                        "time_zone": "Asia/Seoul",
                    },
                },
                None,
            ),
            ({"action": "final", "final_response": "조회 완료"}, None),
        ]
    )

    async def _fake_choose(**kwargs):
        return next(sequence)

    google_tool = SimpleNamespace(
        tool_name="google_calendar_list_events",
        description="list events",
        input_schema={"type": "object", "properties": {"calendar_id": {"type": "string"}}},
    )
    registry = SimpleNamespace(
        list_tools=lambda service: [google_tool] if service == "google" else [],
        get_tool=lambda name: google_tool,
    )

    captured: dict = {}

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        _ = user_id
        captured["tool_name"] = tool_name
        captured["payload"] = dict(payload)
        return {"ok": True, "data": {"items": [{"id": "e1"}]}}

    monkeypatch.setattr("agent.autonomous.get_settings", _settings)
    monkeypatch.setattr("agent.autonomous.load_registry", lambda: registry)
    monkeypatch.setattr("agent.autonomous._choose_next_action", _fake_choose)
    monkeypatch.setattr("agent.autonomous.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_autonomous_loop("user-1", plan))

    assert result.success is True
    payload = captured["payload"]
    assert captured["tool_name"] == "google_calendar_list_events"
    assert payload["calendar_id"] == "windbug99@gmail.com"
    assert payload["time_zone"] == "Asia/Seoul"
    assert payload["time_min"] != "2023-10-10T00:00:00+09:00"
    assert payload["time_max"] != "2023-10-10T23:59:59+09:00"
    assert payload["single_events"] is True
    assert payload["order_by"] == "startTime"
