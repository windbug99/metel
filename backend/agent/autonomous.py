from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from fastapi import HTTPException

from agent.registry import load_registry
from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan
from app.core.config import get_settings


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _normalize_action(payload: dict[str, Any]) -> str:
    action = str(payload.get("action", "")).strip().lower()
    if action in {"tool", "call_tool"}:
        return "tool_call"
    if action in {"done", "finish"}:
        return "final"
    return action


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _rank_tools_by_intent(tools: list[str], plan: AgentPlan) -> list[str]:
    text = (plan.user_text or "").lower()
    workflow_text = " ".join(plan.workflow_steps).lower()
    merged = f"{text} {workflow_text}"

    def score(tool_name: str) -> int:
        name = tool_name.lower()
        s = 0

        if "search" in name:
            s += 2
        if any(token in merged for token in ("조회", "검색", "목록", "show", "list", "find")) and "search" in name:
            s += 4

        if any(token in merged for token in ("요약", "summary", "출력", "본문", "상위")) and (
            "retrieve_page" in name or "retrieve_block_children" in name or "retrieve_page_property_item" in name
        ):
            s += 6

        if any(token in merged for token in ("생성", "만들", "create")) and (
            "create" in name or "append_block_children" in name
        ):
            s += 8

        if any(token in merged for token in ("추가", "append", "추가해줘")) and "append_block_children" in name:
            s += 8

        if any(token in merged for token in ("변경", "수정", "바꿔", "rename", "update")) and "update_page" in name:
            s += 8

        if any(token in merged for token in ("삭제", "아카이브", "archive", "delete")) and (
            "delete_block" in name or "update_page" in name
        ):
            s += 10

        if any(token in merged for token in ("데이터소스", "data source", "data_source")) and (
            "query_data_source" in name or "retrieve_data_source" in name
        ):
            s += 10

        return s

    return sorted(tools, key=lambda item: score(item), reverse=True)


def _plan_needs_lookup(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(keyword in text for keyword in ("조회", "검색", "목록", "보여", "출력", "요약"))


def _plan_needs_creation(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(keyword in text for keyword in ("생성", "만들", "작성", "추가", "변경", "수정", "삭제", "아카이브"))


def _plan_needs_new_artifact(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(keyword in text for keyword in ("생성", "만들", "작성"))


def _compact_tool_result(data: Any, max_chars: int = 1200) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False)
    except TypeError:
        text = str(data)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "...(truncated)"


def _has_new_artifact_reference(history: list[dict[str, Any]]) -> bool:
    for item in history:
        if item.get("action") != "tool_call" or item.get("status") != "success":
            continue
        result = item.get("tool_result")
        if isinstance(result, dict):
            if result.get("id") or result.get("url"):
                return True
            data = result.get("data")
            if isinstance(data, dict) and (data.get("id") or data.get("url")):
                return True
    return False


def _verify_completion(plan: AgentPlan, history: list[dict[str, Any]], final_response: str) -> tuple[bool, str]:
    tool_success_names = [
        item.get("tool_name", "")
        for item in history
        if item.get("action") == "tool_call" and item.get("status") == "success"
    ]
    if _plan_needs_lookup(plan) and not tool_success_names:
        return False, "lookup_requires_tool_call"
    if _plan_needs_move(plan) and not _has_successful_tool(history, "update_page"):
        return False, "move_requires_update_page"
    if _plan_needs_append(plan):
        append_success_count = _count_successful_tool(history, "append_block_children")
        if append_success_count == 0:
            return False, "append_requires_append_block_children"
        target_count = _estimate_append_target_count(plan.user_text)
        if target_count >= 2 and append_success_count < target_count:
            return False, "append_requires_multiple_targets"
    if _plan_needs_rename(plan) and not _has_successful_tool(history, "update_page"):
        return False, "rename_requires_update_page"
    if _plan_needs_archive(plan) and not _has_successful_tool(history, "update_page", "delete_block", "archive"):
        return False, "archive_requires_archive_tool"
    if _plan_needs_creation(plan) and not any(
        any(token in name for token in ("create", "append", "update", "delete", "archive"))
        for name in tool_success_names
    ):
        return False, "mutation_requires_mutation_tool"
    if _plan_needs_new_artifact(plan) and not _has_new_artifact_reference(history):
        return False, "creation_requires_artifact_reference"
    if not final_response.strip():
        return False, "empty_final_response"
    return True, "ok"


def _has_successful_tool(history: list[dict[str, Any]], *tokens: str) -> bool:
    for item in history:
        if item.get("action") != "tool_call" or item.get("status") != "success":
            continue
        name = str(item.get("tool_name", ""))
        if any(token in name for token in tokens):
            return True
    return False


def _count_successful_tool(history: list[dict[str, Any]], *tokens: str) -> int:
    count = 0
    for item in history:
        if item.get("action") != "tool_call" or item.get("status") != "success":
            continue
        name = str(item.get("tool_name", ""))
        if any(token in name for token in tokens):
            count += 1
    return count


def _is_mutation_tool_name(tool_name: str) -> bool:
    lower = tool_name.lower()
    return any(token in lower for token in ("create", "append", "update", "delete", "archive", "move"))


def _has_same_successful_mutation_call(
    history: list[dict[str, Any]],
    *,
    tool_name: str,
    tool_input: dict[str, Any],
) -> bool:
    if not _is_mutation_tool_name(tool_name):
        return False
    try:
        needle = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    except TypeError:
        needle = str(tool_input)
    for item in history:
        if item.get("action") != "tool_call" or item.get("status") != "success":
            continue
        if item.get("tool_name") != tool_name:
            continue
        try:
            prev = json.dumps(item.get("tool_input", {}), ensure_ascii=False, sort_keys=True)
        except TypeError:
            prev = str(item.get("tool_input", {}))
        if prev == needle:
            return True
    return False


def _has_same_failed_validation_call(
    history: list[dict[str, Any]],
    *,
    tool_name: str,
    tool_input: dict[str, Any],
) -> bool:
    try:
        needle = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    except TypeError:
        needle = str(tool_input)

    for item in history:
        if item.get("action") != "tool_call" or item.get("status") != "error":
            continue
        if item.get("tool_name") != tool_name:
            continue
        err = str(item.get("error", "") or "")
        if "VALIDATION_" not in err:
            continue
        try:
            prev = json.dumps(item.get("tool_input", {}), ensure_ascii=False, sort_keys=True)
        except TypeError:
            prev = str(item.get("tool_input", {}))
        if prev == needle:
            return True
    return False


def _plan_needs_move(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(token in text for token in ("이동", "옮겨", "옮기", "이동시키")) and any(
        token in text for token in ("하위", "아래", "밑")
    )


def _plan_needs_append(plan: AgentPlan) -> bool:
    text = plan.user_text
    return "추가" in text and any(token in text for token in ("페이지에", "문서에"))


def _extract_quoted_targets(text: str) -> list[str]:
    results: list[str] = []
    for match in re.finditer(r'"([^"]+)"|\'([^\']+)\'', text):
        value = match.group(1) or match.group(2)
        if value:
            cleaned = value.strip()
            if cleaned:
                results.append(cleaned)
    return results


def _estimate_append_target_count(text: str) -> int:
    quoted = _extract_quoted_targets(text)
    if len(quoted) >= 2:
        return len(quoted)
    normalized = text.lower()
    if "각각" in normalized and any(token in normalized for token in (",", "와", "그리고")):
        return 2
    return 1


def _intent_support_tools(plan: AgentPlan, service_tools: list[Any]) -> list[str]:
    support: list[str] = []

    def _pick(*tokens: str) -> list[str]:
        matched: list[str] = []
        for tool in service_tools:
            name = str(tool.tool_name)
            if any(token in name for token in tokens):
                matched.append(name)
        return matched

    if _plan_needs_lookup(plan):
        support.extend(_pick("search", "retrieve_page", "retrieve_block_children"))
    if _plan_needs_append(plan):
        support.extend(_pick("search", "retrieve_page", "retrieve_block_children", "append_block_children"))
    if _plan_needs_move(plan):
        support.extend(_pick("search", "retrieve_page", "update_page", "create_page", "append_block_children", "delete"))
    if _plan_needs_archive(plan):
        support.extend(_pick("search", "update_page", "delete"))
    if _plan_needs_rename(plan):
        support.extend(_pick("search", "update_page"))

    if _plan_needs_creation(plan):
        support.extend(_pick("create", "append", "update", "delete", "archive"))

    return _dedupe_keep_order(support)


def _plan_needs_rename(plan: AgentPlan) -> bool:
    text = plan.user_text
    return "제목" in text and any(token in text for token in ("변경", "수정", "바꿔", "바꾸", "rename"))


def _plan_needs_archive(plan: AgentPlan) -> bool:
    text = plan.user_text.lower()
    return any(token in text for token in ("삭제", "지워", "아카이브", "archive"))


async def _request_autonomous_action(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    openai_api_key: str | None,
    google_api_key: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if provider == "openai":
        if not openai_api_key:
            return None, "openai_api_key_missing"
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            return None, f"http_{response.status_code}"
        content = ((response.json().get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        parsed = _extract_json_object(content)
        if not parsed:
            return None, "invalid_json"
        return parsed, None

    if provider == "gemini":
        if not google_api_key:
            return None, "google_api_key_missing"
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=google_api_key)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if response.status_code >= 400:
            return None, f"http_{response.status_code}"
        parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        content = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        parsed = _extract_json_object(content)
        if not parsed:
            return None, "invalid_json"
        return parsed, None

    return None, "unsupported_provider"


async def _choose_next_action(
    *,
    plan: AgentPlan,
    allowed_tools: list[str],
    tool_schema_snippet: str,
    history: list[dict[str, Any]],
    extra_guidance: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    settings = get_settings()
    attempts: list[tuple[str, str]] = []

    primary_provider = (settings.llm_planner_provider or "openai").strip().lower()
    primary_model = (settings.llm_planner_model or "gpt-4o-mini").strip()
    if primary_provider and primary_model:
        attempts.append((primary_provider, primary_model))

    fallback_provider = (settings.llm_planner_fallback_provider or "").strip().lower()
    fallback_model = (settings.llm_planner_fallback_model or "").strip()
    if fallback_provider and fallback_model:
        attempts.append((fallback_provider, fallback_model))

    if not attempts:
        attempts = [("openai", "gpt-4o-mini"), ("gemini", "gemini-2.5-flash-lite")]

    history_text = json.dumps(history[-8:], ensure_ascii=False)
    system_prompt = (
        "당신은 metel의 실행 에이전트입니다. 반드시 JSON object만 출력하세요. "
        "도구 호출은 허용된 tool_name만 사용하고, tool_input은 JSON object로 작성하세요. "
        "핵심 원칙: 작업이 끝나기 전에는 final을 선택하지 말고 필요한 tool_call을 우선 수행하세요. "
        "이미 성공한 mutation 도구(create/append/update/delete)를 동일 입력으로 반복 호출하지 마세요."
    )
    user_prompt = (
        f"사용자 요청: {plan.user_text}\n"
        f"요구사항: {[item.summary for item in plan.requirements]}\n"
        f"워크플로우 단계: {plan.workflow_steps}\n"
        f"허용 도구: {allowed_tools}\n"
        f"도구 스키마 요약:\n{tool_schema_snippet}\n"
        f"현재 실행 이력(JSON): {history_text}\n\n"
        "다음 중 하나를 선택하세요.\n"
        "1) tool_call: 다음 도구 1개 호출\n"
        "2) final: 작업 완료, 최종 답변\n"
        "3) replan: 계획 수정(허용 도구 재정렬 제안)\n\n"
        "JSON 형식:\n"
        "{\n"
        '  "action": "tool_call|final|replan",\n'
        '  "reason": "한줄 설명",\n'
        '  "tool_name": "notion_search",\n'
        '  "tool_input": {},\n'
        '  "final_response": "사용자에게 보여줄 최종 메시지",\n'
        '  "updated_selected_tools": ["notion_search"]\n'
        "}\n"
    )
    if extra_guidance:
        user_prompt += f"\n재시도 가이드:\n{extra_guidance}\n"

    errors: list[str] = []
    for provider, model in attempts:
        payload, err = await _request_autonomous_action(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
        )
        if payload:
            payload["_provider"] = provider
            payload["_model"] = model
            return payload, None
        errors.append(f"{provider}:{err}")
    return None, "|".join(errors) if errors else "llm_action_failed"


async def _llm_verify_completion(
    *,
    plan: AgentPlan,
    history: list[dict[str, Any]],
    final_response: str,
) -> tuple[str, str, str]:
    settings = get_settings()
    if not bool(getattr(settings, "llm_autonomous_verifier_enabled", False)):
        return "skipped", "disabled", ""
    fail_closed = bool(getattr(settings, "llm_autonomous_verifier_fail_closed", False))
    require_tool_evidence = bool(getattr(settings, "llm_autonomous_verifier_require_tool_evidence", True))
    history_limit = max(3, min(20, int(getattr(settings, "llm_autonomous_verifier_max_history", 8))))

    attempts: list[tuple[str, str]] = []
    primary_provider = (settings.llm_planner_provider or "openai").strip().lower()
    primary_model = (settings.llm_planner_model or "gpt-4o-mini").strip()
    if primary_provider and primary_model:
        attempts.append((primary_provider, primary_model))
    fallback_provider = (settings.llm_planner_fallback_provider or "").strip().lower()
    fallback_model = (settings.llm_planner_fallback_model or "").strip()
    if fallback_provider and fallback_model:
        attempts.append((fallback_provider, fallback_model))
    if not attempts:
        attempts = [("openai", "gpt-4o-mini"), ("gemini", "gemini-2.5-flash-lite")]

    compact_history = []
    for item in history[-history_limit:]:
        compact_history.append(
            {
                "turn": item.get("turn"),
                "action": item.get("action"),
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
                "error": item.get("error"),
                "tool_result_summary": item.get("tool_result_summary"),
            }
        )

    system_prompt = (
        "당신은 실행 결과 검증기입니다. 반드시 JSON object만 출력하세요. "
        "tool 실행 근거와 final 응답 일치 여부만 판정하세요."
    )
    if require_tool_evidence:
        system_prompt += " final 응답의 핵심 주장마다 tool 근거가 없으면 fail로 판정하세요."
    user_prompt = (
        f"사용자 요청: {plan.user_text}\n"
        f"요구사항: {[item.summary for item in plan.requirements]}\n"
        f"도구 실행 요약(JSON): {json.dumps(compact_history, ensure_ascii=False)}\n"
        f"최종 응답: {final_response}\n\n"
        "JSON 형식:\n"
        "{\n"
        '  "verdict": "pass|fail",\n'
        '  "reason": "짧은 사유"\n'
        "}\n"
    )

    errors: list[str] = []
    for provider, model in attempts:
        payload, err = await _request_autonomous_action(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
        )
        if not payload:
            errors.append(f"{provider}:{err}")
            continue
        verdict = str(payload.get("verdict", "")).strip().lower()
        reason = str(payload.get("reason", "")).strip() or "llm_verifier_no_reason"
        if verdict in {"pass", "fail"}:
            return verdict, reason, f"{provider}:{model}"
        errors.append(f"{provider}:invalid_verdict")
    if fail_closed:
        return "fail", "verifier_unavailable_fail_closed", ""
    return "skipped", "|".join(errors) if errors else "llm_verifier_unavailable", ""


async def run_autonomous_loop(
    user_id: str,
    plan: AgentPlan,
    *,
    max_turns_override: int | None = None,
    max_tool_calls_override: int | None = None,
    timeout_sec_override: int | None = None,
    replan_limit_override: int | None = None,
    max_candidates_override: int | None = None,
    extra_guidance: str | None = None,
) -> AgentExecutionResult:
    settings = get_settings()
    strict_tool_scope = bool(getattr(settings, "llm_autonomous_strict_tool_scope", True))
    max_turns = max(1, max_turns_override if max_turns_override is not None else settings.llm_autonomous_max_turns)
    max_tool_calls = max(
        1, max_tool_calls_override if max_tool_calls_override is not None else settings.llm_autonomous_max_tool_calls
    )
    timeout_sec = max(5, timeout_sec_override if timeout_sec_override is not None else settings.llm_autonomous_timeout_sec)
    replan_limit = max(0, replan_limit_override if replan_limit_override is not None else settings.llm_autonomous_replan_limit)

    registry = load_registry()
    service_tools = []
    for service in plan.target_services:
        service_tools.extend(registry.list_tools(service))
    if not service_tools and plan.selected_tools:
        service_tools = [registry.get_tool(name) for name in plan.selected_tools]

    selected_known = [name for name in plan.selected_tools if any(tool.tool_name == name for tool in service_tools)]
    selected_tools_lock = set(selected_known)
    if selected_known:
        if strict_tool_scope:
            # Hybrid mode default: execute only planner-approved tools.
            allowed_tools = _dedupe_keep_order(selected_known)
        else:
            # Keep planner tools primary, but add minimal mutation fallback tools when request clearly needs mutation.
            mutation_fallback = []
            if _plan_needs_creation(plan):
                mutation_fallback = [
                    tool.tool_name
                    for tool in service_tools
                    if any(token in tool.tool_name for token in ("create", "append", "update", "delete", "archive"))
                ]
            support_tools = _intent_support_tools(plan, service_tools)
            allowed_tools = _dedupe_keep_order(selected_known + support_tools + mutation_fallback)
    else:
        support_tools = _intent_support_tools(plan, service_tools)
        allowed_tools = _dedupe_keep_order(support_tools + [tool.tool_name for tool in service_tools])
    allowed_tools = _rank_tools_by_intent(allowed_tools, plan)

    # Reduce tool fan-out to improve autonomous convergence (while preserving planner-selected tools).
    max_candidates = max_candidates_override if max_candidates_override is not None else 8
    if max_candidates_override is None and _estimate_append_target_count(plan.user_text) >= 2:
        max_candidates = 12
    max_candidates = max(2, int(max_candidates))
    if len(allowed_tools) > max_candidates:
        pinned = [name for name in plan.selected_tools if name in allowed_tools]
        compact = _dedupe_keep_order(pinned + allowed_tools)
        allowed_tools = compact[:max_candidates]

    tools = [registry.get_tool(name) for name in allowed_tools]
    tool_schema_snippet = "\n".join(
        f"- {tool.tool_name}: {tool.description} / schema={json.dumps(tool.input_schema, ensure_ascii=False)}"
        for tool in tools
    )

    if not allowed_tools:
        return AgentExecutionResult(
            success=False,
            summary="자율 루프 실행에 필요한 도구가 없습니다.",
            user_message="현재 요청에서 실행 가능한 도구를 찾지 못했습니다.",
            artifacts={"error_code": "no_tools_for_autonomous"},
            steps=[AgentExecutionStep(name="autonomous_init", status="error", detail="no_selected_tools")],
        )

    steps: list[AgentExecutionStep] = [
        AgentExecutionStep(name="autonomous_init", status="success", detail=f"tools={len(allowed_tools)}")
    ]
    history: list[dict[str, Any]] = []
    tool_calls = 0
    replan_count = 0
    invalid_action_count = 0
    llm_provider: str | None = None
    llm_model: str | None = None
    started = time.monotonic()

    for turn in range(1, max_turns + 1):
        if time.monotonic() - started > timeout_sec:
            steps.append(AgentExecutionStep(name="budget_timeout", status="error", detail=f"{timeout_sec}s"))
            return AgentExecutionResult(
                success=False,
                summary="자율 루프 제한 시간 초과",
                user_message="요청 처리 시간이 초과되었습니다. 다시 시도해주세요.",
                artifacts={"error_code": "timeout", "autonomous": "true"},
                steps=steps,
            )
        if tool_calls >= max_tool_calls:
            steps.append(AgentExecutionStep(name="budget_tool_calls", status="error", detail=f"{tool_calls}"))
            return AgentExecutionResult(
                success=False,
                summary="자율 루프 도구 호출 제한 초과",
                user_message="요청 처리 중 도구 호출 한도를 초과했습니다. 요청을 더 구체적으로 입력해주세요.",
                artifacts={"error_code": "tool_call_limit", "autonomous": "true"},
                steps=steps,
            )

        action_payload, action_error = await _choose_next_action(
            plan=plan,
            allowed_tools=allowed_tools,
            tool_schema_snippet=tool_schema_snippet,
            history=history,
            extra_guidance=extra_guidance,
        )
        if not action_payload:
            steps.append(AgentExecutionStep(name=f"turn_{turn}_action", status="error", detail=action_error or "unknown"))
            return AgentExecutionResult(
                success=False,
                summary="자율 계획 생성 실패",
                user_message="요청 계획을 생성하지 못했습니다. 잠시 후 다시 시도해주세요.",
                artifacts={"error_code": "autonomous_planning_failed", "autonomous": "true"},
                steps=steps,
            )

        action = _normalize_action(action_payload)
        reason = str(action_payload.get("reason", "")).strip()
        payload_provider = str(action_payload.get("_provider", "")).strip()
        payload_model = str(action_payload.get("_model", "")).strip()
        if payload_provider:
            llm_provider = payload_provider
        if payload_model:
            llm_model = payload_model
        steps.append(AgentExecutionStep(name=f"turn_{turn}_action", status="success", detail=f"{action}:{reason}"))

        if action == "final":
            final_response = str(action_payload.get("final_response", "")).strip()
            if not final_response:
                final_response = "작업을 완료했습니다."
            verified, verify_reason = _verify_completion(plan, history, final_response)
            if not verified:
                steps.append(AgentExecutionStep(name=f"turn_{turn}_verify", status="error", detail=verify_reason))
                history.append({"turn": turn, "action": "verify", "status": "error", "detail": verify_reason})
                if replan_count < replan_limit:
                    replan_count += 1
                    history.append({"turn": turn, "action": "replan", "status": "forced", "reason": verify_reason})
                    continue
                return AgentExecutionResult(
                    success=False,
                    summary="자율 루프 완료 검증 실패",
                    user_message="요청 처리 결과를 검증하지 못했습니다. 요청을 조금 더 구체적으로 입력해주세요.",
                    artifacts={
                        "error_code": "verification_failed",
                        "verification_reason": verify_reason,
                        "autonomous": "true",
                        "llm_provider": llm_provider or "",
                        "llm_model": llm_model or "",
                    },
                    steps=steps,
                )
            llm_verdict, llm_reason, llm_verifier_meta = await _llm_verify_completion(
                plan=plan,
                history=history,
                final_response=final_response,
            )
            if llm_verdict == "fail":
                verify_reason = f"llm_verifier_rejected:{llm_reason}"
                steps.append(AgentExecutionStep(name=f"turn_{turn}_verify_llm", status="error", detail=verify_reason))
                history.append({"turn": turn, "action": "verify_llm", "status": "error", "detail": verify_reason})
                if replan_count < replan_limit:
                    replan_count += 1
                    history.append({"turn": turn, "action": "replan", "status": "forced", "reason": verify_reason})
                    continue
                return AgentExecutionResult(
                    success=False,
                    summary="자율 루프 완료 검증 실패",
                    user_message="요청 처리 결과를 검증하지 못했습니다. 요청을 조금 더 구체적으로 입력해주세요.",
                    artifacts={
                        "error_code": "verification_failed",
                        "verification_reason": verify_reason,
                        "autonomous": "true",
                        "llm_provider": llm_provider or "",
                        "llm_model": llm_model or "",
                        "llm_verifier": llm_verifier_meta,
                    },
                    steps=steps,
                )
            if llm_verdict == "pass":
                steps.append(AgentExecutionStep(name=f"turn_{turn}_verify_llm", status="success", detail=llm_reason))
            elif llm_verdict == "skipped":
                steps.append(AgentExecutionStep(name=f"turn_{turn}_verify_llm", status="success", detail=f"skipped:{llm_reason}"))
            steps.append(AgentExecutionStep(name=f"turn_{turn}_verify", status="success", detail="completion_verified"))
            return AgentExecutionResult(
                success=True,
                summary="자율 루프 기반 작업 완료",
                user_message=final_response,
                artifacts={
                    "autonomous": "true",
                    "replan_count": str(replan_count),
                    "tool_calls": str(tool_calls),
                    "llm_provider": llm_provider or "",
                    "llm_model": llm_model or "",
                    "llm_verifier": llm_verifier_meta if llm_verdict != "skipped" else "",
                },
                steps=steps,
            )

        if action == "replan":
            if replan_count >= replan_limit:
                steps.append(AgentExecutionStep(name=f"turn_{turn}_replan", status="error", detail="replan_limit_exceeded"))
                return AgentExecutionResult(
                    success=False,
                    summary="재계획 제한 초과",
                    user_message="요청 처리 중 재계획 한도를 초과했습니다. 요청을 더 구체적으로 입력해주세요.",
                artifacts={"error_code": "replan_limit", "autonomous": "true"},
                steps=steps,
            )
            suggested = action_payload.get("updated_selected_tools")
            if isinstance(suggested, list):
                normalized = [str(item).strip() for item in suggested if isinstance(item, str)]
                normalized = [name for name in normalized if name in allowed_tools]
                blocked = [name for name in normalized if name not in selected_tools_lock]
                if blocked:
                    normalized = [name for name in normalized if name in selected_tools_lock]
                    steps.append(
                        AgentExecutionStep(
                            name=f"turn_{turn}_replan",
                            status="error",
                            detail=f"replan_tool_expansion_blocked:{','.join(blocked)}",
                        )
                    )
                if normalized:
                    plan.selected_tools = normalized
                    allowed_tools = normalized
            replan_count += 1
            history.append({"turn": turn, "action": "replan", "reason": reason, "selected_tools": allowed_tools})
            invalid_action_count = 0
            continue

        if action != "tool_call":
            steps.append(AgentExecutionStep(name=f"turn_{turn}_action", status="error", detail=f"unsupported:{action}"))
            return AgentExecutionResult(
                success=False,
                summary="지원하지 않는 자율 액션",
                user_message="요청 처리 중 지원하지 않는 실행 지시를 받아 작업을 중단했습니다.",
                artifacts={"error_code": "unsupported_action", "autonomous": "true"},
                steps=steps,
            )

        tool_name = str(action_payload.get("tool_name", "")).strip()
        tool_input = action_payload.get("tool_input")
        if tool_name not in allowed_tools:
            steps.append(AgentExecutionStep(name=f"turn_{turn}_tool", status="error", detail=f"tool_not_allowed:{tool_name}"))
            history.append({"turn": turn, "action": "tool_call", "tool_name": tool_name, "error": "tool_not_allowed"})
            invalid_action_count += 1
            if invalid_action_count >= 2 and replan_count < replan_limit:
                replan_count += 1
                history.append({"turn": turn, "action": "replan", "status": "forced", "reason": "invalid_tool_selection"})
            continue
        if not isinstance(tool_input, dict):
            steps.append(AgentExecutionStep(name=f"turn_{turn}_tool", status="error", detail="invalid_tool_input"))
            history.append({"turn": turn, "action": "tool_call", "tool_name": tool_name, "error": "invalid_tool_input"})
            invalid_action_count += 1
            if invalid_action_count >= 2 and replan_count < replan_limit:
                replan_count += 1
                history.append({"turn": turn, "action": "replan", "status": "forced", "reason": "invalid_tool_input"})
            continue

        if _has_same_failed_validation_call(history, tool_name=tool_name, tool_input=tool_input):
            steps.append(
                AgentExecutionStep(
                    name=f"turn_{turn}_tool:{tool_name}",
                    status="error",
                    detail="duplicate_validation_error_call_blocked",
                )
            )
            history.append(
                {
                    "turn": turn,
                    "action": "tool_call",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "status": "skipped",
                    "error": "duplicate_validation_error_call_blocked",
                }
            )
            invalid_action_count += 1
            if invalid_action_count >= 2 and replan_count < replan_limit:
                replan_count += 1
                history.append(
                    {
                        "turn": turn,
                        "action": "replan",
                        "status": "forced",
                        "reason": "duplicate_validation_error_call_blocked",
                    }
                )
            continue

        if _has_same_successful_mutation_call(history, tool_name=tool_name, tool_input=tool_input):
            steps.append(
                AgentExecutionStep(
                    name=f"turn_{turn}_tool:{tool_name}",
                    status="error",
                    detail="duplicate_mutation_call_blocked",
                )
            )
            history.append(
                {
                    "turn": turn,
                    "action": "tool_call",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "status": "skipped",
                    "error": "duplicate_mutation_call_blocked",
                }
            )
            invalid_action_count += 1
            if invalid_action_count >= 2 and replan_count < replan_limit:
                replan_count += 1
                history.append(
                    {
                        "turn": turn,
                        "action": "replan",
                        "status": "forced",
                        "reason": "duplicate_mutation_call_blocked",
                    }
                )
            continue

        try:
            tool_result = await execute_tool(user_id=user_id, tool_name=tool_name, payload=tool_input)
            tool_calls += 1
            invalid_action_count = 0
            steps.append(AgentExecutionStep(name=f"turn_{turn}_tool:{tool_name}", status="success", detail="ok"))
            history.append(
                {
                    "turn": turn,
                    "action": "tool_call",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "status": "success",
                    "tool_result": tool_result.get("data", {}),
                    "tool_result_summary": _compact_tool_result(tool_result.get("data", {})),
                }
            )
        except HTTPException as exc:
            tool_calls += 1
            err_detail = str(exc.detail)
            invalid_action_count = 0
            steps.append(AgentExecutionStep(name=f"turn_{turn}_tool:{tool_name}", status="error", detail=err_detail))
            history.append(
                {
                    "turn": turn,
                    "action": "tool_call",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "status": "error",
                    "error": err_detail,
                }
            )

    return AgentExecutionResult(
        success=False,
        summary="자율 루프 turn 제한 도달",
        user_message="요청 처리 단계를 완료하지 못했습니다. 요청을 더 구체적으로 입력하거나 다시 시도해주세요.",
        artifacts={
            "error_code": "turn_limit",
            "autonomous": "true",
            "llm_provider": llm_provider or "",
            "llm_model": llm_model or "",
        },
        steps=steps,
    )
