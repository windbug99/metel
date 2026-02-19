from __future__ import annotations

import json
import re

import httpx

from agent.planner import build_agent_plan
from agent.registry import load_registry
from agent.types import AgentPlan, AgentRequirement
from app.core.config import get_settings
from app.security.provider_keys import load_user_provider_token


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def _default_workflow_steps(selected_tools: list[str]) -> list[str]:
    steps = [
        "요청문 분석 및 작업 요구사항 도출",
        "작업 요구사항 기반 타겟 서비스 선정",
        "타겟 서비스의 실행 가능한 API(tool) 선정",
        "선정된 API 순서 기반 워크플로우 생성",
        "워크플로우 기반 작업 진행",
        "결과 정리",
        "텔레그램 사용자 결과 전달",
    ]
    if selected_tools:
        steps.append("실행 예정 API 순서: " + " -> ".join(selected_tools))
    return steps


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
    return result


def _to_agent_plan(
    *,
    user_text: str,
    connected_services: list[str],
    payload: dict,
) -> AgentPlan:
    registry = load_registry()
    connected_set = {item.lower().strip() for item in connected_services}
    available_tools = registry.list_available_tools(connected_services=connected_services)
    available_tool_names = {tool.tool_name for tool in available_tools}
    available_services = {tool.service for tool in available_tools}

    target_services = [svc.lower().strip() for svc in _normalize_list(payload.get("target_services"))]
    target_services = [svc for svc in target_services if svc in connected_set and svc in available_services]
    if not target_services:
        # If LLM misses service selection, fallback to rule resolver result.
        return build_agent_plan(user_text=user_text, connected_services=connected_services)

    selected_tools = _normalize_list(payload.get("selected_tools"))
    selected_tools = [tool for tool in selected_tools if tool in available_tool_names]
    if not selected_tools:
        selected_tools = [tool.tool_name for tool in available_tools if tool.service in target_services][:5]

    requirement_summaries = _normalize_list(payload.get("requirements"))
    requirements = [AgentRequirement(summary=item) for item in requirement_summaries]
    if not requirements:
        requirements = [AgentRequirement(summary="사용자 요청 분석 및 실행 계획 수립")]

    workflow_steps = _normalize_list(payload.get("workflow_steps")) or _default_workflow_steps(selected_tools)
    notes = _normalize_list(payload.get("notes"))
    notes.append("planner=llm")
    return AgentPlan(
        user_text=user_text,
        requirements=requirements,
        target_services=target_services,
        selected_tools=selected_tools,
        workflow_steps=workflow_steps,
        notes=notes,
    )


async def try_build_agent_plan_with_llm(
    *,
    user_text: str,
    connected_services: list[str],
    user_id: str | None = None,
) -> tuple[AgentPlan | None, str | None]:
    settings = get_settings()
    if not settings.llm_planner_enabled:
        return None, "llm_planner_disabled"

    registry = load_registry()
    available_tools = registry.list_available_tools(connected_services=connected_services)
    if not available_tools:
        return None, "no_available_tools"

    tool_descriptions = "\n".join(
        f"- {tool.tool_name} ({tool.service}): {tool.description}" for tool in available_tools
    )
    connected = ", ".join(connected_services) if connected_services else "(없음)"
    system_prompt = (
        "당신은 metel의 planning 전용 에이전트입니다. "
        "반드시 JSON object만 응답하세요. "
        "실행 가능한 연결 서비스와 도구만 선택해야 합니다."
    )
    user_prompt = (
        f"사용자 요청: {user_text}\n"
        f"연결 서비스: {connected}\n"
        f"사용 가능한 도구 목록:\n{tool_descriptions}\n\n"
        "JSON 형식:\n"
        "{\n"
        '  "requirements": ["요구사항1", "요구사항2"],\n'
        '  "target_services": ["notion"],\n'
        '  "selected_tools": ["notion_search", "notion_retrieve_block_children"],\n'
        '  "workflow_steps": ["1단계", "2단계"],\n'
        '  "notes": ["주의사항"]\n'
        "}\n"
    )

    attempts: list[tuple[str, str]] = []
    primary_provider = (settings.llm_planner_provider or "openai").strip().lower()
    primary_model = settings.llm_planner_model
    attempts.append((primary_provider, primary_model))
    fallback_provider = (settings.llm_planner_fallback_provider or "").strip().lower()
    fallback_model = (settings.llm_planner_fallback_model or "").strip()
    if fallback_provider and fallback_model:
        attempts.append((fallback_provider, fallback_model))

    errors: list[str] = []
    user_openai_key = load_user_provider_token(user_id, "openai") if user_id else None
    effective_openai_key = user_openai_key or settings.openai_api_key
    used: set[tuple[str, str]] = set()
    for provider, model in attempts:
        key = (provider, model)
        if key in used:
            continue
        used.add(key)

        if provider == "openai" and not effective_openai_key:
            errors.append("openai_api_key_missing")
            continue
        if provider == "gemini" and not settings.google_api_key:
            errors.append("google_api_key_missing")
            continue

        parsed, err = await _request_plan_with_provider(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=effective_openai_key,
            google_api_key=settings.google_api_key,
        )
        if err:
            errors.append(f"{provider}:{err}")
            continue
        plan = _to_agent_plan(user_text=user_text, connected_services=connected_services, payload=parsed)
        plan.notes.append(f"llm_provider={provider}")
        plan.notes.append(f"llm_model={model}")
        return plan, None

    return None, "|".join(errors) if errors else "llm_unknown_error"


def _extract_json_object(text: str) -> dict | None:
    candidate = text.strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


async def _request_plan_with_provider(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    openai_api_key: str | None,
    google_api_key: str | None,
) -> tuple[dict | None, str | None]:
    if provider == "openai":
        request_payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=request_payload)
            if response.status_code >= 400:
                return None, f"http_{response.status_code}"
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not content:
                return None, "empty_content"
            parsed = _extract_json_object(content)
            if not parsed:
                return None, "invalid_json"
            return parsed, None
        except Exception as exc:  # pragma: no cover
            return None, f"error:{exc.__class__.__name__}"

    if provider == "gemini":
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=google_api_key)
        request_payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json=request_payload, headers={"Content-Type": "application/json"})
            if response.status_code >= 400:
                return None, f"http_{response.status_code}"
            data = response.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            content = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
            if not content:
                return None, "empty_content"
            parsed = _extract_json_object(content)
            if not parsed:
                return None, "invalid_json"
            return parsed, None
        except Exception as exc:  # pragma: no cover
            return None, f"error:{exc.__class__.__name__}"

    return None, "unsupported_provider"
