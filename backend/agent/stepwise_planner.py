from __future__ import annotations

import json
import re

import httpx
from supabase import create_client

from agent.intent_keywords import is_create_intent, is_read_intent, is_update_intent
from agent.registry import load_registry
from agent.runtime_api_profile import build_runtime_api_profile
from agent.runtime_catalog import get_or_create_catalog_id
from agent.types import AgentPlan, AgentRequirement, AgentTask
from app.core.config import get_settings


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def _is_gemini_provider(provider: str) -> bool:
    return provider in {"gemini", "google"}


def _extract_json_object(text: str) -> dict | None:
    candidate = (text or "").strip()
    if not candidate:
        return None
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
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


async def _request_json_with_provider(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    openai_api_key: str | None,
    google_api_key: str | None,
) -> dict | None:
    if provider == "openai":
        if not openai_api_key:
            return None
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
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            if resp.status_code >= 400:
                return None
            content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content", "")
            return _extract_json_object(str(content or ""))
        except Exception:
            return None
    if _is_gemini_provider(provider):
        if not google_api_key:
            return None
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=google_api_key)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if resp.status_code >= 400:
                return None
            parts = (((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
            return _extract_json_object(content)
        except Exception:
            return None
    return None


def _sentence_chunks(user_text: str) -> list[str]:
    text = str(user_text or "").strip()
    if not text:
        return []
    chunks = [part.strip() for part in re.split(r"\s*(?:그리고|그리고 나서|그 다음|다음으로|then|and then)\s*", text) if part.strip()]
    return chunks[:5]


def _is_tool_allowed_for_stepwise(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip().lower()
    if not normalized:
        return False
    if normalized.startswith("notion_oauth_token_"):
        return False
    if "_oauth_" in normalized:
        return False
    return True


def _pick_tool_for_sentence(sentence: str, tools: list[dict]) -> tuple[str, str]:
    lowered = sentence.lower()
    for tool in tools:
        service = str(tool.get("service") or "")
        name = str(tool.get("tool_name") or "")
        if service == "google" and any(token in lowered for token in ("일정", "캘린더", "회의", "calendar")) and "list_events" in name:
            return service, name
        if service == "notion" and any(token in lowered for token in ("노션", "notion")):
            if any(token in lowered for token in ("생성", "create", "회의록", "페이지", "초안")) and "create_page" in name:
                return service, name
            if any(token in lowered for token in ("조회", "검색", "찾")) and "search" in name:
                return service, name
        if service == "linear" and any(token in lowered for token in ("리니어", "linear", "이슈", "issue")):
            if any(token in lowered for token in ("생성", "등록", "create")) and "create_issue" in name:
                return service, name
            if any(token in lowered for token in ("조회", "검색", "목록")) and "search_issues" in name:
                return service, name
    first = tools[0] if tools else {}
    return str(first.get("service") or ""), str(first.get("tool_name") or "")


def _build_deterministic_tasks(user_text: str, tools: list[dict]) -> list[dict]:
    chunks = _sentence_chunks(user_text)
    if not chunks:
        return []
    tasks: list[dict] = []
    for index, sentence in enumerate(chunks, start=1):
        service, tool_name = _pick_tool_for_sentence(sentence, tools)
        if not tool_name:
            continue
        tasks.append({"task_id": f"step_{index}", "sentence": sentence, "service": service, "tool_name": tool_name})
    return tasks


def _load_granted_scopes_map(user_id: str, providers: set[str]) -> dict[str, set[str]]:
    if not providers:
        return {}
    settings = get_settings()
    supabase_url = str(getattr(settings, "supabase_url", "") or "").strip()
    service_role_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
    if not supabase_url or not service_role_key:
        return {}
    try:
        supabase = create_client(supabase_url, service_role_key)
        rows = (
            supabase.table("oauth_tokens")
            .select("provider,granted_scopes")
            .eq("user_id", user_id)
            .in_("provider", sorted(providers))
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    result: dict[str, set[str]] = {}
    for row in rows:
        provider = str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        scopes_raw = row.get("granted_scopes")
        scopes: set[str] = set()
        if isinstance(scopes_raw, list):
            scopes = {str(item).strip() for item in scopes_raw if str(item).strip()}
        elif isinstance(scopes_raw, str):
            scopes = {item.strip() for item in scopes_raw.split(" ") if item.strip()}
        result[provider] = scopes
    return result


def _is_stepwise_candidate(user_text: str, connected_services: list[str]) -> bool:
    text = str(user_text or "")
    lowered = text.lower()
    if not (is_create_intent(text) or is_read_intent(text) or is_update_intent(text)):
        return False
    aliases = {
        "google": ("google", "calendar", "캘린더", "구글캘린더", "일정", "회의"),
        "notion": ("notion", "노션", "페이지", "문서", "회의록"),
        "linear": ("linear", "리니어", "이슈", "issue"),
    }
    for service in connected_services:
        key = str(service or "").strip().lower()
        if key not in aliases:
            continue
        if any(token in text or token in lowered for token in aliases[key]):
            return True
    return False


async def try_build_stepwise_pipeline_plan(user_text: str, connected_services: list[str], user_id: str) -> AgentPlan | None:
    settings = get_settings()
    force_enabled = bool(getattr(settings, "stepwise_force_enabled", False))
    if not force_enabled and not _is_stepwise_candidate(user_text, connected_services):
        return None
    registry = load_registry()
    available = registry.list_available_tools(connected_services=connected_services)
    tool_catalog = [
        {
            "service": tool.service,
            "tool_name": tool.tool_name,
            "description": tool.description,
            "required_fields": list(tool.input_schema.get("required") or []),
        }
        for tool in available
        if _is_tool_allowed_for_stepwise(tool.tool_name)
    ]
    if not tool_catalog:
        return None
    providers = {str(item or "").strip().lower() for item in connected_services if str(item or "").strip()}
    granted_scopes = _load_granted_scopes_map(user_id=user_id, providers=providers)
    api_profile = build_runtime_api_profile(
        connected_services=connected_services,
        granted_scopes=granted_scopes,
        tenant_policy=None,
        risk_policy={"allow_high_risk": bool(getattr(settings, "delete_operations_enabled", False))},
    )
    enabled_api_ids = set(api_profile.get("enabled_api_ids") or [])
    tool_catalog = [
        item
        for item in tool_catalog
        if str(item.get("tool_name") or "") in enabled_api_ids
        and _is_tool_allowed_for_stepwise(str(item.get("tool_name") or ""))
    ]
    if not tool_catalog:
        return None

    system_prompt = (
        "You are a planner that decomposes one user request into sequential tasks. "
        "Return JSON only."
    )
    user_prompt = (
        f"user_text={user_text}\n"
        f"connected_services={json.dumps(connected_services, ensure_ascii=False)}\n"
        f"api_catalog={json.dumps(tool_catalog, ensure_ascii=False)}\n"
        "Return format: {\"tasks\":[{\"task_id\":\"step_1\",\"sentence\":\"...\",\"service\":\"...\",\"tool_name\":\"...\"}]}"
    )
    providers: list[tuple[str, str]] = []
    primary_provider = str(getattr(settings, "llm_planner_provider", "openai") or "openai").strip().lower()
    primary_model = str(getattr(settings, "llm_planner_model", "gpt-4o-mini") or "gpt-4o-mini").strip()
    providers.append((primary_provider, primary_model))
    fallback_provider = str(getattr(settings, "llm_planner_fallback_provider", "") or "").strip().lower()
    fallback_model = str(getattr(settings, "llm_planner_fallback_model", "") or "").strip()
    if fallback_provider and fallback_model:
        providers.append((fallback_provider, fallback_model))

    parsed: dict | None = None
    for provider, model in providers:
        parsed = await _request_json_with_provider(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=getattr(settings, "openai_api_key", None),
            google_api_key=getattr(settings, "google_api_key", None),
        )
        if isinstance(parsed, dict):
            break

    tasks_raw = parsed.get("tasks") if isinstance(parsed, dict) else None
    tasks: list[dict] = []
    if isinstance(tasks_raw, list):
        allowed_tools = {item["tool_name"] for item in tool_catalog}
        for index, item in enumerate(tasks_raw, start=1):
            if not isinstance(item, dict):
                continue
            sentence = str(item.get("sentence") or "").strip()
            service = str(item.get("service") or "").strip().lower()
            tool_name = str(item.get("tool_name") or "").strip()
            if not sentence or not tool_name or tool_name not in allowed_tools:
                continue
            tasks.append(
                {
                    "task_id": str(item.get("task_id") or f"step_{index}").strip() or f"step_{index}",
                    "sentence": sentence,
                    "service": service,
                    "tool_name": tool_name,
                }
            )
    if not tasks:
        tasks = _build_deterministic_tasks(user_text, tool_catalog)
    if not tasks:
        return None

    target_services = list(dict.fromkeys([str(item.get("service") or "").strip().lower() for item in tasks if str(item.get("service") or "").strip()]))
    selected_tools = list(dict.fromkeys([str(item.get("tool_name") or "").strip() for item in tasks if str(item.get("tool_name") or "").strip()]))
    workflow_steps = [f"{idx}. {task['sentence']}" for idx, task in enumerate(tasks, start=1)]
    catalog_payload = {
        "connected_services": list(dict.fromkeys([str(item).strip().lower() for item in connected_services if str(item).strip()])),
        "enabled_api_ids": sorted(enabled_api_ids),
        "tool_catalog": tool_catalog,
    }
    catalog_id, _ = get_or_create_catalog_id(user_id=user_id, catalog_payload=catalog_payload)

    return AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary="llm_stepwise_pipeline")],
        target_services=target_services,
        selected_tools=selected_tools,
        workflow_steps=workflow_steps,
        tasks=[
            AgentTask(
                id="task_stepwise_pipeline_v1",
                title="llm stepwise sequential pipeline",
                task_type="STEPWISE_PIPELINE",
                payload={"tasks": tasks, "ctx": {"enabled": True, "catalog_id": catalog_id}},
            )
        ],
        notes=[
            "planner=llm_stepwise",
            "router_mode=STEPWISE_PIPELINE",
            "plan_source=stepwise_template",
            f"catalog_id={catalog_id}",
        ],
    )
