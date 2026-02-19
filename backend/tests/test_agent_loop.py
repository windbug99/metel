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

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "llm"


def test_run_agent_analysis_falls_back_to_rule(monkeypatch):
    rule_plan = _sample_plan()

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


def test_run_agent_analysis_autonomous_fallback_to_executor(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
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
