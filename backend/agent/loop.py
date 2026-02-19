from __future__ import annotations

import re

from agent.autonomous import run_autonomous_loop
from agent.executor import execute_agent_plan
from agent.planner import build_agent_plan
from agent.planner_llm import try_build_agent_plan_with_llm
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentRunResult
from app.core.config import get_settings


def _has_any_tool(selected_tools: list[str], *tokens: str) -> bool:
    return any(any(token in tool for token in tokens) for tool in selected_tools)


def _is_delete_intent(text: str) -> bool:
    patterns = [
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*삭제(?:해줘|해|해주세요)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*지워(?:줘|줘요|라|해줘|해)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*아카이브(?:해줘|해|해주세요)\b",
        r"(?i)\b페이지\s*삭제\b",
        r"(?i)\barchive\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _plan_consistency_reason(user_text: str, selected_tools: list[str]) -> str | None:
    text = (user_text or "").strip()
    lower = text.lower()
    tools = selected_tools or []

    if _is_delete_intent(text) and not _has_any_tool(tools, "delete_block", "update_page", "archive"):
        return "missing_delete_tool"

    if ("데이터소스" in text or "data source" in lower or "data_source" in lower) and any(
        token in text for token in ("조회", "목록", "query", "불러", "보여")
    ):
        if not _has_any_tool(tools, "query_data_source", "retrieve_data_source"):
            return "missing_data_source_tool"

    if ("추가" in text and "페이지" in text) and not _has_any_tool(tools, "append_block_children"):
        return "missing_append_tool"

    if any(token in text for token in ("생성", "만들", "작성", "create")) and not _has_any_tool(tools, "create_page"):
        return "missing_create_tool"

    if "요약" in text and not _has_any_tool(tools, "retrieve_block_children", "retrieve_page"):
        return "missing_summary_read_tool"

    if any(token in text for token in ("조회", "검색", "목록", "출력", "보여")) and not _has_any_tool(tools, "search"):
        return "missing_search_tool"

    return None


def _parse_data_source_query_state(user_text: str) -> tuple[bool, str]:
    text = user_text or ""
    lower = text.lower()
    if not (("데이터소스" in text) or ("data source" in lower) or ("data_source" in lower)):
        return False, "none"
    if not any(keyword in text for keyword in ("조회", "목록", "query", "불러", "보여")):
        return False, "none"

    id_match = re.search(r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})", text)
    if id_match:
        return True, "ok"

    token_match = re.search(r"(?i)(?:데이터소스|data[_ ]source)\s+([^\s]+)", text)
    if not token_match:
        return True, "missing"

    candidate = token_match.group(1).strip(" \"'`,.;:()[]{}")
    if not candidate or candidate in {"조회", "목록", "검색", "불러", "보여", "최근", "상위"}:
        return True, "missing"
    return True, "invalid"


async def run_agent_analysis(user_text: str, connected_services: list[str], user_id: str) -> AgentRunResult:
    """Run the agent flow with planning + execution.

    Stage coverage:
    1) requirement extraction
    2) service/API selection
    3) workflow generation
    4) workflow execution
    5) result summary and return payload generation
    """
    is_data_source_query, data_source_state = _parse_data_source_query_state(user_text)
    if is_data_source_query and data_source_state in {"missing", "invalid"}:
        plan = build_agent_plan(user_text=user_text, connected_services=connected_services)
        detail = "id_missing" if data_source_state == "missing" else "id_invalid_format"
        user_message = (
            "데이터소스 조회를 위해 ID가 필요합니다.\n"
            "예: '노션 데이터소스 <id> 최근 5개 조회'"
            if data_source_state == "missing"
            else (
                "데이터소스 ID 형식이 올바르지 않습니다.\n"
                "UUID 형식으로 입력해주세요.\n"
                "예: '노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 5개 조회'"
            )
        )
        summary = (
            "데이터소스 ID를 찾지 못했습니다."
            if data_source_state == "missing"
            else "데이터소스 ID 형식이 올바르지 않습니다."
        )
        execution = AgentExecutionResult(
            success=False,
            summary=summary,
            user_message=user_message,
            artifacts={"error_code": "validation_error"},
            steps=[AgentExecutionStep(name="parse_data_source_id", status="error", detail=detail)],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=plan,
            result_summary=summary,
            execution=execution,
            plan_source="rule",
        )

    plan_source = "rule"
    llm_plan, llm_error = await try_build_agent_plan_with_llm(
        user_text=user_text,
        connected_services=connected_services,
    )
    if llm_plan:
        plan = llm_plan
        plan_source = "llm"
        consistency_error = _plan_consistency_reason(user_text, plan.selected_tools)
        if consistency_error:
            # Auto-replan to deterministic rule planner when LLM plan misses essential tools.
            plan = build_agent_plan(user_text=user_text, connected_services=connected_services)
            plan_source = "rule"
            plan.notes.append(f"plan_realign_from_llm:{consistency_error}")
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
    autonomous_enabled = bool(getattr(settings, "llm_autonomous_enabled", False))
    autonomous_strict = bool(getattr(settings, "llm_autonomous_strict", False))
    autonomous_retry_once = bool(getattr(settings, "llm_autonomous_limit_retry_once", True))

    if autonomous_enabled:
        autonomous = await run_autonomous_loop(user_id=user_id, plan=plan)
        if autonomous.success:
            execution = autonomous
            plan.notes.append("execution=autonomous")
        else:
            error_code = str(autonomous.artifacts.get("error_code", "unknown"))
            plan.notes.append(f"autonomous_error={error_code}")

            retryable_errors = {"turn_limit", "tool_call_limit", "replan_limit", "timeout"}
            if autonomous_retry_once and error_code in retryable_errors:
                plan.notes.append("autonomous_retry=1")
                retry = await run_autonomous_loop(
                    user_id=user_id,
                    plan=plan,
                    max_turns_override=max(2, int(getattr(settings, "llm_autonomous_max_turns", 6)) + 2),
                    max_tool_calls_override=max(2, int(getattr(settings, "llm_autonomous_max_tool_calls", 8)) + 2),
                    timeout_sec_override=max(10, int(getattr(settings, "llm_autonomous_timeout_sec", 45)) + 15),
                    replan_limit_override=max(0, int(getattr(settings, "llm_autonomous_replan_limit", 1)) + 1),
                )
                if retry.success:
                    execution = retry
                    plan.notes.append("execution=autonomous_retry")
                else:
                    autonomous = retry
                    error_code = str(retry.artifacts.get("error_code", error_code))
                    plan.notes.append(f"autonomous_retry_error={error_code}")

            if execution is None and autonomous_strict:
                execution = autonomous
                plan.notes.append("execution=autonomous_strict")

            if execution is None:
                plan.notes.append("execution=autonomous_fallback")

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
