from __future__ import annotations

import json
import re

from agent.autonomous import run_autonomous_loop
from agent.executor import execute_agent_plan
from agent.intent_keywords import (
    is_append_intent,
    is_create_intent,
    is_data_source_intent,
    is_delete_intent as _is_delete_intent_shared,
    is_read_intent,
    is_summary_intent,
    is_update_intent,
)
from agent.pending_action import clear_pending_action, get_pending_action, set_pending_action
from agent.planner import build_agent_plan
from agent.planner_llm import try_build_agent_plan_with_llm
from agent.registry import load_registry
from agent.slot_collector import collect_slots_from_user_reply, slot_prompt_example
from agent.slot_schema import get_action_slot_schema
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentRunResult
from app.core.config import get_settings


def _has_any_tool(selected_tools: list[str], *tokens: str) -> bool:
    return any(any(token in tool for token in tokens) for tool in selected_tools)


def _tool_service(tool_name: str) -> str:
    return (tool_name or "").split("_", 1)[0].strip().lower()


def _realign_selected_tools_from_tasks(plan) -> list[str]:
    tasks = getattr(plan, "tasks", None) or []
    task_tools = [str(task.tool_name).strip() for task in tasks if getattr(task, "task_type", "") == "TOOL" and getattr(task, "tool_name", "")]
    if not task_tools:
        return plan.selected_tools
    seen: set[str] = set()
    realigned: list[str] = []
    for name in task_tools:
        if name in seen:
            continue
        seen.add(name)
        realigned.append(name)
    return realigned


def _is_delete_intent(text: str) -> bool:
    patterns = [
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*삭제(?:해줘|해|해주세요)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*지워(?:줘|줘요|라|해줘|해)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*아카이브(?:해줘|해|해주세요)\b",
        r"(?i)\b페이지\s*삭제\b",
        r"(?i)\barchive\b",
    ]
    return _is_delete_intent_shared(text) or any(re.search(pattern, text) for pattern in patterns)


def _plan_consistency_reason(user_text: str, selected_tools: list[str]) -> str | None:
    text = (user_text or "").strip()
    lower = text.lower()
    tools = selected_tools or []
    has_linear = ("linear" in lower) or ("리니어" in text)
    has_notion = ("notion" in lower) or ("노션" in text)

    if has_linear and not has_notion and any(_tool_service(tool) == "notion" for tool in tools):
        return "cross_service_tool_leak_notion"
    if has_notion and not has_linear and any(_tool_service(tool) == "linear" for tool in tools):
        return "cross_service_tool_leak_linear"

    if _is_delete_intent(text) and not _has_any_tool(tools, "delete_block", "update_page", "archive"):
        return "missing_delete_tool"

    if is_data_source_intent(text) and is_read_intent(text):
        if not _has_any_tool(tools, "query_data_source", "retrieve_data_source"):
            return "missing_data_source_tool"

    if is_append_intent(text) and "페이지" in text and not _has_any_tool(tools, "append_block_children"):
        return "missing_append_tool"

    if is_create_intent(text) and not _has_any_tool(tools, "create_page", "create_issue", "create_"):
        return "missing_create_tool"

    if is_summary_intent(text) and not _has_any_tool(tools, "retrieve_block_children", "retrieve_page"):
        return "missing_summary_read_tool"

    if is_read_intent(text) and not _has_any_tool(tools, "search"):
        return "missing_search_tool"

    return None


def _required_tokens_for_consistency_error(reason: str) -> tuple[str, ...]:
    mapping = {
        "missing_delete_tool": ("delete_block", "update_page", "archive"),
        "missing_data_source_tool": ("query_data_source", "retrieve_data_source"),
        "missing_append_tool": ("append_block_children",),
        "missing_create_tool": ("create_", "append_block_children"),
        "missing_summary_read_tool": ("retrieve_block_children", "retrieve_page"),
        "missing_search_tool": ("search",),
        "cross_service_tool_leak_notion": (),
        "cross_service_tool_leak_linear": (),
    }
    return mapping.get(reason, ())


def _enrich_plan_tools_with_registry(
    *,
    user_text: str,
    selected_tools: list[str],
    target_services: list[str],
) -> tuple[list[str], str | None]:
    reason = _plan_consistency_reason(user_text, selected_tools)
    if not reason:
        return selected_tools, None

    required_tokens = _required_tokens_for_consistency_error(reason)
    if not required_tokens:
        return selected_tools, reason

    try:
        registry = load_registry()
    except Exception:
        return selected_tools, reason

    candidates: list[str] = []
    for service in target_services:
        for tool in registry.list_tools(service):
            candidates.append(tool.tool_name)

    enriched = list(selected_tools)
    for token in required_tokens:
        if any(token in name for name in enriched):
            continue
        match = next((name for name in candidates if token in name), None)
        if match and match not in enriched:
            enriched.append(match)

    post_reason = _plan_consistency_reason(user_text, enriched)
    return enriched, post_reason


def _parse_data_source_query_state(user_text: str) -> tuple[bool, str]:
    text = user_text or ""
    if not is_data_source_intent(text):
        return False, "none"
    if not is_read_intent(text):
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


def _is_mutation_intent(user_text: str) -> bool:
    text = (user_text or "").strip()
    lower = text.lower()
    return (
        is_create_intent(text)
        or is_append_intent(text)
        or is_update_intent(text)
        or _is_delete_intent_shared(text)
        or any(keyword in lower for keyword in ("이동", "옮겨", "rename", "move"))
    )


def _is_multi_target_intent(user_text: str) -> bool:
    text = (user_text or "").strip().lower()
    quoted_count = len(re.findall(r'"[^"]+"|\'[^\']+\'', text))
    if quoted_count >= 2:
        return True
    if "각각" in text and any(token in text for token in (",", "와", "그리고")):
        return True
    return False


def _build_retry_overrides(
    *,
    settings,
    user_text: str,
    error_code: str,
    verification_reason: str | None = None,
) -> dict[str, int]:
    base_turns = int(getattr(settings, "llm_autonomous_max_turns", 6))
    base_tool_calls = int(getattr(settings, "llm_autonomous_max_tool_calls", 8))
    base_timeout = int(getattr(settings, "llm_autonomous_timeout_sec", 45))
    base_replan = int(getattr(settings, "llm_autonomous_replan_limit", 1))

    is_mutation = _is_mutation_intent(user_text)
    is_multi_target = _is_multi_target_intent(user_text)

    turn_bonus = 2
    tool_bonus = 2
    timeout_bonus = 15
    replan_bonus = 1

    if is_mutation:
        turn_bonus += 1
        tool_bonus += 2
    if is_multi_target:
        turn_bonus += 1
        tool_bonus += 3
        timeout_bonus += 10

    if error_code in {"tool_call_limit", "turn_limit"}:
        tool_bonus += 2
    if error_code in {"timeout"}:
        timeout_bonus += 20
    if error_code in {"replan_limit"}:
        replan_bonus += 1
    if error_code == "verification_failed":
        # Verification 실패는 한 번 더 재검증 기회를 주기 위해 replan/tool 예산을 확대.
        tool_bonus += 2
        replan_bonus += 1
        if verification_reason and "multiple_targets" in verification_reason:
            tool_bonus += 2
            turn_bonus += 1

    return {
        "max_turns_override": max(2, base_turns + turn_bonus),
        "max_tool_calls_override": max(2, base_tool_calls + tool_bonus),
        "timeout_sec_override": max(10, base_timeout + timeout_bonus),
        "replan_limit_override": max(0, base_replan + replan_bonus),
        "max_candidates_override": 24 if (is_mutation or is_multi_target) else 20,
    }


def _retry_guidance_for_error(error_code: str) -> str:
    guides = {
        "turn_limit": "이전 실행에서 turn 한도에 도달했습니다. 불필요한 조회를 줄이고 핵심 도구만 사용하세요.",
        "tool_call_limit": "이전 실행에서 도구 호출 한도에 도달했습니다. 반복 호출 없이 목적 작업을 우선 수행하세요.",
        "timeout": "이전 실행에서 시간 제한을 초과했습니다. 단계 수를 줄이고 즉시 실행 가능한 도구를 선택하세요.",
        "replan_limit": "이전 실행에서 재계획 한도를 초과했습니다. 재계획보다 실행 단계 완료를 우선하세요.",
        "verification_failed": "이전 실행이 완료 검증에 실패했습니다. 요청의 필수 동작을 실제 도구 호출로 충족하세요.",
    }
    return guides.get(error_code, "이전 실패 원인을 반영해 같은 오류를 반복하지 마세요.")


def _verification_guidance_for_reason(verification_reason: str | None) -> str:
    reason = (verification_reason or "").strip()
    if not reason:
        return ""
    guides = {
        "append_requires_append_block_children": (
            "추가 요청은 append_block_children 호출이 필수입니다. "
            "대상 페이지를 먼저 식별(search/retrieve)하고 append를 수행하세요."
        ),
        "append_requires_multiple_targets": (
            "복수 대상 각각 추가 요청입니다. "
            "각 대상 페이지마다 append_block_children를 최소 1회씩 호출해야 합니다."
        ),
        "move_requires_update_page": (
            "이동 요청은 update_page로 parent 갱신이 필요합니다. "
            "원본/상위 페이지를 식별한 뒤 update_page를 실행하세요."
        ),
        "rename_requires_update_page": (
            "제목 변경 요청은 update_page(properties.title)가 필요합니다. "
            "페이지 식별 후 제목 변경 payload를 포함하세요."
        ),
        "archive_requires_archive_tool": (
            "삭제/아카이브 요청은 update_page(archived 또는 in_trash) 또는 delete 계열 호출이 필요합니다."
        ),
        "lookup_requires_tool_call": (
            "조회/요약 요청은 최소 1회 이상 조회 도구(search/retrieve) 호출이 필요합니다."
        ),
        "creation_requires_artifact_reference": (
            "생성 요청은 새 리소스 id/url 근거가 필요합니다. "
            "create/append 후 결과의 id/url을 최종 응답에 반영하세요."
        ),
        "mutation_requires_mutation_tool": "변경 요청은 mutation 도구(create/append/update/delete) 호출이 필요합니다.",
        "empty_final_response": "final 응답 본문이 비어 있습니다. 작업 결과 요약을 포함해 응답하세요.",
    }
    return guides.get(reason, f"검증 실패 사유({reason})를 충족하도록 도구 호출/응답을 보강하세요.")


def _retry_tuning_rule(error_code: str, verification_reason: str | None = None) -> str:
    verification = (verification_reason or "").strip()
    if error_code == "verification_failed" and verification:
        return f"verification:{verification}"
    return f"error:{error_code}"


def _extract_last_tool_error_detail(steps: list[AgentExecutionStep]) -> str | None:
    for step in reversed(steps):
        if "_tool:" in step.name and step.status == "error":
            return f"{step.name} -> {step.detail}"
    return None


def _build_retry_guidance(autonomous: AgentExecutionResult, error_code: str) -> str:
    parts = [_retry_guidance_for_error(error_code)]
    verification_reason = str(autonomous.artifacts.get("verification_reason", "") or "").strip()
    if verification_reason:
        parts.append(f"검증 실패 사유: {verification_reason}")
        detail_guide = _verification_guidance_for_reason(verification_reason)
        if detail_guide:
            parts.append(f"검증 보완 가이드: {detail_guide}")
    last_tool_error = _extract_last_tool_error_detail(autonomous.steps)
    if last_tool_error:
        parts.append(f"직전 도구 오류: {last_tool_error}")
    return "\n".join(parts)


def _autonomous_successful_tool_calls(autonomous: AgentExecutionResult | None) -> int:
    if autonomous is None:
        return 0
    count = 0
    for step in autonomous.steps:
        if "_tool:" in step.name and step.status == "success":
            count += 1
    return count


def _autonomous_metrics(autonomous: AgentExecutionResult, plan) -> dict[str, float]:
    steps = autonomous.steps or []
    turn_actions = sum(1 for step in steps if "_action" in step.name)
    tool_steps = [step for step in steps if "_tool" in step.name]
    tool_errors = sum(1 for step in tool_steps if step.status == "error")
    replan_steps = sum(1 for step in steps if "_replan" in step.name)
    plan_services = {str(service).strip().lower() for service in (plan.target_services or [])}

    cross_service_blocks = 0
    for step in tool_steps:
        detail = str(step.detail or "")
        if not detail.startswith("tool_not_allowed:"):
            continue
        tool_name = detail.split(":", 1)[1].strip()
        service = tool_name.split("_", 1)[0].lower() if "_" in tool_name else ""
        if service and service not in plan_services:
            cross_service_blocks += 1

    tool_error_rate = float(tool_errors) / float(max(1, len(tool_steps)))
    replan_ratio = float(replan_steps) / float(max(1, turn_actions))
    return {
        "tool_error_rate": tool_error_rate,
        "replan_ratio": replan_ratio,
        "cross_service_blocks": float(cross_service_blocks),
    }


def _autonomous_guardrail_degrade_reason(settings, metrics: dict[str, float]) -> str | None:
    if not bool(getattr(settings, "llm_autonomous_guardrail_enabled", True)):
        return None
    tool_error_rate_threshold = float(getattr(settings, "llm_autonomous_guardrail_tool_error_rate_threshold", 0.6))
    replan_ratio_threshold = float(getattr(settings, "llm_autonomous_guardrail_replan_ratio_threshold", 0.5))
    cross_service_threshold = int(getattr(settings, "llm_autonomous_guardrail_cross_service_block_threshold", 1))

    if int(metrics.get("cross_service_blocks", 0.0)) >= cross_service_threshold:
        return "cross_service_blocks"
    if float(metrics.get("tool_error_rate", 0.0)) >= tool_error_rate_threshold:
        return "tool_error_rate"
    if float(metrics.get("replan_ratio", 0.0)) >= replan_ratio_threshold:
        return "replan_ratio"
    return None


def _finalizer_evidence_lines(execution: AgentExecutionResult, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for step in execution.steps:
        if step.status != "success":
            continue
        if "_tool:" in step.name or step.name.endswith("_verify") or step.name.endswith("_verify_llm"):
            lines.append(f"- {step.name}: {step.detail}")
        if len(lines) >= limit:
            break
    return lines


def _apply_response_finalizer_template(
    *,
    execution: AgentExecutionResult,
    settings,
) -> tuple[str, str]:
    if not bool(getattr(settings, "llm_response_finalizer_enabled", False)):
        return execution.user_message, "disabled"
    base = (execution.user_message or "").strip() or execution.summary
    evidence = _finalizer_evidence_lines(execution)
    if evidence:
        final = f"{base}\n\n[근거]\n" + "\n".join(evidence)
    else:
        final = base
    return final.strip(), "template"


def _is_cancel_pending_text(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return normalized in {"취소", "cancel", "그만", "중단", "/cancel"}


def _looks_like_new_request(text: str) -> bool:
    raw = (text or "").strip().lower()
    if not raw:
        return False
    service_token = any(token in raw for token in ("notion", "노션", "linear", "리니어", "spotify", "스포티파이"))
    action_token = any(
        token in raw
        for token in ("조회", "검색", "생성", "추가", "수정", "삭제", "요약", "create", "search", "update", "delete")
    )
    return service_token and action_token


def _build_slot_question_message(action: str, slot_name: str) -> str:
    display_slot = _display_slot_name(action, slot_name)
    reason = _slot_reason(action, slot_name)
    return (
        f"{display_slot} 값이 필요합니다.\n"
        f"이유: {reason}\n"
        f"예시: {slot_prompt_example(action, slot_name)}\n"
        "취소하려면 `취소`라고 입력해주세요."
    )


def _slot_reason(action: str, slot_name: str) -> str:
    action_key = (action or "").strip()
    slot_key = (slot_name or "").strip()
    reasons = {
        ("linear_create_issue", "title"): "생성할 이슈 제목을 지정해야 작업을 만들 수 있습니다.",
        ("linear_create_issue", "team_id"): "이슈를 생성할 팀을 지정해야 합니다.",
        ("linear_update_issue", "issue_id"): "수정할 대상 이슈를 식별해야 합니다.",
        ("linear_update_issue", "description"): "업데이트할 내용을 반영하려면 설명이 필요합니다.",
        ("linear_create_comment", "issue_id"): "댓글을 추가할 이슈를 식별해야 합니다.",
        ("linear_create_comment", "body"): "등록할 댓글 본문이 필요합니다.",
        ("notion_append_block_children", "block_id"): "본문을 추가할 대상 페이지를 알아야 합니다.",
        ("notion_append_block_children", "content"): "추가할 본문 내용이 필요합니다.",
        ("notion_query_data_source", "data_source_id"): "조회할 데이터소스를 식별해야 합니다.",
        ("notion_search", "query"): "검색할 키워드를 알아야 결과를 찾을 수 있습니다.",
    }
    return reasons.get((action_key, slot_key), f"요청을 실행하려면 `{slot_key}` 값이 필요합니다.")


def _has_keyed_slot_marker(text: str) -> bool:
    return bool(re.search(r"[0-9A-Za-z가-힣_]+\s*[:=]\s*", text or ""))


def _display_slot_name(action: str, slot_name: str) -> str:
    schema = get_action_slot_schema(action)
    if not schema:
        return slot_name
    aliases = schema.aliases.get(slot_name) or ()
    for alias in aliases:
        candidate = str(alias or "").strip()
        if candidate and re.search(r"[가-힣]", candidate):
            return candidate
    return aliases[0] if aliases else slot_name


def _build_validation_guide_message(action: str, slot_name: str) -> str:
    display_slot = _display_slot_name(action, slot_name)
    return (
        f"누락 항목: {display_slot}\n"
        f"입력 예시: {slot_prompt_example(action, slot_name)}\n"
        "다음 동작: 값을 보내주시면 이어서 실행합니다. (취소: `취소`)"
    )


def _is_slot_loop_enabled(settings, user_id: str) -> bool:
    if not bool(getattr(settings, "slot_loop_enabled", True)):
        return False
    rollout = int(getattr(settings, "slot_loop_rollout_percent", 100))
    rollout = max(0, min(100, rollout))
    if rollout >= 100:
        return True
    if rollout <= 0:
        return False
    key = (user_id or "").strip().encode("utf-8")
    bucket = sum(key) % 100 if key else 0
    return bucket < rollout


def _looks_like_identifier_value(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{32}", text):
        return True
    if re.fullmatch(r"[0-9a-fA-F\-]{36}", text):
        return True
    if re.fullmatch(r"[A-Za-z]{2,10}-\d{1,6}", text):
        return True
    return False


def _should_reask_low_confidence(
    *,
    action: str,
    slot_name: str,
    slot_value: object,
    confidence: float,
    user_text: str,
) -> bool:
    if confidence >= 0.8:
        return False
    if _has_keyed_slot_marker(user_text):
        return False
    schema = get_action_slot_schema(action)
    if schema is None:
        # 스키마가 없는 액션은 plain 응답도 수용한다.
        return False
    if slot_name.endswith("_id") and _looks_like_identifier_value(slot_value):
        return False
    return True


def _looks_like_slot_only_input(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if not _has_keyed_slot_marker(raw):
        return False
    lowered = raw.lower()
    service_tokens = ("notion", "노션", "linear", "리니어", "spotify", "스포티파이")
    action_tokens = ("생성", "수정", "삭제", "조회", "검색", "추가", "요약", "create", "update", "delete", "search")
    has_service_or_action = any(token in lowered for token in service_tokens) or any(token in lowered for token in action_tokens)
    return not has_service_or_action


def _apply_slot_loop_from_validation_error(
    *,
    execution: AgentExecutionResult,
    plan,
    plan_source: str,
    user_id: str,
    enabled: bool,
) -> None:
    if not enabled:
        return
    if execution.success or execution.artifacts.get("error_code") != "validation_error":
        return
    action = str(execution.artifacts.get("slot_action", "") or "").strip()
    missing_slot = str(execution.artifacts.get("missing_slot", "") or "").strip()
    task_id = str(execution.artifacts.get("slot_task_id", "") or "").strip()
    payload_json = str(execution.artifacts.get("slot_payload_json", "") or "").strip()
    if not (action and missing_slot):
        for step in execution.steps:
            detail = str(step.detail or "")
            match = re.search(r"([a-z_]+):VALIDATION_REQUIRED:([a-z_]+)", detail)
            if not match:
                continue
            action = action or match.group(1)
            missing_slot = missing_slot or match.group(2)
            task_id = task_id or action
            break
    if not (action and missing_slot and task_id):
        return

    payload = {}
    if payload_json:
        try:
            parsed = json.loads(payload_json)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = {}
    missing_slots = [slot.strip() for slot in str(execution.artifacts.get("missing_slots", "")).split(",") if slot.strip()]
    if not missing_slots:
        missing_slots = [missing_slot]
    plan.notes.append("slot_loop_started")
    plan.notes.append("slot_loop_restarted_from_validation_error")
    set_pending_action(
        user_id=user_id,
        intent=action,
        action=action,
        task_id=task_id,
        plan=plan,
        plan_source=plan_source,
        collected_slots=payload,
        missing_slots=missing_slots,
    )
    execution.user_message = (
        f"{_build_slot_question_message(action, missing_slot)}\n\n"
        f"{_build_validation_guide_message(action, missing_slot)}"
    )
    execution.artifacts["next_action"] = "provide_slot_value"


async def _try_resume_pending_action(
    *,
    user_id: str,
    user_text: str,
) -> AgentRunResult | None:
    pending = get_pending_action(user_id)
    if not pending:
        return None

    if _is_cancel_pending_text(user_text):
        clear_pending_action(user_id)
        pending.plan.notes.append("slot_loop_cancelled")
        execution = AgentExecutionResult(
            success=False,
            summary="보류 중인 작업을 취소했습니다.",
            user_message="보류 중이던 작업을 취소했습니다. 새 요청을 입력해주세요.",
            artifacts={"error_code": "cancelled"},
            steps=[AgentExecutionStep(name="pending_action_cancel", status="success", detail="user_cancelled")],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=pending.plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source=pending.plan_source,
        )

    if _looks_like_new_request(user_text):
        clear_pending_action(user_id)
        pending.plan.notes.append("slot_loop_replaced_new_request")
        return None

    if not pending.missing_slots:
        clear_pending_action(user_id)
        return None

    target_slot = pending.missing_slots[0]
    collected = collect_slots_from_user_reply(
        action=pending.action,
        user_text=user_text,
        collected_slots=pending.collected_slots,
        preferred_slot=target_slot,
    )
    pending.collected_slots = collected.collected_slots

    if collected.validation_errors:
        set_pending_action(
            user_id=pending.user_id,
            intent=pending.intent,
            action=pending.action,
            task_id=pending.task_id,
            plan=pending.plan,
            plan_source=pending.plan_source,
            collected_slots=pending.collected_slots,
            missing_slots=[target_slot],
        )
        pending.plan.notes.append("slot_loop_validation_error")
        execution = AgentExecutionResult(
            success=False,
            summary="입력 형식이 올바르지 않습니다.",
            user_message=(
                "입력 형식이 올바르지 않습니다.\n"
                f"- 오류: {collected.validation_errors[0]}\n"
                f"- 다시 입력 예시: {slot_prompt_example(pending.action, target_slot)}\n"
                f"- 다음 동작: 값을 다시 보내주시면 이어서 실행합니다. (취소: `취소`)"
            ),
            artifacts={
                "error_code": "validation_error",
                "missing_slot": target_slot,
                "slot_action": pending.action,
                "next_action": "provide_slot_value",
            },
            steps=[AgentExecutionStep(name="pending_action_validate", status="error", detail=collected.validation_errors[0])],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=pending.plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source=pending.plan_source,
        )

    confidence = float(collected.confidence_by_slot.get(target_slot, 1.0))
    if _should_reask_low_confidence(
        action=pending.action,
        slot_name=target_slot,
        slot_value=collected.collected_slots.get(target_slot),
        confidence=confidence,
        user_text=user_text,
    ):
        set_pending_action(
            user_id=pending.user_id,
            intent=pending.intent,
            action=pending.action,
            task_id=pending.task_id,
            plan=pending.plan,
            plan_source=pending.plan_source,
            collected_slots=pending.collected_slots,
            missing_slots=[target_slot],
        )
        pending.plan.notes.append("slot_loop_low_confidence_reask")
        execution = AgentExecutionResult(
            success=False,
            summary="입력 확인이 필요합니다.",
            user_message=(
                f"`{target_slot}` 값을 명확히 확인하기 위해 키-값 형식으로 다시 입력해주세요.\n"
                f"예시: {slot_prompt_example(pending.action, target_slot)}\n"
                "다음 동작: 위 형식으로 값을 보내주시면 이어서 실행합니다. (취소: `취소`)"
            ),
            artifacts={
                "error_code": "validation_error",
                "missing_slot": target_slot,
                "slot_action": pending.action,
                "next_action": "provide_slot_value",
            },
            steps=[AgentExecutionStep(name="pending_action_low_confidence", status="error", detail=f"slot={target_slot}")],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=pending.plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source=pending.plan_source,
        )

    if collected.missing_slots:
        schema = get_action_slot_schema(pending.action)
        auto_fill_slots = set(schema.auto_fill_slots) if schema else set()
        if auto_fill_slots and all(slot in auto_fill_slots for slot in collected.missing_slots):
            for task in pending.plan.tasks:
                if task.id == pending.task_id or (task.tool_name or "") == pending.action:
                    task.payload = {**(task.payload or {}), **pending.collected_slots}
                    break
            clear_pending_action(user_id)
            execution = await execute_agent_plan(user_id=user_id, plan=pending.plan)
            settings = get_settings()
            finalized_message, finalizer_mode = _apply_response_finalizer_template(execution=execution, settings=settings)
            execution.user_message = finalized_message
            if finalizer_mode != "disabled":
                pending.plan.notes.append(f"response_finalizer={finalizer_mode}")
            pending.plan.notes.append("pending_action_autofill_retry")
            pending.plan.notes.append("slot_loop_autofill_retry")
            _apply_slot_loop_from_validation_error(
                execution=execution,
                plan=pending.plan,
                plan_source=pending.plan_source,
                user_id=user_id,
                enabled=True,
            )
            return AgentRunResult(
                ok=execution.success,
                stage="execution",
                plan=pending.plan,
                result_summary=execution.summary,
                execution=execution,
                plan_source=pending.plan_source,
            )

        next_slot = collected.ask_next_slot or collected.missing_slots[0]
        set_pending_action(
            user_id=pending.user_id,
            intent=pending.intent,
            action=pending.action,
            task_id=pending.task_id,
            plan=pending.plan,
            plan_source=pending.plan_source,
            collected_slots=pending.collected_slots,
            missing_slots=collected.missing_slots,
        )
        pending.plan.notes.append(f"slot_loop_turn:{next_slot}")
        execution = AgentExecutionResult(
            success=False,
            summary="추가 입력이 필요합니다.",
            user_message=f"{_build_slot_question_message(pending.action, next_slot)}\n\n{_build_validation_guide_message(pending.action, next_slot)}",
            artifacts={
                "error_code": "validation_error",
                "missing_slot": next_slot,
                "slot_action": pending.action,
                "next_action": "provide_slot_value",
            },
            steps=[AgentExecutionStep(name="pending_action_ask_next", status="error", detail=f"missing_slot:{next_slot}")],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=pending.plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source=pending.plan_source,
        )

    task_found = False
    for task in pending.plan.tasks:
        if task.id == pending.task_id or (task.tool_name or "") == pending.action:
            task.payload = {**(task.payload or {}), **pending.collected_slots}
            task_found = True
            break
    if not task_found:
        extra = " ".join(f"{k}: {v}" for k, v in pending.collected_slots.items() if str(v).strip())
        if extra:
            pending.plan.user_text = f"{pending.plan.user_text} {extra}".strip()
    clear_pending_action(user_id)

    execution = await execute_agent_plan(user_id=user_id, plan=pending.plan)
    settings = get_settings()
    finalized_message, finalizer_mode = _apply_response_finalizer_template(execution=execution, settings=settings)
    execution.user_message = finalized_message
    if finalizer_mode != "disabled":
        pending.plan.notes.append(f"response_finalizer={finalizer_mode}")
    pending.plan.notes.append("pending_action_resumed")
    pending.plan.notes.append("slot_loop_completed")
    return AgentRunResult(
        ok=execution.success,
        stage="execution",
        plan=pending.plan,
        result_summary=execution.summary,
        execution=execution,
        plan_source=pending.plan_source,
    )


async def run_agent_analysis(user_text: str, connected_services: list[str], user_id: str) -> AgentRunResult:
    """Run the agent flow with planning + execution.

    Stage coverage:
    1) requirement extraction
    2) service/API selection
    3) workflow generation
    4) workflow execution
    5) result summary and return payload generation
    """
    settings = get_settings()
    slot_loop_enabled = _is_slot_loop_enabled(settings, user_id)
    if slot_loop_enabled:
        resumed = await _try_resume_pending_action(user_id=user_id, user_text=user_text)
        if resumed is not None:
            return resumed

    else:
        _ = get_pending_action(user_id)
        if _ is not None:
            clear_pending_action(user_id)

    if slot_loop_enabled and _looks_like_slot_only_input(user_text):
        plan = build_agent_plan(user_text=user_text, connected_services=connected_services)
        plan.notes.append("slot_loop_orphan_slot_input")
        plan.notes.append(f"slot_loop_enabled={1 if slot_loop_enabled else 0}")
        execution = AgentExecutionResult(
            success=False,
            summary="진행 중인 작업을 찾지 못했습니다.",
            user_message=(
                "현재 이어서 입력할 보류 작업이 없습니다.\n"
                "먼저 작업 요청을 입력해주세요.\n"
                "예: `linear 이슈 생성해줘`"
            ),
            artifacts={"error_code": "validation_error", "next_action": "start_new_request"},
            steps=[AgentExecutionStep(name="slot_loop_orphan_slot_input", status="error", detail="no_pending_action")],
        )
        return AgentRunResult(
            ok=False,
            stage="validation",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="rule",
        )

    llm_planner_enabled = bool(getattr(settings, "llm_planner_enabled", False))

    is_data_source_query, data_source_state = _parse_data_source_query_state(user_text)
    # Regex 기반 데이터소스 사전 검증은 rule planner fallback일 때만 강제한다.
    if (not llm_planner_enabled) and is_data_source_query and data_source_state in {"missing", "invalid"}:
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

    planner_rule_fallback_enabled = bool(getattr(settings, "llm_planner_rule_fallback_enabled", True))

    plan_source = "rule"
    llm_plan, llm_error = await try_build_agent_plan_with_llm(
        user_text=user_text,
        connected_services=connected_services,
    )
    if llm_plan:
        plan = llm_plan
        plan_source = "llm"
        realigned_tools = _realign_selected_tools_from_tasks(plan)
        if realigned_tools != plan.selected_tools:
            plan.selected_tools = realigned_tools
            plan.notes.append("plan_tools_aligned_to_tasks")
        enriched_tools, post_enrich_error = _enrich_plan_tools_with_registry(
            user_text=user_text,
            selected_tools=plan.selected_tools,
            target_services=plan.target_services,
        )
        if enriched_tools != plan.selected_tools:
            plan.selected_tools = enriched_tools
            plan.notes.append("plan_enriched_from_llm")
        if post_enrich_error:
            if planner_rule_fallback_enabled:
                # If essential tool is still missing after enrichment, fall back to rule planner.
                plan = build_agent_plan(user_text=user_text, connected_services=connected_services)
                plan_source = "rule"
                plan.notes.append(f"plan_realign_from_llm:{post_enrich_error}")
            else:
                plan.notes.append(f"plan_realign_skipped:{post_enrich_error}")
    else:
        if bool(getattr(settings, "llm_planner_enabled", False)) and not planner_rule_fallback_enabled:
            empty_plan = AgentRunResult(
                ok=False,
                stage="planning",
                plan=build_agent_plan(user_text=user_text, connected_services=connected_services),
                result_summary="LLM planner가 계획을 생성하지 못해 실행을 중단했습니다.",
                execution=AgentExecutionResult(
                    success=False,
                    user_message=(
                        "현재는 자율 LLM planner 우선 모드입니다.\n"
                        "계획 생성에 실패해 실행을 중단했습니다. 잠시 후 다시 시도해주세요."
                    ),
                    summary="LLM planner planning 실패",
                    artifacts={"error_code": "llm_planner_failed"},
                    steps=[AgentExecutionStep(name="planning", status="error", detail=llm_error or "llm_plan_missing")],
                ),
                plan_source="llm",
            )
            empty_plan.plan.notes.append(f"llm_planner_failed_no_rule_fallback:{llm_error or 'llm_plan_missing'}")
            return empty_plan
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

    execution = None
    autonomous_enabled = bool(getattr(settings, "llm_autonomous_enabled", False))
    hybrid_executor_first = bool(getattr(settings, "llm_hybrid_executor_first", False))
    autonomous_strict = bool(getattr(settings, "llm_autonomous_strict", False))
    autonomous_retry_once = bool(getattr(settings, "llm_autonomous_limit_retry_once", True))
    autonomous_rule_fallback_enabled = bool(getattr(settings, "llm_autonomous_rule_fallback_enabled", True))
    autonomous_rule_fallback_mutation_enabled = bool(
        getattr(settings, "llm_autonomous_rule_fallback_mutation_enabled", False)
    )
    autonomous_progressive_no_fallback_enabled = bool(
        getattr(settings, "llm_autonomous_progressive_no_fallback_enabled", True)
    )
    autonomous: AgentExecutionResult | None = None

    if autonomous_enabled and not hybrid_executor_first:
        try:
            autonomous = await run_autonomous_loop(user_id=user_id, plan=plan)
        except Exception as exc:
            autonomous = AgentExecutionResult(
                success=False,
                user_message="자율 실행 중 네트워크 오류가 발생했습니다. 규칙 기반 실행으로 전환합니다.",
                summary="자율 루프 예외로 fallback",
                artifacts={"error_code": "autonomous_runtime_error"},
                steps=[AgentExecutionStep(name="autonomous_runtime_exception", status="error", detail=exc.__class__.__name__)],
            )
            plan.notes.append(f"autonomous_exception={exc.__class__.__name__}")
        if autonomous.success:
            execution = autonomous
            plan.notes.append("execution=autonomous")
        else:
            error_code = str(autonomous.artifacts.get("error_code", "unknown"))
            plan.notes.append(f"autonomous_error={error_code}")
            metrics = _autonomous_metrics(autonomous, plan)
            plan.notes.append(
                "autonomous_metrics="
                f"tool_error_rate:{metrics['tool_error_rate']:.2f},"
                f"replan_ratio:{metrics['replan_ratio']:.2f},"
                f"cross_service_blocks:{int(metrics['cross_service_blocks'])}"
            )
            guardrail_reason = _autonomous_guardrail_degrade_reason(settings, metrics)
            if guardrail_reason:
                plan.notes.append(f"autonomous_guardrail_degrade:{guardrail_reason}")

            retryable_errors = {
                "turn_limit",
                "tool_call_limit",
                "replan_limit",
                "timeout",
                "verification_failed",
                "unsupported_action",
            }
            if autonomous_retry_once and error_code in retryable_errors and not guardrail_reason:
                plan.notes.append("autonomous_retry=1")
                verification_reason = str(autonomous.artifacts.get("verification_reason", "") or "").strip() or None
                plan.notes.append(f"autonomous_retry_tuning_rule={_retry_tuning_rule(error_code, verification_reason)}")
                retry_overrides = _build_retry_overrides(
                    settings=settings,
                    user_text=user_text,
                    error_code=error_code,
                    verification_reason=verification_reason,
                )
                plan.notes.append(
                    "autonomous_retry_budget="
                    f"turns:{retry_overrides['max_turns_override']},"
                    f"tools:{retry_overrides['max_tool_calls_override']},"
                    f"timeout:{retry_overrides['timeout_sec_override']},"
                    f"replan:{retry_overrides['replan_limit_override']},"
                    f"candidates:{retry_overrides['max_candidates_override']}"
                )
                try:
                    retry = await run_autonomous_loop(
                        user_id=user_id,
                        plan=plan,
                        max_turns_override=retry_overrides["max_turns_override"],
                        max_tool_calls_override=retry_overrides["max_tool_calls_override"],
                        timeout_sec_override=retry_overrides["timeout_sec_override"],
                        replan_limit_override=retry_overrides["replan_limit_override"],
                        max_candidates_override=retry_overrides["max_candidates_override"],
                        extra_guidance=_build_retry_guidance(autonomous, error_code),
                    )
                except Exception as exc:
                    plan.notes.append(f"autonomous_retry_exception={exc.__class__.__name__}")
                    retry = AgentExecutionResult(
                        success=False,
                        user_message="자율 재시도 중 네트워크 오류가 발생했습니다. 규칙 기반 실행으로 전환합니다.",
                        summary="자율 재시도 예외로 fallback",
                        artifacts={"error_code": "autonomous_runtime_error"},
                        steps=[
                            AgentExecutionStep(
                                name="autonomous_retry_runtime_exception",
                                status="error",
                                detail=exc.__class__.__name__,
                            )
                        ],
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

            if execution is None and not autonomous_rule_fallback_enabled:
                execution = autonomous
                plan.notes.append("execution=autonomous_no_rule_fallback")

            if (
                execution is None
                and autonomous is not None
                and not autonomous_rule_fallback_mutation_enabled
                and _is_mutation_intent(user_text)
            ):
                execution = autonomous
                plan.notes.append("execution=autonomous_no_rule_fallback_mutation")

            if execution is None and autonomous is not None and autonomous_progressive_no_fallback_enabled:
                error_code = str(autonomous.artifacts.get("error_code", "unknown"))
                progressive_errors = {
                    "verification_failed",
                    "turn_limit",
                    "tool_call_limit",
                    "timeout",
                    "replan_limit",
                }
                successful_tools = _autonomous_successful_tool_calls(autonomous)
                if successful_tools >= 1 and error_code in progressive_errors:
                    execution = autonomous
                    plan.notes.append(f"execution=autonomous_progress_guard:{error_code}:{successful_tools}")

            if execution is None:
                plan.notes.append("execution=autonomous_fallback")
    elif hybrid_executor_first:
        plan.notes.append("execution=deterministic_first")

    if execution is None:
        execution = await execute_agent_plan(user_id=user_id, plan=plan)

    finalized_message, finalizer_mode = _apply_response_finalizer_template(execution=execution, settings=settings)
    execution.user_message = finalized_message
    if finalizer_mode != "disabled":
        plan.notes.append(f"response_finalizer={finalizer_mode}")
    plan.notes.append(f"slot_loop_enabled={1 if slot_loop_enabled else 0}")
    _apply_slot_loop_from_validation_error(
        execution=execution,
        plan=plan,
        plan_source=plan_source,
        user_id=user_id,
        enabled=slot_loop_enabled,
    )

    summary = execution.summary
    return AgentRunResult(
        ok=execution.success,
        stage="execution",
        plan=plan,
        result_summary=summary,
        execution=execution,
        plan_source=plan_source,
    )
