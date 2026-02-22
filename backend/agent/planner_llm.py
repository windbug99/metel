from __future__ import annotations

import json
import re

import httpx

from agent.planner import build_agent_plan, build_execution_tasks, is_user_facing_tool
from agent.registry import load_registry
from agent.slot_collector import collect_slots_from_user_reply
from agent.slot_schema import validate_slots
from agent.types import AgentPlan, AgentRequirement, AgentTask
from app.core.config import get_settings


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


def _normalize_tasks(value: object) -> list[AgentTask]:
    if not isinstance(value, list):
        return []
    tasks: list[AgentTask] = []
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        task_type = str(item.get("task_type", "")).strip().upper()
        if task_type not in {"TOOL", "LLM"}:
            continue
        task_id = str(item.get("id") or f"task_{idx}").strip()
        title = str(item.get("title") or task_id).strip()
        depends_on = [dep.strip() for dep in _normalize_list(item.get("depends_on")) if dep.strip()]
        service = str(item.get("service", "")).strip() or None
        tool_name = str(item.get("tool_name", "")).strip() or None
        payload = item.get("payload")
        instruction = str(item.get("instruction", "")).strip() or None
        output_schema = item.get("output_schema")
        tasks.append(
            AgentTask(
                id=task_id,
                title=title,
                task_type=task_type,
                depends_on=depends_on,
                service=service,
                tool_name=tool_name,
                payload=payload if isinstance(payload, dict) else {},
                instruction=instruction,
                output_schema=output_schema if isinstance(output_schema, dict) else {},
            )
        )
    return tasks


def _validate_task_contract(
    *,
    tasks: list[AgentTask],
    target_services: list[str],
    available_tool_names: set[str],
) -> tuple[bool, str | None]:
    if not tasks:
        return True, None

    ids = [task.id for task in tasks]
    if len(set(ids)) != len(ids):
        return False, "duplicate_task_id"

    id_set = set(ids)
    target_set = {service.lower().strip() for service in target_services}

    for task in tasks:
        if not task.id.strip():
            return False, "missing_task_id"
        if task.task_type not in {"TOOL", "LLM"}:
            return False, "invalid_task_type"
        if not task.title.strip():
            return False, "missing_task_title"
        if not isinstance(task.payload, dict):
            return False, f"invalid_payload:{task.id}"
        if not isinstance(task.output_schema, dict) or not task.output_schema:
            return False, f"missing_output_schema:{task.id}"
        for dep in task.depends_on:
            if dep not in id_set:
                return False, f"depends_on_not_found:{task.id}:{dep}"

        if task.task_type == "TOOL":
            service = (task.service or "").strip().lower()
            tool_name = (task.tool_name or "").strip()
            if not service:
                return False, f"missing_service:{task.id}"
            if service not in target_set:
                return False, f"service_not_in_target:{task.id}:{service}"
            if not tool_name:
                return False, f"missing_tool_name:{task.id}"
            if tool_name not in available_tool_names:
                return False, f"unknown_tool:{task.id}:{tool_name}"
            if not tool_name.startswith(f"{service}_"):
                return False, f"tool_service_mismatch:{task.id}:{tool_name}"
        else:
            if not (task.instruction or "").strip():
                return False, f"missing_instruction:{task.id}"

    return True, None


def _to_agent_plan(
    *,
    user_text: str,
    connected_services: list[str],
    payload: dict,
) -> AgentPlan:
    registry = load_registry()
    connected_set = {item.lower().strip() for item in connected_services}
    available_tools = registry.list_available_tools(connected_services=connected_services)
    available_tools = [tool for tool in available_tools if is_user_facing_tool(tool.tool_name)]
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
    tasks = _normalize_tasks(payload.get("tasks"))
    synthesized_tasks = build_execution_tasks(
        user_text=user_text,
        target_services=target_services,
        selected_tools=selected_tools,
    )
    if not tasks:
        tasks = synthesized_tasks
    else:
        valid_contract, reason = _validate_task_contract(
            tasks=tasks,
            target_services=target_services,
            available_tool_names=available_tool_names,
        )
        if not valid_contract:
            tasks = synthesized_tasks
            notes.append(f"tasks_contract_rejected:{reason}")
        else:
            has_llm = any(task.task_type == "LLM" for task in tasks)
            synthesized_has_llm = any(task.task_type == "LLM" for task in synthesized_tasks)
            if not has_llm and synthesized_has_llm:
                tasks = synthesized_tasks
                notes.append("tasks_rehydrated_with_rule_synthesis")
    return AgentPlan(
        user_text=user_text,
        requirements=requirements,
        target_services=target_services,
        selected_tools=selected_tools,
        workflow_steps=workflow_steps,
        tasks=tasks,
        notes=notes,
    )


def _normalize_structured_slots_payload(
    payload: dict,
    *,
    available_tool_names: set[str],
) -> tuple[dict[str, object], str | None]:
    intent = str(payload.get("intent") or "").strip().lower() or "unknown"
    service = str(payload.get("service") or "").strip().lower()
    tool = str(payload.get("tool") or "").strip()
    workflow = _normalize_list(payload.get("workflow"))
    raw_confidence = payload.get("confidence")
    confidence: float | None = None
    if isinstance(raw_confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    slots_by_action: dict[str, dict] = {}

    raw_slots = payload.get("slots")
    if isinstance(raw_slots, dict):
        for action, slots in raw_slots.items():
            action_name = str(action or "").strip()
            if action_name not in available_tool_names:
                continue
            if isinstance(slots, dict):
                slots_by_action[action_name] = dict(slots)

    actions = payload.get("actions")
    if isinstance(actions, list):
        for item in actions:
            if not isinstance(item, dict):
                continue
            action_name = str(item.get("action") or item.get("tool_name") or "").strip()
            if action_name not in available_tool_names:
                continue
            slots = item.get("slots")
            if isinstance(slots, dict):
                slots_by_action[action_name] = dict(slots)

    if tool and tool in available_tool_names and tool not in slots_by_action:
        slots_by_action[tool] = {}

    normalized: dict[str, object] = {
        "intent": intent,
        "service": service,
        "tool": tool,
        "workflow": workflow,
        "confidence": confidence,
        "slots_by_action": slots_by_action,
    }

    if not slots_by_action:
        # Intent-only output is still useful for task rewrite/routing.
        if intent and intent != "unknown":
            return normalized, None
        return normalized, "structured_slots_empty"
    return normalized, None


def _apply_structured_slots_to_plan(
    *,
    plan: AgentPlan,
    structured: dict[str, object],
    slots_by_action: dict[str, dict],
) -> tuple[AgentPlan, list[str]]:
    intent = str(structured.get("intent") or "").strip()
    service = str(structured.get("service") or "").strip()
    tool = str(structured.get("tool") or "").strip()
    workflow = [item for item in (structured.get("workflow") or []) if isinstance(item, str) and item.strip()]
    confidence = structured.get("confidence")
    notes: list[str] = []
    if intent:
        notes.append(f"structured_intent={intent}")
    if service:
        notes.append(f"structured_service={service}")
    if tool:
        notes.append(f"structured_tool={tool}")
    if workflow:
        notes.append(f"structured_workflow_steps={len(workflow)}")
    if isinstance(confidence, float):
        notes.append(f"structured_confidence={confidence:.2f}")
    if not slots_by_action:
        return plan, notes

    for task in plan.tasks:
        if task.task_type != "TOOL":
            continue
        tool_name = str(task.tool_name or "").strip()
        if not tool_name:
            continue
        parsed_slots = slots_by_action.get(tool_name)
        if not isinstance(parsed_slots, dict):
            continue
        normalized, _, validation_errors = validate_slots(tool_name, parsed_slots)
        if validation_errors:
            notes.append(f"structured_slots_validation_error:{tool_name}:{validation_errors[0]}")
            continue
        # Keep task payload precedence for planner-inferred control fields.
        task.payload = {**normalized, **(task.payload or {})}
        notes.append(f"structured_slots_applied:{tool_name}")
    return plan, notes


def _maybe_rewrite_tasks_by_intent(*, plan: AgentPlan, intent: str) -> tuple[AgentPlan, str | None]:
    normalized_intent = (intent or "").strip().lower()
    if normalized_intent != "update":
        return plan, None
    has_update_tool = any(
        task.task_type == "TOOL" and "update" in str(task.tool_name or "").lower()
        for task in (plan.tasks or [])
    )
    if has_update_tool:
        return plan, None
    rewritten = build_execution_tasks(
        user_text=plan.user_text,
        target_services=plan.target_services,
        selected_tools=plan.selected_tools,
    )
    if not rewritten:
        return plan, None
    plan.tasks = rewritten
    return plan, "tasks_rewritten_by_structured_intent:update"


def _apply_keyed_slot_fallback_to_plan(*, plan: AgentPlan, user_text: str) -> tuple[AgentPlan, list[str]]:
    notes: list[str] = []
    raw = (user_text or "").strip()
    if not raw:
        return plan, notes
    # keyed marker only fallback (e.g., "제목: ... 팀: ...")
    if not re.search(r"[0-9A-Za-z가-힣_]+\s*[:=]\s*", raw):
        return plan, notes

    for task in plan.tasks:
        if task.task_type != "TOOL":
            continue
        action = str(task.tool_name or "").strip()
        if not action:
            continue
        parsed = collect_slots_from_user_reply(
            action=action,
            user_text=raw,
            collected_slots=dict(task.payload or {}),
        )
        if parsed.collected_slots != dict(task.payload or {}):
            task.payload = dict(parsed.collected_slots)
            notes.append(f"keyed_slots_fallback_applied:{action}")
    return plan, notes


async def _try_structured_parse_with_llm(
    *,
    user_text: str,
    connected_services: list[str],
    available_tools: list,
    settings,
) -> tuple[dict[str, object] | None, str | None]:
    available_tool_names = {tool.tool_name for tool in available_tools}
    if not available_tool_names:
        return None, "no_available_tools"

    connected = ", ".join(connected_services) if connected_services else "(없음)"
    tool_names = ", ".join(sorted(available_tool_names))
    system_prompt = (
        "당신은 metel의 구조화 파서입니다. "
        "반드시 JSON object만 응답하세요. "
        "intent와 action별 slots를 추출하며, 제공된 tool_name만 사용하세요."
    )
    user_prompt = (
        f"사용자 요청: {user_text}\n"
        f"연결 서비스: {connected}\n"
        f"허용 tool_name: {tool_names}\n\n"
        "JSON 형식:\n"
        "{\n"
        '  "intent": "search|create|update|delete|summary|query|unknown",\n'
        '  "service": "notion|linear|spotify|unknown",\n'
        '  "tool": "tool_name 또는 빈 문자열",\n'
        '  "workflow": ["1단계", "2단계"],\n'
        '  "confidence": 0.0,\n'
        '  "slots": {\n'
        '    "tool_name": {"slot_key": "value"}\n'
        "  }\n"
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
    used: set[tuple[str, str]] = set()
    for provider, model in attempts:
        key = (provider, model)
        if key in used:
            continue
        used.add(key)
        parsed, err = await _request_structured_parse_with_provider(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
        )
        if err:
            errors.append(f"{provider}:{err}")
            continue
        normalized, normalize_err = _normalize_structured_slots_payload(
            parsed,
            available_tool_names=available_tool_names,
        )
        if normalize_err:
            errors.append(f"{provider}:{normalize_err}")
            continue
        return normalized, None
    return None, "|".join(errors) if errors else "structured_parse_unknown_error"


async def try_build_agent_plan_with_llm(
    *,
    user_text: str,
    connected_services: list[str],
) -> tuple[AgentPlan | None, str | None]:
    settings = get_settings()
    if not settings.llm_planner_enabled:
        return None, "llm_planner_disabled"

    registry = load_registry()
    available_tools = registry.list_available_tools(connected_services=connected_services)
    available_tools = [tool for tool in available_tools if is_user_facing_tool(tool.tool_name)]
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
        '  "tasks": [{"id":"task1","title":"작업","task_type":"TOOL","service":"notion","tool_name":"notion_search","depends_on":[],"payload":{"query":"최근"}}],\n'
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
    used: set[tuple[str, str]] = set()
    for provider, model in attempts:
        key = (provider, model)
        if key in used:
            continue
        used.add(key)

        if provider == "openai" and not settings.openai_api_key:
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
            openai_api_key=settings.openai_api_key,
            google_api_key=settings.google_api_key,
        )
        if err:
            errors.append(f"{provider}:{err}")
            continue
        plan = _to_agent_plan(user_text=user_text, connected_services=connected_services, payload=parsed)
        plan, keyed_notes = _apply_keyed_slot_fallback_to_plan(plan=plan, user_text=user_text)
        if keyed_notes:
            plan.notes.extend(keyed_notes)
        structured, structured_err = await _try_structured_parse_with_llm(
            user_text=user_text,
            connected_services=connected_services,
            available_tools=available_tools,
            settings=settings,
        )
        if structured:
            intent = str(structured.get("intent") or "").strip()
            slots_by_action = structured.get("slots_by_action")
            plan, structured_notes = _apply_structured_slots_to_plan(
                plan=plan,
                structured=structured,
                slots_by_action=slots_by_action if isinstance(slots_by_action, dict) else {},
            )
            plan, rewrite_note = _maybe_rewrite_tasks_by_intent(plan=plan, intent=intent)
            if rewrite_note:
                plan.notes.append(rewrite_note)
            if structured_notes:
                plan.notes.extend(structured_notes)
            plan.notes.append("structured_parser=llm")
            plan.notes.append("semantic_parse=llm")
            plan.notes.append("execution_decision=rule")
        elif structured_err:
            plan.notes.append(f"structured_parser_fallback:{structured_err}")
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


async def _request_structured_parse_with_provider(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    openai_api_key: str | None,
    google_api_key: str | None,
) -> tuple[dict | None, str | None]:
    return await _request_plan_with_provider(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        openai_api_key=openai_api_key,
        google_api_key=google_api_key,
    )
