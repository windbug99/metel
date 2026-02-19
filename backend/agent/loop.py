from __future__ import annotations

from agent.autonomous import run_autonomous_loop
from agent.executor import execute_agent_plan
from agent.planner import build_agent_plan
from agent.planner_llm import try_build_agent_plan_with_llm
from agent.types import AgentRunResult
from app.core.config import get_settings


async def run_agent_analysis(user_text: str, connected_services: list[str], user_id: str) -> AgentRunResult:
    """Run the agent flow with planning + execution.

    Stage coverage:
    1) requirement extraction
    2) service/API selection
    3) workflow generation
    4) workflow execution
    5) result summary and return payload generation
    """
    plan_source = "rule"
    llm_plan, llm_error = await try_build_agent_plan_with_llm(
        user_text=user_text,
        connected_services=connected_services,
    )
    if llm_plan:
        plan = llm_plan
        plan_source = "llm"
    else:
        plan = build_agent_plan(user_text=user_text, connected_services=connected_services)
        if llm_error:
            plan.notes.append(f"llm_planner_fallback:{llm_error}")

    if not plan.target_services:
        summary = (
            "요청에서 타겟 서비스를 확정하지 못했습니다. "
            "예: '노션', '스포티파이'처럼 서비스 이름을 포함해 다시 요청해주세요."
        )
        return AgentRunResult(
            ok=False,
            stage="planning",
            plan=plan,
            result_summary=summary,
            execution=None,
            plan_source=plan_source,
        )

    settings = get_settings()
    execution = None
    if settings.llm_autonomous_enabled and plan_source == "llm":
        autonomous = await run_autonomous_loop(user_id=user_id, plan=plan)
        if autonomous.success:
            execution = autonomous
            plan.notes.append("execution=autonomous")
        else:
            plan.notes.append("execution=autonomous_fallback")
            plan.notes.append(f"autonomous_error={autonomous.artifacts.get('error_code', 'unknown')}")

    if execution is None:
        execution = await execute_agent_plan(user_id=user_id, plan=plan)

    summary = execution.summary
    return AgentRunResult(
        ok=execution.success,
        stage="execution",
        plan=plan,
        result_summary=summary,
        execution=execution,
        plan_source=plan_source,
    )
