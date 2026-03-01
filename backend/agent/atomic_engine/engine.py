from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from agent.pending_action import PendingActionStorageError, clear_pending_action, get_pending_action, set_pending_action
from agent.registry import load_registry
from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan, AgentRequirement, AgentRunResult, AgentTask
from app.core.config import get_settings


SUPPORTED_SERVICES = {"google", "notion", "linear"}
CONFIDENCE_THRESHOLD = 0.8
CLARIFICATION_MAX_TURNS = 2
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"


@dataclass
class UnderstandingResult:
    request_type: str
    intent: str | None
    service: str | None
    slots: dict[str, object]
    missing_slots: list[str]
    confidence: float


@dataclass
class RequestContract:
    intent: str
    service: str
    tool_name: str
    slots: dict[str, object]
    clarification_needed: list[str] = field(default_factory=list)
    autofilled: list[str] = field(default_factory=list)
    expected_output: dict[str, object] = field(default_factory=dict)
    tool_candidates: list[str] = field(default_factory=list)


def _normalize_message(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_first_int(text: str) -> int | None:
    match = re.search(r"(\d+)", text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    value = (text or "").lower()
    return any(token in value for token in tokens)


def _looks_like_linear_internal_issue_id(value: object) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F\-]{27}", candidate))


def _normalize_linear_state_name(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").strip().lower())


def _extract_linear_update_title(text: str) -> str | None:
    normalized = _normalize_message(text)
    patterns = [
        r'(?i)(?:이슈\s*)?(?:제목|title)(?:을|를)?\s*["“]?([^"”]+?)["”]?\s*(?:로|으로)?\s*(?:업데이트|수정|변경|바꿔|rename)',
        r"(?i)(?:제목|title)\s*[:：]\s*['\"“”]?(.+?)['\"“”]?(?:\s|$)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`.,")
        if candidate:
            return candidate[:120]
    return None


def _extract_linear_update_description(text: str) -> str | None:
    raw_text = str(text or "")
    append_tail = re.search(
        r"(?is)(?:추가|append|덧붙(?:여)?|붙여|반영|수정|변경|교체|업데이트)(?:해줘|해주세요|하세요|해)\s*[.!?]?\s*[:：]?\s*(.+)$",
        raw_text,
    )
    if append_tail:
        tail_candidate = str(append_tail.group(1) or "").strip(" \"'`")
        tail_candidate = tail_candidate.lstrip(" \t\r\n.:-")
        if tail_candidate:
            return tail_candidate[:5000]

    replace_tail = re.search(
        r"(?is)(?:다음|아래)\s*(?:메모|내용|텍스트|문장)(?:를|을)?\s*(?:추가|수정|변경|교체|업데이트)(?:해줘|해주세요|하세요|해)\s*[.!?]?\s*(.+)$",
        raw_text,
    )
    if replace_tail:
        tail_candidate = str(replace_tail.group(1) or "").strip(" \"'`")
        tail_candidate = tail_candidate.lstrip(" \t\r\n.:-")
        if tail_candidate:
            return tail_candidate[:5000]

    normalized = _normalize_message(text)
    patterns = [
        r"(?i)(?:설명|description|내용|본문)\s*(?:업데이트|수정|변경)?\s*[:：]\s*(.+)$",
        r'(?i)(?:설명|description|내용|본문)에\s*["“]?(.+?)["”]?\s*(?:를\s*)?(?:추가|append|넣어|작성|반영)',
        r"(?i)(?:설명|description|내용|본문)(?:을|를)?\s*(.+?)\s*(?:으로|로)\s*(?:업데이트|수정|변경|바꿔|바꿔줘|수정해줘|업데이트해줘|수정하세요|변경해줘)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`")
        if candidate:
            return candidate[:5000]
    return None


def _extract_linear_update_state(text: str) -> str | None:
    normalized = _normalize_message(text)
    explicit = re.search(r"(?i)(?:state_id|state id|상태id|상태_id)\s*[:：]\s*([^\s,]+)", normalized)
    if explicit:
        candidate = str(explicit.group(1) or "").strip(" \"'`.,")
        return candidate or None
    natural = re.search(
        r"(?i)(?:상태|state)\s*(?:를|을)?\s*([^\s,;]+(?:\s+[^\s,;]+)?)\s*(?:으로|로)\s*(?:변경|수정|업데이트|바꿔|전환)",
        normalized,
    )
    if not natural:
        return None
    candidate = str(natural.group(1) or "").strip(" \"'`.,")
    candidate = re.sub(r"(으|로)$", "", candidate).strip()
    return candidate or None


def _extract_linear_update_priority(text: str) -> int | None:
    normalized = _normalize_message(text)
    matched = re.search(r"(?i)(?:priority|우선순위)\s*[:：]\s*([0-4])", normalized)
    if not matched:
        return None
    try:
        return int(matched.group(1))
    except Exception:
        return None


def _is_linear_description_append_intent(text: str) -> bool:
    raw = _normalize_message(text)
    lower = raw.lower()
    has_target = any(token in raw or token in lower for token in ("설명", "description", "본문", "내용"))
    has_append = any(token in raw or token in lower for token in ("추가", "append", "덧붙", "붙여", "반영"))
    return has_target and has_append


def _merge_linear_description(*, current: str, addition: str) -> str:
    current_text = (current or "").strip()
    addition_text = (addition or "").strip()
    if not addition_text:
        return current_text
    if not current_text:
        return addition_text
    if addition_text in current_text:
        return current_text
    return f"{current_text}\n\n{addition_text}"


def _detect_service(text: str, connected_services: list[str]) -> str | None:
    lower = (text or "").lower()
    if ("google" in lower or "구글" in lower or "캘린더" in lower) and "google" in connected_services:
        return "google"
    if ("notion" in lower or "노션" in lower) and "notion" in connected_services:
        return "notion"
    if re.search(r"\b[A-Za-z]{2,10}-\d{1,6}\b", text or "") and "linear" in connected_services:
        return "linear"
    if ("linear" in lower or "리니어" in lower) and "linear" in connected_services:
        return "linear"
    if len(connected_services) == 1:
        return connected_services[0]
    return None


def _extract_time_range(text: str) -> str | None:
    raw = text or ""
    if "오늘" in raw:
        return "today"
    if "내일" in raw:
        return "tomorrow"
    if "어제" in raw:
        return "yesterday"
    return None


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
    return parsed if isinstance(parsed, dict) else None


def _load_prompt_file(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or fallback
    except Exception:
        return fallback


def _understanding_system_prompt() -> str:
    return _load_prompt_file(
        PROMPT_ROOT / "request_understanding.txt",
        (
            "You are a SaaS automation parser. Return JSON only.\n"
            "Schema: request_type, intent, service, slots, missing_slots, confidence.\n"
            "request_type in [saas_execution, unsupported]."
        ),
    )


def _understanding_user_prompt(*, user_message: str, connected_services: list[str], timezone_name: str) -> str:
    template = _load_prompt_file(
        PROMPT_ROOT / "request_understanding_user.txt",
        "사용자 요청: {user_message}\n연결된 서비스: {connected_services}\n사용자 timezone: {timezone}\n",
    )
    return (
        template.replace("{user_message}", user_message)
        .replace("{connected_services}", ", ".join(connected_services))
        .replace("{timezone}", timezone_name)
    )


def _coerce_understanding(payload: dict) -> UnderstandingResult | None:
    request_type = str(payload.get("request_type") or "").strip().lower()
    if request_type not in {"saas_execution", "unsupported"}:
        return None
    intent = payload.get("intent")
    service = payload.get("service")
    slots = payload.get("slots")
    missing_slots = payload.get("missing_slots")
    confidence = payload.get("confidence")
    if intent is not None and not isinstance(intent, str):
        return None
    if service is not None and not isinstance(service, str):
        return None
    if not isinstance(slots, dict):
        return None
    if not isinstance(missing_slots, list):
        return None
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(1.0, score))
    return UnderstandingResult(
        request_type=request_type,
        intent=intent.strip() if isinstance(intent, str) and intent.strip() else None,
        service=service.strip().lower() if isinstance(service, str) and service.strip() else None,
        slots=slots,
        missing_slots=[str(item).strip() for item in missing_slots if str(item).strip()],
        confidence=score,
    )


async def _request_understanding_with_provider(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    openai_api_key: str | None,
    google_api_key: str | None,
    timeout_sec: int,
) -> dict | None:
    if provider == "openai" and openai_api_key:
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            return None
        content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return _extract_json_object(content)

    if provider in {"google", "gemini"} and google_api_key:
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=google_api_key)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if resp.status_code >= 400:
            return None
        parts = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
        return _extract_json_object(content)
    return None


def _build_understanding_rule(user_text: str, connected_services: list[str]) -> UnderstandingResult:
    text = _normalize_message(user_text)
    lower = text.lower()
    service = _detect_service(text, connected_services)
    slots: dict[str, object] = {}
    missing_slots: list[str] = []

    if _contains_any(lower, ("서식", "템플릿", "회의록")) and service is None:
        return UnderstandingResult(
            request_type="unsupported",
            intent=None,
            service=None,
            slots={},
            missing_slots=[],
            confidence=0.95,
        )

    if service == "google" and _contains_any(lower, ("일정", "캘린더", "event", "list", "조회")):
        slots["time_range"] = _extract_time_range(text) or "today"
        count = _extract_first_int(text)
        if count:
            slots["limit"] = max(1, min(20, count))
        return UnderstandingResult(
            request_type="saas_execution",
            intent="list_events",
            service="google",
            slots=slots,
            missing_slots=[],
            confidence=0.92,
        )

    if service == "notion":
        if _contains_any(lower, ("본문", "추가", "append", "내용")) and _contains_any(lower, ("페이지", "page")):
            quoted = re.findall(r'"([^"]+)"', text)
            if quoted:
                slots["page_title"] = quoted[0].strip()
            content_match = re.search(r"(?:업데이트[:\s]+|추가[:\s]+)(.+)$", text)
            if content_match:
                slots["content"] = content_match.group(1).strip()
            return UnderstandingResult(
                request_type="saas_execution",
                intent="append_page_content",
                service="notion",
                slots=slots,
                missing_slots=[],
                confidence=0.82,
            )
        if _contains_any(lower, ("업데이트", "수정", "update")) and _contains_any(lower, ("페이지", "page")):
            quoted = re.findall(r'"([^"]+)"', text)
            if len(quoted) >= 2:
                slots["page_title"] = quoted[0].strip()
                slots["new_title"] = quoted[1].strip()
            return UnderstandingResult(
                request_type="saas_execution",
                intent="update_page",
                service="notion",
                slots=slots,
                missing_slots=[],
                confidence=0.84,
            )
        if _contains_any(lower, ("삭제", "지워", "아카이브", "delete", "archive")):
            page_id_match = re.search(r"(?:page_id|페이지\s*id|id)[:\s]+([A-Za-z0-9\-]+)", text, flags=re.IGNORECASE)
            if page_id_match:
                slots["page_id"] = page_id_match.group(1).strip()
            return UnderstandingResult(
                request_type="saas_execution",
                intent="delete_page",
                service="notion",
                slots=slots,
                missing_slots=[],
                confidence=0.88,
            )
        if _contains_any(lower, ("생성", "만들", "create")):
            title_match = re.search(r"(?:제목[:\s]+)(.+)$", text)
            if title_match:
                slots["title"] = title_match.group(1).strip()
            missing_slots.append("database_id")
            return UnderstandingResult(
                request_type="saas_execution",
                intent="create_page",
                service="notion",
                slots=slots,
                missing_slots=missing_slots,
                confidence=0.9,
            )
        if _contains_any(lower, ("조회", "검색", "list", "search")):
            query = re.sub(r"(노션|notion|조회|검색|해줘|해주세요)", "", text, flags=re.IGNORECASE).strip()
            if query:
                slots["query"] = query
            return UnderstandingResult(
                request_type="saas_execution",
                intent="search_pages",
                service="notion",
                slots=slots,
                missing_slots=[],
                confidence=0.86,
            )

    if service == "linear":
        issue_match = re.search(r"([A-Za-z]{2,10}-\d{1,6})", text)
        if _contains_any(lower, ("업데이트", "추가", "수정", "변경", "바꿔", "append", "update", "덧붙", "붙여", "반영")) and (
            _contains_any(lower, ("이슈", "issue")) or issue_match is not None
        ):
            if issue_match:
                slots["issue_id"] = issue_match.group(1).strip()
            title_text = _extract_linear_update_title(text)
            if title_text:
                slots["title"] = title_text
            description_text = _extract_linear_update_description(text)
            if description_text:
                slots["description"] = description_text
            state_value = _extract_linear_update_state(text)
            if state_value:
                slots["state_id"] = state_value
            priority_value = _extract_linear_update_priority(text)
            if priority_value is not None:
                slots["priority"] = priority_value
            if _is_linear_description_append_intent(text):
                slots["description_append"] = "1"
                if "description" not in slots:
                    fallback = text
                    if issue_match:
                        fallback = fallback.replace(issue_match.group(1), " ")
                    fallback = re.sub(r"\b(linear|리니어)\b", " ", fallback, flags=re.IGNORECASE)
                    fallback = re.sub(
                        r"(?i)(?:설명|description|본문|내용)에?\s*(?:.*?)(?:추가|append|덧붙|붙여|반영)(?:해줘|해주세요|하세요)?\s*$",
                        " ",
                        fallback,
                    )
                    fallback = _normalize_message(fallback)
                    if fallback:
                        slots["description"] = fallback[:5000]
            if (
                "description" not in slots
                and "title" not in slots
                and "state_id" not in slots
                and "priority" not in slots
                and ":" in text
            ):
                slots["description"] = text.split(":", 1)[1].strip()
            return UnderstandingResult(
                request_type="saas_execution",
                intent="update_issue",
                service="linear",
                slots=slots,
                missing_slots=[],
                confidence=0.9,
            )
        if _contains_any(lower, ("삭제", "지워", "archive", "delete")) and _contains_any(lower, ("이슈", "issue")):
            issue_match = re.search(r"([A-Za-z]{2,10}-\d{1,6})", text)
            if issue_match:
                slots["issue_id"] = issue_match.group(1).strip()
            return UnderstandingResult(
                request_type="saas_execution",
                intent="delete_issue",
                service="linear",
                slots=slots,
                missing_slots=[],
                confidence=0.86,
            )
        if _contains_any(lower, ("생성", "create")) and _contains_any(lower, ("이슈", "issue")):
            title_match = re.search(r"(?:제목[:\s]+)(.+)$", text)
            if title_match:
                slots["title"] = title_match.group(1).strip()
            missing_slots.append("team_id")
            return UnderstandingResult(
                request_type="saas_execution",
                intent="create_issue",
                service="linear",
                slots=slots,
                missing_slots=missing_slots,
                confidence=0.86,
            )
        if _contains_any(lower, ("조회", "검색", "list", "search", "최근")) and _contains_any(lower, ("이슈", "issue")):
            count = _extract_first_int(text)
            if count:
                slots["limit"] = max(1, min(20, count))
            if _contains_any(lower, ("검색", "search")):
                query = re.sub(r"(linear|리니어|이슈|검색|해줘|해주세요|최근|\d+개?)", "", text, flags=re.IGNORECASE).strip()
                if query:
                    slots["query"] = query
                    return UnderstandingResult(
                        request_type="saas_execution",
                        intent="search_issues",
                        service="linear",
                        slots=slots,
                        missing_slots=[],
                        confidence=0.88,
                    )
            return UnderstandingResult(
                request_type="saas_execution",
                intent="list_issues",
                service="linear",
                slots=slots,
                missing_slots=[],
                confidence=0.88,
            )

    return UnderstandingResult(
        request_type="unsupported",
        intent=None,
        service=None,
        slots={},
        missing_slots=[],
        confidence=0.4,
    )


async def _build_understanding(user_text: str, connected_services: list[str], timezone_name: str) -> UnderstandingResult:
    settings = get_settings()
    provider = str(getattr(settings, "llm_planner_provider", "openai") or "openai").strip().lower()
    model = str(getattr(settings, "llm_planner_model", "gpt-4o-mini") or "gpt-4o-mini").strip()
    timeout_sec = max(5, int(getattr(settings, "llm_request_timeout_sec", 20)))
    system_prompt = _understanding_system_prompt()
    user_prompt = _understanding_user_prompt(
        user_message=user_text,
        connected_services=connected_services,
        timezone_name=timezone_name,
    )
    parsed: dict | None = None
    try:
        parsed = await _request_understanding_with_provider(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            openai_api_key=getattr(settings, "openai_api_key", None),
            google_api_key=getattr(settings, "google_api_key", None),
            timeout_sec=timeout_sec,
        )
        if parsed:
            coerced = _coerce_understanding(parsed)
            if coerced is not None:
                if coerced.request_type == "unsupported":
                    fallback = _build_understanding_rule(user_text=user_text, connected_services=connected_services)
                    if fallback.request_type == "saas_execution":
                        return fallback
                if coerced.service and coerced.service not in connected_services:
                    coerced.service = None
                    coerced.confidence = min(coerced.confidence, 0.5)
                return coerced
    except Exception:
        pass
    return _build_understanding_rule(user_text=user_text, connected_services=connected_services)


def _time_bounds(time_range: str, timezone_name: str) -> tuple[str, str]:
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    if time_range == "tomorrow":
        base = now + timedelta(days=1)
    elif time_range == "yesterday":
        base = now - timedelta(days=1)
    else:
        base = now
    start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    end = base.replace(hour=23, minute=59, second=59, microsecond=0)
    return start.isoformat(), end.isoformat()


def _tool_spec_path_for_service(service: str) -> Path:
    return Path(__file__).resolve().parents[1] / "tool_specs" / f"{service}.json"


def _load_service_tools(service: str) -> list[str]:
    path = _tool_spec_path_for_service(service)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("tool_name") or "").strip()
        if name:
            names.append(name)
    return names


def _intent_tool_tokens(service: str, intent: str) -> tuple[str, ...]:
    mapping: dict[tuple[str, str], tuple[str, ...]] = {
        ("google", "list_events"): ("list_events", "get_event", "list_calendars"),
        ("notion", "create_page"): ("create_page", "search", "retrieve_page"),
        ("notion", "search_pages"): ("search", "query_database", "retrieve_page"),
        ("notion", "update_page"): ("update_page", "search", "retrieve_page"),
        ("notion", "append_page_content"): ("append_block_children", "search", "retrieve_page"),
        ("notion", "delete_page"): ("update_page", "retrieve_page", "search"),
        ("linear", "create_issue"): ("create_issue", "list_teams", "search_issues"),
        ("linear", "list_issues"): ("list_issues", "search_issues", "list_teams"),
        ("linear", "search_issues"): ("search_issues", "list_issues", "list_teams"),
        ("linear", "update_issue"): ("update_issue", "search_issues", "list_issues"),
        ("linear", "delete_issue"): ("update_issue", "search_issues", "list_issues"),
    }
    return mapping.get((service, intent), ())


def _retrieve_tools_top_k(*, service: str, intent: str, top_k: int = 3) -> list[str]:
    names = _load_service_tools(service)
    if not names:
        return []
    tokens = _intent_tool_tokens(service, intent)
    if not tokens:
        return names[: max(1, top_k)]
    ranked: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for name in names:
            if token in name and name not in seen:
                ranked.append(name)
                seen.add(name)
    for name in names:
        if name in seen:
            continue
        ranked.append(name)
        seen.add(name)
    return ranked[: max(1, top_k)]


def _resolve_contract_tool(contract: RequestContract, top_k: int = 3) -> RequestContract:
    if not contract.service or contract.intent == "unsupported":
        return contract
    candidates = _retrieve_tools_top_k(service=contract.service, intent=contract.intent, top_k=top_k)
    contract.tool_candidates = list(candidates)
    if not contract.tool_name and candidates:
        contract.tool_name = candidates[0]
        return contract
    if contract.tool_name and contract.tool_name in candidates:
        return contract
    if candidates:
        contract.tool_name = candidates[0]
    return contract


def _build_request_contract(understanding: UnderstandingResult, timezone_name: str) -> RequestContract:
    intent = str(understanding.intent or "")
    service = str(understanding.service or "")
    slots = dict(understanding.slots)
    autofilled: list[str] = []

    if intent == "list_events" and service == "google":
        tool_name = "google_calendar_list_events"
        time_range = str(slots.get("time_range") or "today")
        time_min, time_max = _time_bounds(time_range, timezone_name)
        slots["time_min"] = time_min
        slots["time_max"] = time_max
        autofilled.extend(["time_min", "time_max"])
        if "max_results" not in slots:
            slots["max_results"] = int(slots.get("limit") or 5)
            autofilled.append("max_results")
        if "time_zone" not in slots:
            slots["time_zone"] = timezone_name
            autofilled.append("time_zone")
        clarification_needed = ["calendar_id"] if not slots.get("calendar_id") else []
        expected_output = {"type": "list", "count": int(slots.get("max_results") or 5), "format": "bullet"}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "create_page" and service == "notion":
        tool_name = "notion_create_page"
        if "title" not in slots:
            slots["title"] = "새 페이지"
            autofilled.append("title")
        if not isinstance(slots.get("parent"), dict):
            database_id = str(slots.get("database_id") or "").strip()
            if database_id:
                slots["parent"] = {"database_id": database_id}
            else:
                slots["parent"] = {"workspace": True}
            autofilled.append("parent")
        if not isinstance(slots.get("properties"), dict):
            title = str(slots.get("title") or "새 페이지")
            slots["properties"] = {
                "title": {
                    "title": [{"type": "text", "text": {"content": title[:100]}}],
                }
            }
            autofilled.append("properties")
        clarification_needed: list[str] = []
        expected_output = {"type": "object", "required_keys": ["id", "url"]}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "search_pages" and service == "notion":
        tool_name = "notion_search"
        if "page_size" not in slots:
            slots["page_size"] = int(slots.get("limit") or 5)
            autofilled.append("page_size")
        expected_output = {"type": "list", "count": int(slots.get("page_size") or 5), "format": "bullet"}
        return RequestContract(intent, service, tool_name, slots, [], autofilled, expected_output)

    if intent == "update_page" and service == "notion":
        tool_name = "notion_update_page"
        clarification_needed = ["page_id"] if not slots.get("page_id") else []
        if slots.get("new_title"):
            slots["properties"] = {"title": {"title": [{"type": "text", "text": {"content": str(slots.get("new_title"))}}]}}
            autofilled.append("properties")
        expected_output = {"type": "object", "required_keys": []}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "append_page_content" and service == "notion":
        tool_name = "notion_append_block_children"
        clarification_needed = ["block_id"] if not slots.get("block_id") else []
        content = str(slots.get("content") or "").strip()
        if content:
            slots["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
                }
            ]
            autofilled.append("children")
        else:
            clarification_needed.append("content")
        expected_output = {"type": "object", "required_keys": []}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "delete_page" and service == "notion":
        tool_name = "notion_update_page"
        slots["in_trash"] = True
        clarification_needed = []
        if not slots.get("page_id"):
            clarification_needed.append("page_id")
        if "approval_confirmed" not in slots:
            clarification_needed.append("approval_confirmed")
        expected_output = {"type": "object", "required_keys": ["id"]}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "create_issue" and service == "linear":
        tool_name = "linear_create_issue"
        if "title" not in slots:
            slots["title"] = "새 이슈"
            autofilled.append("title")
        clarification_needed = ["team_id"] if not slots.get("team_id") else []
        if "priority" not in slots:
            slots["priority"] = 3
            autofilled.append("priority")
        expected_output = {"type": "object", "required_keys": ["id"]}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "list_issues" and service == "linear":
        tool_name = "linear_list_issues"
        if "first" not in slots:
            slots["first"] = int(slots.get("limit") or 5)
            autofilled.append("first")
        expected_output = {"type": "list", "count": int(slots.get("first") or 5), "format": "bullet"}
        return RequestContract(intent, service, tool_name, slots, [], autofilled, expected_output)

    if intent == "search_issues" and service == "linear":
        tool_name = "linear_search_issues"
        if "first" not in slots:
            slots["first"] = int(slots.get("limit") or 5)
            autofilled.append("first")
        clarification_needed = ["query"] if not slots.get("query") else []
        expected_output = {"type": "list", "count": int(slots.get("first") or 5), "format": "bullet"}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "update_issue" and service == "linear":
        tool_name = "linear_update_issue"
        clarification_needed = []
        if not slots.get("issue_id"):
            clarification_needed.append("issue_id")
        if not any(slots.get(key) not in (None, "", []) for key in ("title", "description", "state_id", "priority")):
            clarification_needed.append("update_fields")
        expected_output = {"type": "object", "required_keys": []}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    if intent == "delete_issue" and service == "linear":
        tool_name = "linear_update_issue"
        slots["archived"] = True
        clarification_needed = []
        if not slots.get("issue_id"):
            clarification_needed.append("issue_id")
        if "approval_confirmed" not in slots:
            clarification_needed.append("approval_confirmed")
        expected_output = {"type": "object", "required_keys": ["id"]}
        return RequestContract(intent, service, tool_name, slots, clarification_needed, autofilled, expected_output)

    return RequestContract(
        intent="unsupported",
        service=service or "unknown",
        tool_name="",
        slots=slots,
        clarification_needed=[],
        autofilled=[],
        expected_output={},
    )


def _build_agent_plan(user_text: str, contract: RequestContract) -> AgentPlan:
    task = AgentTask(
        id=f"task_{contract.tool_name or 'unsupported'}",
        title=f"Atomic task: {contract.intent}",
        task_type="TOOL",
        service=contract.service,
        tool_name=contract.tool_name,
        payload=contract.slots,
    )
    return AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary=f"{contract.service}:{contract.intent}")],
        target_services=[contract.service],
        selected_tools=list(contract.tool_candidates or ([contract.tool_name] if contract.tool_name else [])),
        workflow_steps=[
            "1. Request Understanding",
            "2. Request Contract",
            "3. Atomic Planner",
            "4. Executor",
            "5. Expectation Verification",
        ],
        tasks=[task] if contract.tool_name else [],
        notes=[
            "planner=atomic_overhaul_v1",
            "execution_mode=atomic_first",
            f"tool_retrieval_top_k={len(contract.tool_candidates or [])}",
        ],
    )


def _build_clarification_response(plan: AgentPlan, missing_slot: str, phase: str) -> AgentRunResult:
    execution = AgentExecutionResult(
        success=False,
        user_message=f"`{missing_slot}` 값이 필요합니다. 값을 보내주시면 이어서 실행합니다.",
        summary="Clarification required",
        artifacts={"error_code": "clarification_needed", "clarification_phase": phase, "missing_slot": missing_slot},
        steps=[AgentExecutionStep(name=f"clarification_{phase}", status="error", detail=f"missing_slot:{missing_slot}")],
    )
    return AgentRunResult(
        ok=False,
        stage="clarification",
        plan=plan,
        result_summary=execution.summary,
        execution=execution,
        plan_source="atomic_overhaul_v1",
    )


def _extract_attempt_count(plan: AgentPlan, phase: str) -> int:
    prefix = f"clarification_{phase}_attempts="
    for note in plan.notes:
        if note.startswith(prefix):
            try:
                return int(note.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def _set_attempt_count(plan: AgentPlan, phase: str, value: int) -> None:
    prefix = f"clarification_{phase}_attempts="
    plan.notes = [note for note in plan.notes if not note.startswith(prefix)]
    plan.notes.append(f"{prefix}{value}")


def _missing_slot_prompt(slot_name: str) -> str:
    mapping = {
        "calendar_id": "어느 캘린더를 조회할까요? 예: primary",
        "database_id": "어느 Notion 데이터베이스에 생성할까요? database_id를 입력해주세요.",
        "team_id": "어느 Linear 팀에 생성할까요? team_id를 입력해주세요.",
        "page_id": "어느 페이지를 삭제할까요? page_id를 입력해주세요.",
        "issue_id": "어느 이슈를 수정할까요? issue_id를 입력해주세요. 예: OPS-42",
        "update_fields": "무엇을 수정할지 알려주세요. 예: 제목: ..., 설명: ..., 상태: Todo, 우선순위: 2",
        "approval_confirmed": "파괴적 작업입니다. 진행하려면 `yes` 또는 `승인`이라고 입력해주세요.",
    }
    return mapping.get(slot_name, f"{slot_name} 값을 입력해주세요.")


def _extract_slot_value(user_text: str, slot_name: str) -> str:
    value = _normalize_message(user_text)
    if slot_name == "title":
        match = re.search(r"(?i)^(?:제목|title)\s*[:：]\s*(.+)$", value)
        if match:
            parsed = match.group(1).strip()
            if parsed:
                return parsed
    if slot_name == "team_id":
        match = re.search(r"(?i)^(?:팀|team)\s*[:：]\s*(.+)$", value)
        if match:
            parsed = match.group(1).strip()
            if parsed:
                return parsed
    return value


def _merge_pending_slot(plan: AgentPlan, user_text: str, missing_slot: str) -> AgentPlan:
    value = _extract_slot_value(user_text, missing_slot)
    if missing_slot == "approval_confirmed":
        lowered = value.lower()
        value = "yes" if lowered in {"yes", "y", "승인", "확인", "동의", "네", "예"} else "no"
    for task in plan.tasks:
        if task.task_type == "TOOL":
            task.payload = dict(task.payload or {})
            if missing_slot == "update_fields":
                title_text = _extract_linear_update_title(user_text)
                description_text = _extract_linear_update_description(user_text)
                state_value = _extract_linear_update_state(user_text)
                priority_value = _extract_linear_update_priority(user_text)
                if title_text:
                    task.payload["title"] = title_text
                if description_text:
                    task.payload["description"] = description_text
                if state_value:
                    task.payload["state_id"] = state_value
                if priority_value is not None:
                    task.payload["priority"] = priority_value
                if _is_linear_description_append_intent(user_text):
                    task.payload["description_append"] = "1"
            else:
                task.payload[missing_slot] = value
    return plan


async def _resolve_linear_team_id(user_id: str, team_ref: str) -> str | None:
    ref = str(team_ref or "").strip()
    if not ref:
        return None
    # Already looks like an id.
    if re.fullmatch(r"[A-Za-z0-9\-]{8,}", ref):
        return ref
    try:
        result = await execute_tool(user_id=user_id, tool_name="linear_list_teams", payload={"first": 20})
    except Exception:
        return None
    data = result.get("data")
    nodes: list[dict] = []
    if isinstance(data, dict):
        if isinstance(data.get("nodes"), list):
            nodes = [item for item in data.get("nodes") if isinstance(item, dict)]
        elif isinstance(data.get("teams"), dict) and isinstance(data.get("teams", {}).get("nodes"), list):
            nodes = [item for item in data.get("teams", {}).get("nodes") if isinstance(item, dict)]
    target = ref.lower()
    for node in nodes:
        team_name = str(node.get("name") or "").strip().lower()
        team_key = str(node.get("key") or "").strip().lower()
        if target and (target == team_name or target == team_key):
            team_id = str(node.get("id") or "").strip()
            if team_id:
                return team_id
    return None


def _extract_linear_issue_nodes(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("nodes"), list):
        return [item for item in payload.get("nodes") if isinstance(item, dict)]
    issues = payload.get("issues")
    if isinstance(issues, dict) and isinstance(issues.get("nodes"), list):
        return [item for item in issues.get("nodes") if isinstance(item, dict)]
    return []


async def _resolve_linear_issue_for_update(user_id: str, issue_ref: str) -> tuple[str, str, str, str]:
    ref = str(issue_ref or "").strip()
    if not ref:
        return "", "", "", ""
    if _looks_like_linear_internal_issue_id(ref):
        return ref, "", "", ""
    queries = [{"tool_name": "linear_search_issues", "payload": {"query": ref, "first": 10}}]
    queries.append({"tool_name": "linear_list_issues", "payload": {"first": 20}})
    for query in queries:
        try:
            result = await execute_tool(user_id=user_id, tool_name=query["tool_name"], payload=query["payload"])
        except Exception:
            continue
        data = (result or {}).get("data") if isinstance(result, dict) else {}
        nodes = _extract_linear_issue_nodes(data)
        target = ref.lower()
        exact: dict | None = None
        fuzzy: dict | None = None
        for node in nodes:
            issue_id = str(node.get("id") or "").strip()
            if not issue_id:
                continue
            identifier = str(node.get("identifier") or "").strip().lower()
            title = str(node.get("title") or "").strip().lower()
            if target in {identifier, issue_id.lower(), title}:
                exact = node
                break
            if target and (target in identifier or target in title):
                fuzzy = fuzzy or node
        matched = exact or fuzzy
        if matched:
            return (
                str(matched.get("id") or "").strip(),
                str(matched.get("url") or "").strip(),
                str(matched.get("description") or "").strip(),
                str(((matched.get("team") or {}) if isinstance(matched.get("team"), dict) else {}).get("id") or "").strip(),
            )
    return "", "", "", ""


async def _resolve_linear_state_id(user_id: str, state_value: str, team_id: str | None = None) -> str:
    candidate = str(state_value or "").strip()
    if not candidate:
        return ""
    if _looks_like_linear_internal_issue_id(candidate):
        return candidate
    normalized = _normalize_linear_state_name(candidate)
    if not normalized:
        return ""
    try:
        listed_states = await execute_tool(user_id=user_id, tool_name="linear_list_workflow_states", payload={"first": 200})
        data_states = (listed_states or {}).get("data") if isinstance(listed_states, dict) else {}
        workflow_states = (((data_states or {}).get("workflowStates") or {}).get("nodes") if isinstance(data_states, dict) else None) or []
        if isinstance(workflow_states, list):
            for state in workflow_states:
                if not isinstance(state, dict):
                    continue
                state_name = str(state.get("name") or "").strip()
                state_id = str(state.get("id") or "").strip()
                state_team_id = str(((state.get("team") or {}) if isinstance(state.get("team"), dict) else {}).get("id") or "").strip()
                if team_id and state_team_id and team_id != state_team_id:
                    continue
                if state_name and state_id and _normalize_linear_state_name(state_name) == normalized:
                    return state_id
    except Exception:
        pass
    try:
        listed = await execute_tool(user_id=user_id, tool_name="linear_list_issues", payload={"first": 20})
    except Exception:
        return ""
    data = (listed or {}).get("data") if isinstance(listed, dict) else {}
    nodes = _extract_linear_issue_nodes(data)
    for node in nodes:
        state = node.get("state") if isinstance(node, dict) else None
        if not isinstance(state, dict):
            continue
        state_name = str(state.get("name") or "").strip()
        state_id = str(state.get("id") or "").strip()
        if state_name and state_id and _normalize_linear_state_name(state_name) == normalized:
            return state_id
    return ""


def _parse_error_status(detail: str) -> int | None:
    match = re.search(r"status=(\d{3})", detail or "")
    if not match:
        return None
    return int(match.group(1))


def _map_tool_error_code(detail: str | None) -> str:
    lower = str(detail or "").strip().lower()
    if not lower:
        return "tool_failed"
    if any(token in lower for token in ("auth_required", "auth_error", "unauthorized", "forbidden", "oauth")):
        return "auth_error"
    if any(token in lower for token in ("validation", "bad_request", "invalid")):
        return "validation_error"
    return "tool_failed"


def _is_approval_confirmed(value: object) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {"yes", "y", "true", "1", "승인", "확인", "동의", "네", "예"}


def _is_cancel_message(user_text: str) -> bool:
    lowered = _normalize_message(user_text).lower()
    return lowered in {"취소", "cancel", "/cancel", "중단", "그만", "stop"}


def _risk_gate_missing_slot(contract: RequestContract) -> str | None:
    payload = contract.slots or {}
    tool_name = str(contract.tool_name or "").lower()

    destructive = False
    if "delete" in tool_name or "archive" in tool_name:
        destructive = True
    if bool(payload.get("archived")) or bool(payload.get("in_trash")):
        destructive = True

    external_target = any(str(payload.get(key) or "").strip() for key in ("channel", "recipient", "to", "email"))
    if destructive or external_target:
        if not _is_approval_confirmed(payload.get("approval_confirmed")):
            return "approval_confirmed"
    return None


async def _execute_with_retry(user_id: str, tool_name: str, payload: dict[str, object]) -> tuple[dict[str, object] | None, list[AgentExecutionStep], str | None]:
    steps: list[AgentExecutionStep] = []
    for attempt in (1, 2):
        try:
            result = await execute_tool(user_id=user_id, tool_name=tool_name, payload=payload)
            steps.append(AgentExecutionStep(name=f"executor_call_{attempt}", status="success", detail=tool_name))
            return result, steps, None
        except HTTPException as exc:
            detail = str(exc.detail or "")
            status_code = _parse_error_status(detail)
            retryable = "RATE_LIMITED" in detail or "timeout" in detail.lower() or (status_code is not None and status_code >= 500)
            steps.append(AgentExecutionStep(name=f"executor_call_{attempt}", status="error", detail=detail))
            if attempt == 1 and retryable:
                continue
            return None, steps, detail
    return None, steps, "unknown_tool_error"


def _sanitize_payload_for_tool(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
    # Atomic planner may keep helper slots (e.g. page_title/content) in the contract.
    # Drop keys that are outside runtime tool input schema to avoid upstream 4xx.
    sanitized = dict(payload or {})
    try:
        tool = load_registry().get_tool(tool_name)
    except Exception:
        return sanitized
    schema = tool.input_schema or {}
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return sanitized
    allowed = set(properties.keys())
    if "idempotency_key" in sanitized:
        allowed.add("idempotency_key")
    return {key: value for key, value in sanitized.items() if key in allowed}


def _extract_list_items(tool_name: str, tool_result: dict[str, object]) -> list[dict]:
    if tool_name == "google_calendar_list_events":
        payload = tool_result.get("data")
        if isinstance(payload, dict):
            items = payload.get("items")
            return items if isinstance(items, list) else []
    if tool_name == "notion_search":
        payload = tool_result.get("data")
        if isinstance(payload, dict):
            items = payload.get("results")
            return items if isinstance(items, list) else []
    if tool_name in {"linear_list_issues", "linear_search_issues"}:
        payload = tool_result.get("data")
        if isinstance(payload, dict):
            if isinstance(payload.get("nodes"), list):
                return payload.get("nodes")  # type: ignore[return-value]
            if isinstance(payload.get("issues"), dict):
                nodes = payload.get("issues", {}).get("nodes")
                return nodes if isinstance(nodes, list) else []
    return []


def _notion_first_result_id(tool_result: dict[str, object]) -> str | None:
    payload = tool_result.get("data")
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        if str(item.get("object") or "").strip() != "page":
            continue
        value = str(item.get("id") or "").strip()
        if value:
            return value
    return None


async def _hydrate_notion_target_slots(
    *,
    user_id: str,
    contract: RequestContract,
) -> tuple[RequestContract, list[AgentExecutionStep]]:
    steps: list[AgentExecutionStep] = []
    if contract.service != "notion":
        return contract, steps
    page_title = str(contract.slots.get("page_title") or "").strip()
    if not page_title:
        return contract, steps

    needs_page_id = contract.intent == "update_page" and not str(contract.slots.get("page_id") or "").strip()
    needs_block_id = contract.intent == "append_page_content" and not str(contract.slots.get("block_id") or "").strip()
    if not (needs_page_id or needs_block_id):
        return contract, steps

    lookup_result, lookup_steps, _ = await _execute_with_retry(
        user_id=user_id,
        tool_name="notion_search",
        payload={"query": page_title, "page_size": 1},
    )
    for step in lookup_steps:
        step.name = f"prefetch_{step.name}"
    steps.extend(lookup_steps)
    if lookup_result is None:
        return contract, steps

    resolved_id = _notion_first_result_id(lookup_result)
    if not resolved_id:
        return contract, steps

    if needs_page_id:
        contract.slots["page_id"] = resolved_id
        contract.clarification_needed = [slot for slot in contract.clarification_needed if slot != "page_id"]
    if needs_block_id:
        contract.slots["block_id"] = resolved_id
        contract.clarification_needed = [slot for slot in contract.clarification_needed if slot != "block_id"]
    return contract, steps


def _render_success_message(contract: RequestContract, tool_result: dict[str, object]) -> str:
    if contract.expected_output.get("type") == "list":
        items = _extract_list_items(contract.tool_name, tool_result)
        lines = [f"요청 결과 {len(items)}건입니다."]
        for item in items[: int(contract.expected_output.get("count") or 5)]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("identifier") or "(제목 없음)")
            lines.append(f"- {title}")
        return "\n".join(lines)
    payload = tool_result.get("data")
    if isinstance(payload, dict):
        if contract.tool_name == "linear_update_issue":
            update = payload.get("issueUpdate") if isinstance(payload.get("issueUpdate"), dict) else {}
            issue = update.get("issue") if isinstance(update.get("issue"), dict) else {}
            identifier = str(issue.get("identifier") or "").strip()
            title = str(issue.get("title") or "").strip()
            url = str(issue.get("url") or "").strip()
            label = identifier or title or str(contract.slots.get("issue_id") or "-")
            lines = ["작업결과", f"- Linear 이슈를 업데이트했습니다. ({label})", "", "링크"]
            lines.append(f"- {url}" if url else "- 링크 없음")
            return "\n".join(lines)
        if contract.tool_name == "linear_create_issue":
            create = payload.get("issueCreate") if isinstance(payload.get("issueCreate"), dict) else {}
            issue = create.get("issue") if isinstance(create.get("issue"), dict) else {}
            identifier = str(issue.get("identifier") or "").strip()
            title = str(issue.get("title") or "").strip()
            url = str(issue.get("url") or "").strip()
            label = identifier or title or str(contract.slots.get("title") or "-")
            lines = ["작업결과", f"- Linear 이슈를 생성했습니다. ({label})", "", "링크"]
            lines.append(f"- {url}" if url else "- 링크 없음")
            return "\n".join(lines)
        if contract.tool_name in {"notion_create_page", "notion_update_page", "notion_append_block_children"}:
            url = str(payload.get("url") or "").strip()
            lines = ["작업결과", "- Notion 페이지 작업을 완료했습니다.", "", "링크"]
            lines.append(f"- {url}" if url else "- 링크 없음")
            return "\n".join(lines)
        ref = str(payload.get("id") or payload.get("url") or "").strip()
        if ref:
            return f"작업결과\n- 요청을 완료했습니다.\n\n링크\n- {ref}"
    return "작업결과\n- 요청을 완료했습니다.\n\n링크\n- 링크 없음"


def _verify_expectation(contract: RequestContract, tool_result: dict[str, object], user_message: str) -> tuple[bool, str, dict[str, bool]]:
    expected_type = str(contract.expected_output.get("type") or "")
    if expected_type == "list":
        items = _extract_list_items(contract.tool_name, tool_result)
        expected_count = int(contract.expected_output.get("count") or 0)
        count_match = True
        if expected_count > 0:
            count_match = len(items) == expected_count

        date_range_match = True
        if contract.tool_name == "google_calendar_list_events":
            time_min = str(contract.slots.get("time_min") or "")
            time_max = str(contract.slots.get("time_max") or "")
            date_range_match = bool(time_min and time_max)

        format_match = True
        if str(contract.expected_output.get("format") or "") == "bullet":
            lines = [line for line in user_message.splitlines() if line.strip()]
            bullet_lines = [line for line in lines if line.strip().startswith("- ")]
            expected_bullets = min(len(items), int(contract.expected_output.get("count") or len(items)))
            format_match = len(bullet_lines) >= expected_bullets

        checks = {
            "count_match": count_match,
            "date_range_match": date_range_match,
            "format_match": format_match,
        }
        if all(checks.values()):
            return True, "list_verified", checks
        if not count_match:
            return False, "count_mismatch", checks
        if not date_range_match:
            return False, "date_range_mismatch", checks
        return False, "format_mismatch", checks
    if expected_type == "object":
        payload = tool_result.get("data")
        if not isinstance(payload, dict):
            return False, "object_missing", {"required_keys_match": False}
        if contract.tool_name == "linear_update_issue":
            update = payload.get("issueUpdate")
            if isinstance(update, dict):
                success = bool(update.get("success"))
                issue = update.get("issue")
                issue_ok = isinstance(issue, dict) and bool(str(issue.get("id") or issue.get("identifier") or "").strip())
                checks = {"issue_update_success": success, "issue_present": issue_ok}
                if success and issue_ok:
                    return True, "object_verified", checks
                return False, "issue_update_failed", checks
        required = contract.expected_output.get("required_keys") or []
        for key in required:
            if not payload.get(str(key)):
                return False, f"missing_key:{key}", {"required_keys_match": False}
        return True, "object_verified", {"required_keys_match": True}
    return True, "no_expectation", {}


async def _run_from_contract(
    *,
    user_text: str,
    user_id: str,
    contract: RequestContract,
) -> AgentRunResult:
    plan = _build_agent_plan(user_text=user_text, contract=contract)
    if not contract.tool_name:
        execution = AgentExecutionResult(
            success=False,
            user_message="지원하지 않는 요청입니다.",
            summary="Unsupported request",
            artifacts={"error_code": "unsupported_request"},
            steps=[AgentExecutionStep(name="request_contract", status="error", detail="unsupported")],
        )
        return AgentRunResult(False, "validation", plan, execution.summary, execution, "atomic_overhaul_v1")

    risk_gate_slot = _risk_gate_missing_slot(contract)
    if risk_gate_slot:
        _set_attempt_count(plan, "2", 1)
        try:
            set_pending_action(
                user_id=user_id,
                intent=contract.intent,
                action=contract.tool_name,
                task_id=plan.tasks[0].id if plan.tasks else contract.tool_name,
                plan=plan,
                plan_source="atomic_overhaul_v1_clarification2",
                collected_slots={},
                missing_slots=[risk_gate_slot],
                ttl_seconds=get_settings().pending_action_ttl_seconds,
            )
        except PendingActionStorageError:
            pass
        response = _build_clarification_response(plan, risk_gate_slot, "2")
        response.execution.user_message = _missing_slot_prompt(risk_gate_slot)
        response.execution.artifacts["error_code"] = "risk_gate_blocked"
        return response

    slots = dict(contract.slots or {})
    if contract.tool_name == "linear_update_issue":
        issue_ref = str(slots.get("issue_id") or "").strip()
        resolved_issue_id = ""
        current_issue_description = ""
        issue_team_id = ""
        if issue_ref:
            resolved_issue_id, _resolved_issue_url, current_issue_description, issue_team_id = await _resolve_linear_issue_for_update(
                user_id=user_id,
                issue_ref=issue_ref,
            )
            if resolved_issue_id:
                slots["issue_id"] = resolved_issue_id
        state_value = str(slots.get("state_id") or "").strip()
        if state_value and not _looks_like_linear_internal_issue_id(state_value):
            resolved_state_id = await _resolve_linear_state_id(
                user_id=user_id,
                state_value=state_value,
                team_id=issue_team_id or None,
            )
            if resolved_state_id:
                slots["state_id"] = resolved_state_id
        append_intent = str(slots.get("description_append") or "").strip().lower() in {"1", "true", "yes", "y"}
        description = str(slots.get("description") or "").strip()
        if append_intent and description:
            slots["description"] = _merge_linear_description(current=current_issue_description, addition=description)

    tool_payload = _sanitize_payload_for_tool(contract.tool_name, slots)
    tool_result, steps, tool_error = await _execute_with_retry(
        user_id=user_id,
        tool_name=contract.tool_name,
        payload=tool_payload,
    )
    if tool_result is None:
        mapped_error_code = _map_tool_error_code(tool_error)
        user_message = "API 호출에 실패했습니다. 잠시 후 다시 시도해주세요."
        if mapped_error_code == "auth_error":
            user_message = "권한이 부족하거나 만료되었습니다. 해당 서비스 권한을 다시 승인해주세요."
        elif mapped_error_code == "validation_error":
            user_message = "요청 값이 올바르지 않습니다. 입력을 확인한 뒤 다시 시도해주세요."
        execution = AgentExecutionResult(
            success=False,
            user_message=user_message,
            summary="Executor failed",
            artifacts={"error_code": mapped_error_code, "tool_error": str(tool_error or "")},
            steps=steps,
        )
        return AgentRunResult(False, "execution", plan, execution.summary, execution, "atomic_overhaul_v1")

    user_message = _render_success_message(contract, tool_result)
    verified, verification_reason, verification_checks = _verify_expectation(contract, tool_result, user_message)
    retried_for_verification = False
    if not verified:
        retry_result, retry_steps, retry_error = await _execute_with_retry(
            user_id=user_id,
            tool_name=contract.tool_name,
            payload=tool_payload,
        )
        for step in retry_steps:
            step.name = f"verification_retry_{step.name}"
        steps.extend(retry_steps)
        if retry_result is not None:
            retried_for_verification = True
            tool_result = retry_result
            user_message = _render_success_message(contract, tool_result)
            verified, verification_reason, verification_checks = _verify_expectation(contract, tool_result, user_message)
        else:
            steps.append(
                AgentExecutionStep(
                    name="verification_retry",
                    status="error",
                    detail=str(retry_error or "retry_failed"),
                )
            )

    steps.append(
        AgentExecutionStep(
            name="expectation_verification",
            status="success" if verified else "error",
            detail=verification_reason,
        )
    )
    if contract.autofilled:
        user_message = f"{user_message}\n\n가정값: {', '.join(contract.autofilled)}"
    execution = AgentExecutionResult(
        success=verified,
        user_message=user_message,
        summary="Atomic pipeline completed" if verified else "Expectation verification failed",
        artifacts={
            "verified": "1" if verified else "0",
            "tool_name": contract.tool_name,
            "tool_candidates": ",".join(contract.tool_candidates or []),
            "verification_reason": verification_reason,
            "verification_checks": json.dumps(verification_checks, ensure_ascii=False),
            "verification_retry_attempted": "1" if retried_for_verification else "0",
        },
        steps=steps,
    )
    return AgentRunResult(verified, "execution", plan, execution.summary, execution, "atomic_overhaul_v1")


def _is_connected(service: str | None, connected_services: list[str]) -> bool:
    if not service:
        return False
    normalized = {item.strip().lower() for item in connected_services if item and item.strip()}
    return service in normalized


async def _resume_pending_if_exists(user_text: str, user_id: str) -> AgentRunResult | None:
    pending = get_pending_action(user_id)
    if pending is None:
        return None
    if _is_cancel_message(user_text):
        clear_pending_action(user_id)
        execution = AgentExecutionResult(
            success=False,
            user_message="진행 중인 요청을 취소했습니다.",
            summary="Pending action cancelled",
            artifacts={"error_code": "pending_action_cancelled"},
            steps=[AgentExecutionStep(name="pending_action_cancel", status="success", detail="user_cancelled")],
        )
        return AgentRunResult(False, "clarification", pending.plan, execution.summary, execution, "atomic_overhaul_v1")
    if float(getattr(pending, "expires_at", 0.0) or 0.0) <= time.time():
        clear_pending_action(user_id)
        execution = AgentExecutionResult(
            success=False,
            user_message="이전 요청이 만료되었습니다. 처음부터 다시 요청해주세요.",
            summary="Pending action expired",
            artifacts={"error_code": "pending_action_expired"},
            steps=[AgentExecutionStep(name="pending_action_expired", status="error", detail="expired")],
        )
        return AgentRunResult(False, "clarification", pending.plan, execution.summary, execution, "atomic_overhaul_v1")
    plan = pending.plan
    if not pending.missing_slots:
        clear_pending_action(user_id)
        return None

    phase = "1" if pending.plan_source.endswith("clarification1") else "2"
    attempts = _extract_attempt_count(plan, phase)
    if attempts >= CLARIFICATION_MAX_TURNS:
        clear_pending_action(user_id)
        execution = AgentExecutionResult(
            success=False,
            user_message="요청을 정확히 이해하지 못했습니다. 다시 구체적으로 요청해주세요.",
            summary="Clarification exceeded",
            artifacts={"error_code": "clarification_exceeded"},
            steps=[AgentExecutionStep(name="clarification_limit", status="error", detail=f"phase={phase}")],
        )
        return AgentRunResult(False, "clarification", plan, execution.summary, execution, "atomic_overhaul_v1")

    missing_slot = pending.missing_slots[0]
    updated = _merge_pending_slot(plan, user_text, missing_slot)
    if pending.action == "linear_create_issue" and missing_slot == "team_id":
        task = next((item for item in updated.tasks if item.task_type == "TOOL"), None)
        if task is not None:
            payload = dict(task.payload or {})
            resolved_team_id = await _resolve_linear_team_id(user_id=user_id, team_ref=str(payload.get("team_id") or ""))
            if resolved_team_id:
                payload["team_id"] = resolved_team_id
                task.payload = payload
    clear_pending_action(user_id)
    if len(pending.missing_slots) > 1:
        remaining = pending.missing_slots[1:]
        _set_attempt_count(updated, phase, attempts + 1)
        try:
            set_pending_action(
                user_id=user_id,
                intent=pending.intent,
                action=pending.action,
                task_id=pending.task_id,
                plan=updated,
                plan_source=pending.plan_source,
                collected_slots={},
                missing_slots=remaining,
                ttl_seconds=get_settings().pending_action_ttl_seconds,
            )
        except PendingActionStorageError:
            pass
        return _build_clarification_response(updated, remaining[0], phase)

    task = next((item for item in updated.tasks if item.task_type == "TOOL"), None)
    if task is None:
        execution = AgentExecutionResult(
            success=False,
            user_message="내부 상태를 복구하지 못했습니다. 요청을 다시 시도해주세요.",
            summary="Pending task missing",
            artifacts={"error_code": "pending_task_missing"},
            steps=[AgentExecutionStep(name="pending_resume", status="error", detail="missing_tool_task")],
        )
        return AgentRunResult(False, "validation", updated, execution.summary, execution, "atomic_overhaul_v1")

    contract = RequestContract(
        intent=pending.intent,
        service=str(task.service or ""),
        tool_name=str(task.tool_name or ""),
        slots=dict(task.payload or {}),
        clarification_needed=[],
        autofilled=[],
        expected_output={"type": "list"} if "list" in str(task.tool_name or "") else {"type": "object"},
    )
    return await _run_from_contract(user_text=updated.user_text, user_id=user_id, contract=contract)


async def run_atomic_overhaul_analysis(user_text: str, connected_services: list[str], user_id: str) -> AgentRunResult:
    connected = [item.strip().lower() for item in connected_services if item and item.strip() in SUPPORTED_SERVICES]
    timezone_name = "Asia/Seoul"

    resumed = await _resume_pending_if_exists(user_text=user_text, user_id=user_id)
    if resumed is not None:
        return resumed

    understanding = await _build_understanding(user_text, connected, timezone_name)
    if understanding.request_type == "unsupported" or understanding.confidence < CONFIDENCE_THRESHOLD:
        fallback_understanding = _build_understanding_rule(user_text=user_text, connected_services=connected)
        if (
            fallback_understanding.request_type == "saas_execution"
            and fallback_understanding.confidence >= CONFIDENCE_THRESHOLD
        ):
            understanding = fallback_understanding

    plan = AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary="atomic_overhaul")],
        target_services=[understanding.service] if understanding.service else [],
        selected_tools=[],
        workflow_steps=["1. Request Understanding"],
        tasks=[],
        notes=["planner=atomic_overhaul_v1"],
    )

    if understanding.request_type == "unsupported" or understanding.confidence < CONFIDENCE_THRESHOLD:
        execution = AgentExecutionResult(
            success=False,
            user_message="지원하지 않는 요청입니다. SaaS 실행 요청으로 다시 입력해주세요.",
            summary="Unsupported or low confidence request",
            artifacts={"error_code": "unsupported_request", "confidence": f"{understanding.confidence:.2f}"},
            steps=[AgentExecutionStep(name="request_understanding", status="error", detail="unsupported_or_low_confidence")],
        )
        return AgentRunResult(False, "validation", plan, execution.summary, execution, "atomic_overhaul_v1")

    if not _is_connected(understanding.service, connected):
        execution = AgentExecutionResult(
            success=False,
            user_message=f"{understanding.service} 서비스가 연결되어 있지 않습니다. OAuth 연결 후 다시 시도해주세요.",
            summary="Service not connected",
            artifacts={"error_code": "service_not_connected", "service": str(understanding.service or "")},
            steps=[AgentExecutionStep(name="oauth_check", status="error", detail="not_connected")],
        )
        return AgentRunResult(False, "validation", plan, execution.summary, execution, "atomic_overhaul_v1")

    contract = _resolve_contract_tool(_build_request_contract(understanding, timezone_name), top_k=3)
    if contract.intent == "unsupported" or not contract.tool_name:
        fallback_understanding = _build_understanding_rule(user_text=user_text, connected_services=connected)
        if fallback_understanding.request_type == "saas_execution":
            fallback_contract = _resolve_contract_tool(
                _build_request_contract(fallback_understanding, timezone_name),
                top_k=3,
            )
            if fallback_contract.intent != "unsupported" and bool(fallback_contract.tool_name):
                understanding = fallback_understanding
                contract = fallback_contract

    if contract.tool_name == "":
        unsupported_contract = contract.intent == "unsupported"
        execution = AgentExecutionResult(
            success=False,
            user_message=(
                "지원하지 않는 요청입니다. SaaS 실행 요청으로 다시 입력해주세요."
                if unsupported_contract
                else "해당 요청을 처리할 도구를 찾지 못했습니다."
            ),
            summary="Unsupported request" if unsupported_contract else "Tool retrieval failed",
            artifacts={
                "error_code": "unsupported_request" if unsupported_contract else "tool_not_found",
                "service": contract.service,
                "intent": contract.intent,
            },
            steps=[AgentExecutionStep(name="tool_retrieval", status="error", detail="empty_candidates")],
        )
        return AgentRunResult(False, "validation", plan, execution.summary, execution, "atomic_overhaul_v1")
    contract, prefetch_steps = await _hydrate_notion_target_slots(user_id=user_id, contract=contract)
    plan = _build_agent_plan(user_text, contract)

    if contract.clarification_needed:
        missing_slot = contract.clarification_needed[0]
        _set_attempt_count(plan, "2", 1)
        try:
            set_pending_action(
                user_id=user_id,
                intent=contract.intent,
                action=contract.tool_name,
                task_id=plan.tasks[0].id if plan.tasks else contract.tool_name,
                plan=plan,
                plan_source="atomic_overhaul_v1_clarification2",
                collected_slots={},
                missing_slots=list(contract.clarification_needed),
                ttl_seconds=get_settings().pending_action_ttl_seconds,
            )
        except PendingActionStorageError:
            pass
        response = _build_clarification_response(plan, missing_slot, "2")
        if prefetch_steps:
            response.execution.steps = list(prefetch_steps) + list(response.execution.steps or [])
        response.execution.user_message = _missing_slot_prompt(missing_slot)
        if missing_slot == "approval_confirmed":
            response.execution.artifacts["error_code"] = "risk_gate_blocked"
        return response

    return await _run_from_contract(
        user_text=user_text,
        user_id=user_id,
        contract=contract,
    )
