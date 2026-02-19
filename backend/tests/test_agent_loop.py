import asyncio

from agent.loop import run_agent_analysis
from agent.types import AgentExecutionResult, AgentPlan, AgentRequirement


def _sample_plan() -> AgentPlan:
    return AgentPlan(
        user_text="노션에서 최근 페이지 3개 조회",
        requirements=[AgentRequirement(summary="대상 데이터 조회", quantity=3)],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=["1", "2"],
        notes=[],
    )


def test_run_agent_analysis_uses_llm_plan(monkeypatch):
    llm_plan = _sample_plan()
    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "llm"


def test_run_agent_analysis_falls_back_to_rule(monkeypatch):
    rule_plan = _sample_plan()
    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return None, "llm_planner_disabled"

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(item.startswith("llm_planner_fallback:") for item in result.plan.notes)


def test_run_agent_analysis_prefers_autonomous_when_enabled(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(
            success=True,
            user_message="auto-ok",
            summary="auto-done",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when autonomous succeeds")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "auto-done"
    assert any(item == "execution=autonomous" for item in result.plan.notes)


def test_run_agent_analysis_prefers_autonomous_even_with_rule_plan(monkeypatch):
    rule_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return None, "llm_planner_disabled"

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(
            success=True,
            user_message="auto-ok",
            summary="auto-done",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when autonomous succeeds")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert result.result_summary == "auto-done"
    assert any(item == "execution=autonomous" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_fallback_to_executor(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "done"
    assert any(item == "execution=autonomous_fallback" for item in result.plan.notes)
    assert any(item == "autonomous_error=turn_limit" for item in result.plan.notes)


def test_run_agent_analysis_validates_data_source_id_early(monkeypatch):
    called = {"llm": False, "exec": False}

    async def _fake_try_build(**kwargs):
        called["llm"] = True
        raise AssertionError("llm planner should not be called for invalid data source id")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        called["exec"] = True
        raise AssertionError("executor should not be called for invalid data source id")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 데이터소스 invalid-id 조회해줘", ["notion"], "user-1"))
    assert result.ok is False
    assert result.stage == "validation"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "validation_error"
    assert "형식이 올바르지" in result.execution.user_message
    assert called == {"llm": False, "exec": False}


def test_run_agent_analysis_autonomous_strict_no_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = True
        llm_autonomous_limit_retry_once = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called in strict mode")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is False
    assert result.result_summary == "auto-fail"
    assert any(item == "execution=autonomous_strict" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_retry_then_success(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_max_turns = 6
        llm_autonomous_max_tool_calls = 8
        llm_autonomous_timeout_sec = 45
        llm_autonomous_replan_limit = 1

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="limit",
                summary="limit",
                artifacts={"error_code": "turn_limit"},
            )
        assert kwargs.get("max_turns_override") == 8
        assert isinstance(kwargs.get("extra_guidance"), str)
        assert "turn 한도" in kwargs.get("extra_guidance")
        return AgentExecutionResult(
            success=True,
            user_message="auto-retry-ok",
            summary="auto-retry-ok",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called after retry success")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "auto-retry-ok"
    assert calls["count"] == 2
    assert any(item == "autonomous_retry=1" for item in result.plan.notes)
    assert any(item == "execution=autonomous_retry" for item in result.plan.notes)


def test_run_agent_analysis_realigns_bad_llm_plan_to_rule(monkeypatch):
    # Delete intent인데 llm plan이 delete/update tool을 빠뜨린 경우 자동 재계획(rule)로 전환
    bad_llm_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search"],  # intentionally incomplete
        workflow_steps=["1. 검색", "2. 삭제"],
        notes=[],
    )
    rule_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search", "notion_update_page"],
        workflow_steps=["1. 검색", "2. 아카이브"],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return bad_llm_plan, None

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("일일 회의록 페이지 삭제해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(item.startswith("plan_realign_from_llm:") for item in result.plan.notes)
