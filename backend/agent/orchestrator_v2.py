from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from agent.skill_contracts import (
    infer_skill_name_from_runtime_tools,
    runtime_tools_for_services,
    runtime_tools_for_skill,
    service_for_skill,
    validate_all_contracts,
)
from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan, AgentRequirement, AgentRunResult
from app.core.config import get_settings

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

MODE_LLM_ONLY = "LLM_ONLY"
MODE_LLM_THEN_SKILL = "LLM_THEN_SKILL"
MODE_SKILL_THEN_LLM = "SKILL_THEN_LLM"


class NeedsInputSignal(Exception):
    def __init__(
        self,
        *,
        missing_fields: list[str],
        questions: list[str],
        choices: dict | None = None,
    ) -> None:
        self.missing_fields = missing_fields
        self.questions = questions
        self.choices = choices or {}
        super().__init__("needs_input")


class RouterDecision:
    def __init__(
        self,
        *,
        mode: str,
        reason: str,
        skill_name: str | None = None,
        target_services: list[str] | None = None,
        selected_tools: list[str] | None = None,
        arguments: dict | None = None,
    ) -> None:
        self.mode = mode
        self.reason = reason
        self.skill_name = str(skill_name or "").strip() or None
        self.target_services = target_services or []
        self.selected_tools = selected_tools or []
        self.arguments = arguments or {}


def _decision_for_skill(
    *,
    mode: str,
    reason: str,
    skill_name: str,
    arguments: dict | None = None,
    target_services: list[str] | None = None,
) -> RouterDecision:
    return RouterDecision(
        mode=mode,
        reason=reason,
        skill_name=skill_name,
        target_services=target_services or [],
        selected_tools=runtime_tools_for_skill(skill_name),
        arguments=arguments or {},
    )


def _allowed_v2_tools_for_services(connected_services: list[str]) -> list[str]:
    return runtime_tools_for_services(connected_services)


def _extract_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _parse_router_payload(payload: dict, connected_services: list[str]) -> RouterDecision | None:
    allowed_keys = {"mode", "reason", "skill_name", "selected_tools", "arguments"}
    if any(key not in allowed_keys for key in payload.keys()):
        return None

    mode = str(payload.get("mode") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if mode not in {MODE_LLM_ONLY, MODE_LLM_THEN_SKILL, MODE_SKILL_THEN_LLM}:
        return None
    if not reason:
        return None

    skill_name = str(payload.get("skill_name") or "").strip() or None
    if "selected_tools" not in payload or "arguments" not in payload:
        return None
    selected_tools_raw = payload.get("selected_tools") or []
    if not isinstance(selected_tools_raw, list):
        return None
    selected_tools = [str(item).strip() for item in selected_tools_raw if str(item).strip()]
    if skill_name and not selected_tools:
        selected_tools = runtime_tools_for_skill(skill_name)
    if not skill_name and selected_tools:
        skill_name = infer_skill_name_from_runtime_tools(selected_tools)
    arguments_raw = payload.get("arguments") or {}
    arguments = arguments_raw if isinstance(arguments_raw, dict) else {}
    if not isinstance(arguments_raw, dict):
        return None

    allowed_tools = set(_allowed_v2_tools_for_services(connected_services))
    if mode == MODE_LLM_ONLY:
        if selected_tools or skill_name:
            return None
    else:
        if not selected_tools:
            return None
        if any(tool not in allowed_tools for tool in selected_tools):
            return None
        if not skill_name:
            return None

    target_services: list[str] = []
    if skill_name:
        service = service_for_skill(skill_name)
        if service:
            target_services = [service]
            if service not in {item.strip().lower() for item in connected_services if item.strip()}:
                return None
            expected_tools = set(runtime_tools_for_skill(skill_name))
            if expected_tools and any(tool not in expected_tools for tool in selected_tools):
                return None
    if not target_services:
        target_services = sorted(
            {
                "notion" if tool.startswith("notion_") else "linear"
                for tool in selected_tools
                if tool.startswith("notion_") or tool.startswith("linear_")
            }
        )
    return RouterDecision(
        mode=mode,
        reason=reason,
        skill_name=skill_name,
        target_services=target_services,
        selected_tools=selected_tools,
        arguments=arguments,
    )


async def _request_router_decision_with_llm(
    *,
    user_text: str,
    connected_services: list[str],
) -> tuple[RouterDecision | None, str | None, str | None]:
    allowed_tools = _allowed_v2_tools_for_services(connected_services)
    if not allowed_tools:
        return None, None, None

    prompt = (
        "You are a routing engine. Return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "mode": "LLM_ONLY|LLM_THEN_SKILL|SKILL_THEN_LLM",\n'
        '  "reason": "short_reason",\n'
        '  "skill_name": "optional skill contract name",\n'
        '  "selected_tools": ["tool_name"],\n'
        '  "arguments": {}\n'
        "}\n"
        "Rules:\n"
        "- If mode is LLM_ONLY, selected_tools must be [].\n"
        "- If mode includes skill, provide skill_name and selected_tools.\n"
        "- If skill_name is provided, it must map to allowed tools.\n"
        "- selected_tools must contain allowed tool names only.\n"
        "- Do not invent skill/tool names.\n"
        "- If request mentions connected service (notion/linear) and an operation, avoid LLM_ONLY.\n"
        "- For 'recent/latest/list issues' on linear, use skill_name=linear.issue_search and include arguments.linear_first.\n"
        "- For create page requests on notion, use skill_name=notion.page_create.\n"
        f"- Allowed tools: {', '.join(allowed_tools)}\n\n"
        f"[user_request]\n{user_text}\n"
    )

    try:
        raw, provider, model = await _request_llm_text(prompt=prompt)
    except Exception:
        return None, None, None

    payload = _extract_json_object(raw)
    if not payload:
        return None, provider, model
    parsed = _parse_router_payload(payload, connected_services)
    return parsed, provider, model


def _mentions_service(text: str, service: str) -> bool:
    lower = text.lower()
    if service == "notion":
        return ("notion" in lower) or ("노션" in text)
    if service == "linear":
        return ("linear" in lower) or ("리니어" in text)
    return False


def _is_write_intent(text: str) -> bool:
    lower = text.lower()
    tokens = ("생성", "만들", "기록", "저장", "등록", "작성", "추가", "create", "save", "write")
    return any(token in lower for token in tokens)


def _is_update_intent(text: str) -> bool:
    lower = text.lower()
    tokens = ("업데이트", "수정", "변경", "바꿔", "갱신", "update", "edit", "modify")
    return any(token in lower for token in tokens)


def _is_create_intent(text: str) -> bool:
    lower = text.lower()
    tokens = ("생성", "만들", "등록", "작성", "create", "new")
    return any(token in lower for token in tokens)


def _is_delete_intent(text: str) -> bool:
    lower = text.lower()
    tokens = ("삭제", "지워", "제거", "아카이브", "delete", "remove", "archive")
    return any(token in lower for token in tokens)


def _is_analysis_intent(text: str) -> bool:
    lower = text.lower()
    tokens = ("정리", "요약", "해결", "방법", "분석", "explain", "how", "solve", "summar")
    return any(token in lower for token in tokens)


def _extract_linear_issue_reference(text: str) -> str | None:
    keyed = re.search(r"\b([A-Za-z]{2,10}-\d{1,6})\b", text)
    if keyed:
        return keyed.group(1)
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    return None


def _extract_notion_page_title(text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    pattern = re.search(r"(?i)(?:notion|노션)(?:에서|의)?\s*(.+?)\s*페이지", text.strip())
    if pattern:
        candidate = pattern.group(1).strip(" \"'`")
        if candidate:
            return candidate
    return None


def _extract_notion_page_title_for_create(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    def _sanitize(candidate: str | None) -> str | None:
        value = str(candidate or "").strip(" \"'`.,")
        if not value:
            return None
        lowered = value.lower()
        if value in {"에", "의", "에서"} or lowered in {"at", "in", "on"}:
            return None
        if len(value) < 2:
            return None
        return value[:100]

    labeled = re.search(
        r"(?i)(?:제목은|title is|제목|title)\s*[:：]?\s*['\"“”]?"
        r"(.+?)"
        r"(?=(?:\s*(?:이고|이며|,|\.)?\s*(?:내용|본문|설명|description)\s*[:：])|$)",
        normalized,
    )
    if labeled:
        candidate = _sanitize(labeled.group(1))
        if candidate:
            return candidate
    page_labeled = re.search(
        r"(?i)(?:페이지\s*제목|page\s*title)\s*[:：]?\s*['\"“”]?(.+?)['\"“”]?"
        r"(?=(?:\s*(?:이고|이며|,|\.)?\s*(?:내용|본문|설명|description)\s*[:：])|$)",
        normalized,
    )
    if page_labeled:
        candidate = _sanitize(page_labeled.group(1))
        if candidate:
            return candidate
    for pattern in [
        r'(?i)(?:notion|노션)(?:에서|에|의)?\s*["“]([^"”]+)["”]\s*페이지',
        r"(?i)(?:notion|노션)(?:에서|에|의)?\s*'([^']+)'\s*페이지",
        r'(?i)["“]([^"”]+)["”]\s*(?:페이지)\s*(?:생성|만들|작성|create)',
    ]:
        match = re.search(pattern, text.strip())
        if match:
            candidate = _sanitize(match.group(1))
            if candidate:
                return candidate

    # e.g. "오늘 서울 날씨를 notion에 페이지로 생성해줘" -> "오늘 서울 날씨"
    prefix_intent = re.search(
        r"(?i)^\s*(.+?)\s*(?:을|를)\s*(?:notion|노션)(?:에서|에|의)?.*(?:페이지).*(?:생성|만들|작성|create)",
        normalized,
    )
    if prefix_intent:
        candidate = re.sub(r"(?i)^(?:기사|문서|내용)\s*", "", prefix_intent.group(1)).strip()
        candidate = _sanitize(candidate)
        if candidate:
            return candidate

    candidate = _extract_notion_page_title(text)
    return _sanitize(candidate)


def _extract_notion_update_new_title(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    patterns = [
        r'(?i)(?:페이지\s*)?(?:제목|title)(?:을|를)?\s*["“]?([^"”]+?)["”]?\s*(?:로|으로)?\s*(?:업데이트|수정|변경|바꿔|rename)',
        r'(?i)(?:새\s*제목|new\s*title)\s*[:：]?\s*["“]?([^"”]+?)["”]?(?:\s|$)',
        r'(?i)(?:제목|title)\s*[:：]\s*["“]?([^"”]+?)["”]?(?:\s|$)',
    ]
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`.,")
        if candidate:
            return candidate[:100]
    return None


def _needs_notion_update_clarification(text: str) -> bool:
    lower = (text or "").lower()
    if not _is_update_intent(text):
        return False
    if _extract_notion_update_new_title(text):
        return False
    detail_tokens = (
        "본문",
        "내용",
        "추가",
        "append",
        "요약",
        "문단",
        "블록",
        "설명",
        "description",
        "property",
        "속성",
        "status",
        "태그",
        "priority",
    )
    return not any(token in lower or token in text for token in detail_tokens)


def _extract_notion_update_body_text(text: str) -> str | None:
    raw = " ".join((text or "").strip().split())
    patterns = [
        r"(?i)(?:본문\s*업데이트|본문\s*수정|content\s*update|내용\s*업데이트)\s*[:：]\s*(.+)$",
        r"(?i)(?:본문|내용)\s*[:：]\s*(.+)$",
        r'(?i)(?:본문|내용)에\s*["“]?(.+?)["”]?\s*(?:추가|append|넣어|작성)',
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`")
        if candidate:
            return candidate[:1800]
    return None


def _extract_linear_team_reference(text: str) -> str | None:
    keyed = re.search(r"(?i)(?:팀|team)\s*[:：]?\s*([^\s,]+)", text.strip())
    if keyed:
        candidate = keyed.group(1).strip(" \"'`")
        if candidate:
            return candidate
    return None


def _extract_linear_issue_title_for_create(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    labeled = re.search(
        r"(?i)(?:제목은|title is|제목|title)\s*[:：]?\s*['\"“”]?"
        r"(.+?)"
        r"(?=(?:\s+(?:설명|내용|description|본문|priority|우선순위|라벨|label|담당자|assignee)\s*[:：])|$)",
        normalized,
    )
    if labeled:
        candidate = labeled.group(1).strip(" \"'`.,")
        if candidate:
            return candidate[:120]
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    # e.g. "linear에서 비밀번호 찾기 오류 이슈 생성해줘"
    service_first = re.search(
        r"(?i)(?:linear|리니어)(?:에서|에|의)?\s*(.+?)\s*(?:이슈)\s*(?:생성|만들|작성|create)",
        normalized,
    )
    if service_first:
        candidate = service_first.group(1).strip(" \"'`.,")
        candidate = re.sub(r"(?i)^(?:팀|team)\s*[:：]?\s*[^\s,]+\s*", "", candidate).strip()
        if candidate:
            return candidate[:120]
    pattern = re.search(r"(?i)(.+?)\s*(?:linear|리니어).*(?:이슈).*(?:생성|만들|작성|create)", text.strip())
    if pattern:
        candidate = pattern.group(1).strip(" \"'`")
        candidate = re.sub(r"^(?:linear|리니어)(?:의|에서)?\s*", "", candidate, flags=re.IGNORECASE).strip()
        if candidate:
            return candidate[:120]
    return None


def _extract_linear_update_new_title(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    patterns = [
        r'(?i)(?:이슈\s*)?(?:제목|title)(?:을|를)?\s*["“]?([^"”]+?)["”]?\s*(?:로|으로)?\s*(?:업데이트|수정|변경|바꿔|rename)',
        r"(?i)(?:새\s*제목|new\s*title)\s*[:：]?\s*['\"“”]?(.+?)['\"“”]?(?:\s|$)",
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


def _extract_linear_update_description_text(text: str) -> str | None:
    raw = " ".join((text or "").strip().split())
    patterns = [
        r"(?i)(?:설명|description|내용|본문)\s*(?:업데이트|수정|변경)?\s*[:：]\s*(.+)$",
        r'(?i)(?:설명|description|내용|본문)에\s*["“]?(.+?)["”]?\s*(?:추가|append|넣어|작성|반영)',
        r"(?i)(?:설명|description|내용|본문)(?:을|를)?\s*(.+?)\s*(?:으로|로)\s*(?:업데이트|수정|변경|바꿔|바꿔줘|수정해줘|업데이트해줘|수정하세요|변경해줘)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`")
        if candidate:
            return candidate[:5000]
    return None


def _extract_linear_update_state_id(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    matched = re.search(r"(?i)(?:state_id|state id|상태id|상태_id)\s*[:：]\s*([^\s,]+)", normalized)
    if not matched:
        return None
    candidate = str(matched.group(1) or "").strip(" \"'`.,")
    return candidate or None


def _extract_linear_update_priority(text: str) -> int | None:
    normalized = " ".join((text or "").strip().split())
    matched = re.search(r"(?i)(?:priority|우선순위)\s*[:：]\s*([0-4])", normalized)
    if not matched:
        return None
    try:
        return int(matched.group(1))
    except Exception:
        return None


def _is_linear_description_append_intent(text: str) -> bool:
    raw = " ".join((text or "").strip().split())
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


def _needs_linear_update_clarification(text: str) -> bool:
    if not _is_update_intent(text):
        return False
    if _extract_linear_update_new_title(text):
        return False
    if _extract_linear_update_description_text(text):
        return False
    if _extract_linear_update_state_id(text):
        return False
    if _extract_linear_update_priority(text) is not None:
        return False
    return True


def _extract_count_limit(text: str, *, default: int = 5, minimum: int = 1, maximum: int = 20) -> int:
    m = re.search(r"(\d{1,3})\s*(?:개|건|items?)", text or "", flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bfirst\s*[:=]?\s*(\d{1,3})\b", text or "", flags=re.IGNORECASE)
    if not m:
        return default
    value = int(m.group(1))
    return max(minimum, min(maximum, value))


def _safe_int(value: object, *, default: int, minimum: int = 1, maximum: int = 20) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _is_linear_recent_list_intent(text: str) -> bool:
    lower = (text or "").lower()
    has_issue_token = ("이슈" in text) or ("issue" in lower)
    has_list_token = any(token in lower for token in ("최근", "latest", "list", "목록", "검색", "조회"))
    return has_issue_token and has_list_token


def _is_notion_recent_list_intent(text: str) -> bool:
    lower = (text or "").lower()
    has_page_token = ("페이지" in text) or ("page" in lower)
    has_list_token = any(token in lower for token in ("최근", "latest", "list", "목록", "검색", "조회"))
    return has_page_token and has_list_token


def _normalize_router_arguments(*, decision: RouterDecision, user_text: str) -> RouterDecision:
    args = dict(getattr(decision, "arguments", {}) or {})
    skill_name = str(getattr(decision, "skill_name", None) or "").strip()
    text = user_text or ""

    if skill_name == "linear.issue_search":
        if not str(args.get("linear_query") or "").strip():
            ref = _extract_linear_issue_reference(text)
            if ref:
                args["linear_query"] = ref
        args["linear_first"] = _safe_int(
            args.get("linear_first"),
            default=_extract_count_limit(text, default=5),
            minimum=1,
            maximum=20,
        )
    elif skill_name == "linear.issue_create":
        if not str(args.get("linear_team_ref") or "").strip():
            args["linear_team_ref"] = _extract_linear_team_reference(text)
        if not str(args.get("linear_issue_title") or "").strip():
            args["linear_issue_title"] = _extract_linear_issue_title_for_create(text)
    elif skill_name == "notion.page_create":
        if not str(args.get("notion_page_title") or "").strip():
            args["notion_page_title"] = _extract_notion_page_title_for_create(text)
    elif skill_name in {"linear.issue_update", "linear.issue_delete"}:
        if not str(args.get("linear_issue_ref") or "").strip():
            args["linear_issue_ref"] = _extract_linear_issue_reference(text)
    elif skill_name in {"notion.page_update", "notion.page_delete"}:
        if not str(args.get("notion_page_title") or "").strip():
            args["notion_page_title"] = _extract_notion_page_title(text)
    elif skill_name == "notion.page_search":
        args["notion_first"] = _safe_int(
            args.get("notion_first"),
            default=_extract_count_limit(text, default=5),
            minimum=1,
            maximum=20,
        )

    return RouterDecision(
        mode=str(getattr(decision, "mode", MODE_LLM_ONLY)),
        reason=str(getattr(decision, "reason", "normalized")),
        skill_name=skill_name or None,
        target_services=list(getattr(decision, "target_services", []) or []),
        selected_tools=list(getattr(decision, "selected_tools", []) or []),
        arguments=args,
    )


def _is_supported_mode_skill_combo(mode: str, skill_name: str | None) -> bool:
    skill = str(skill_name or "").strip()
    if mode == MODE_LLM_ONLY:
        return not skill
    if mode == MODE_LLM_THEN_SKILL:
        return skill in {
            "notion.page_create",
            "notion.page_update",
            "notion.page_delete",
            "linear.issue_create",
            "linear.issue_update",
            "linear.issue_delete",
        }
    if mode == MODE_SKILL_THEN_LLM:
        return skill in {"linear.issue_search", "notion.page_search"}
    return False


def _apply_decision_safety_overrides(
    *,
    decision: RouterDecision,
    user_text: str,
    connected_services: list[str],
) -> tuple[RouterDecision, str | None]:
    text = user_text or ""
    connected = {service.strip().lower() for service in connected_services if service and service.strip()}
    skill_name = str(decision.skill_name or "").strip()

    if not _is_supported_mode_skill_combo(decision.mode, skill_name or None):
        return _normalize_router_arguments(
            decision=route_request_v2(user_text=text, connected_services=connected_services),
            user_text=text,
        ), "force_rule_unsupported_mode_skill_combo"

    # Force deterministic routing for recent-list intents.
    if "linear" in connected and _is_linear_recent_list_intent(text):
        return _normalize_router_arguments(
            decision=route_request_v2(user_text=text, connected_services=connected_services),
            user_text=text,
        ), "force_rule_linear_recent_list"
    if "notion" in connected and _is_notion_recent_list_intent(text):
        return _normalize_router_arguments(
            decision=route_request_v2(user_text=text, connected_services=connected_services),
            user_text=text,
        ), "force_rule_notion_recent_list"

    # Explicit mutation intent on connected service should always be rule-routed.
    notion_mutation_intent = "notion" in connected and _mentions_service(text, "notion") and (
        _is_create_intent(text) or _is_update_intent(text) or _is_delete_intent(text)
    )
    linear_mutation_intent = "linear" in connected and _mentions_service(text, "linear") and (
        (_is_create_intent(text) and (("이슈" in text) or ("issue" in text.lower())))
        or _is_update_intent(text)
        or _is_linear_description_append_intent(text)
        or _is_delete_intent(text)
    )
    if notion_mutation_intent or linear_mutation_intent:
        forced = _normalize_router_arguments(
            decision=route_request_v2(user_text=text, connected_services=connected_services),
            user_text=text,
        )
        if forced.mode != decision.mode or forced.skill_name != decision.skill_name:
            return forced, "force_rule_explicit_mutation_intent"

    # If LLM picks search skill with mutation mode, coerce to read mode.
    if decision.mode == MODE_LLM_THEN_SKILL and skill_name in {"linear.issue_search", "notion.page_search"}:
        return RouterDecision(
            mode=MODE_SKILL_THEN_LLM,
            reason=f"{decision.reason}_coerced_read_mode",
            skill_name=decision.skill_name,
            target_services=decision.target_services,
            selected_tools=decision.selected_tools,
            arguments=decision.arguments,
        ), "coerce_mode_to_skill_then_llm"

    # If LLM picks mutation skill with read mode, coerce to mutation mode.
    if decision.mode == MODE_SKILL_THEN_LLM and skill_name in {
        "notion.page_create",
        "notion.page_update",
        "notion.page_delete",
        "linear.issue_create",
        "linear.issue_update",
        "linear.issue_delete",
    }:
        return RouterDecision(
            mode=MODE_LLM_THEN_SKILL,
            reason=f"{decision.reason}_coerced_mutation_mode",
            skill_name=decision.skill_name,
            target_services=decision.target_services,
            selected_tools=decision.selected_tools,
            arguments=decision.arguments,
        ), "coerce_mode_to_llm_then_skill"

    return decision, None


def route_request_v2(user_text: str, connected_services: list[str]) -> RouterDecision:
    text = (user_text or "").strip()
    connected = {service.strip().lower() for service in connected_services if service.strip()}

    has_notion = "notion" in connected and _mentions_service(text, "notion")
    has_linear = "linear" in connected and _mentions_service(text, "linear")

    # Mutation intents must win over analysis keywords ("방법", "정리", ...).
    # Otherwise create/update/delete requests are misrouted into search flows.

    if has_linear and (_is_update_intent(text) or _is_linear_description_append_intent(text)):
        issue_ref = _extract_linear_issue_reference(text)
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_linear_issue_update",
            skill_name="linear.issue_update",
            target_services=["linear"],
            arguments={"linear_issue_ref": issue_ref},
        )

    if has_linear and _is_create_intent(text) and ("이슈" in text or "issue" in text.lower()):
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_linear_issue_create",
            skill_name="linear.issue_create",
            target_services=["linear"],
            arguments={
                "linear_team_ref": _extract_linear_team_reference(text),
                "linear_issue_title": _extract_linear_issue_title_for_create(text),
            },
        )

    if has_linear and _is_delete_intent(text) and ("이슈" in text or "issue" in text.lower()):
        issue_ref = _extract_linear_issue_reference(text)
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_linear_issue_delete",
            skill_name="linear.issue_delete",
            target_services=["linear"],
            arguments={"linear_issue_ref": issue_ref},
        )

    if has_notion and _is_update_intent(text):
        page_title = _extract_notion_page_title(text)
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_notion_page_update",
            skill_name="notion.page_update",
            target_services=["notion"],
            arguments={"notion_page_title": page_title},
        )

    if has_notion and _is_delete_intent(text):
        page_title = _extract_notion_page_title(text)
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_notion_page_delete",
            skill_name="notion.page_delete",
            target_services=["notion"],
            arguments={"notion_page_title": page_title},
        )

    if has_notion and _is_write_intent(text):
        return _decision_for_skill(
            mode=MODE_LLM_THEN_SKILL,
            reason="llm_result_to_notion_page",
            skill_name="notion.page_create",
            target_services=["notion"],
            arguments={"notion_page_title": _extract_notion_page_title_for_create(text)},
        )

    # Read/search/analysis intents
    if has_notion and _is_notion_recent_list_intent(text):
        return _decision_for_skill(
            mode=MODE_SKILL_THEN_LLM,
            reason="notion_recent_pages_list",
            skill_name="notion.page_search",
            target_services=["notion"],
            arguments={"notion_page_title": "", "notion_first": _extract_count_limit(text, default=5)},
        )

    if has_linear and _is_linear_recent_list_intent(text):
        return _decision_for_skill(
            mode=MODE_SKILL_THEN_LLM,
            reason="linear_recent_issues_then_llm",
            skill_name="linear.issue_search",
            target_services=["linear"],
            arguments={"linear_query": "", "linear_first": _extract_count_limit(text, default=10)},
        )

    if has_linear and _is_analysis_intent(text):
        issue_ref = _extract_linear_issue_reference(text)
        if issue_ref:
            return _decision_for_skill(
                mode=MODE_SKILL_THEN_LLM,
                reason="service_read_then_llm",
                skill_name="linear.issue_search",
                target_services=["linear"],
                arguments={"linear_query": issue_ref},
            )

    if has_notion and _is_analysis_intent(text):
        page_title = _extract_notion_page_title(text)
        if page_title:
            return _decision_for_skill(
                mode=MODE_SKILL_THEN_LLM,
                reason="notion_read_then_llm",
                skill_name="notion.page_search",
                target_services=["notion"],
                arguments={"notion_page_title": page_title},
            )

    return RouterDecision(mode=MODE_LLM_ONLY, reason="default_llm_only", target_services=[], selected_tools=[])


async def _request_llm_text(*, prompt: str) -> tuple[str, str, str]:
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

    timeout_sec = max(5, int(getattr(settings, "llm_request_timeout_sec", 20)))

    for provider, model in attempts:
        try:
            if provider == "openai":
                if not settings.openai_api_key:
                    continue
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.post(
                        OPENAI_CHAT_COMPLETIONS_URL,
                        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "temperature": 0.2,
                            "messages": [
                                {"role": "system", "content": "You are a concise assistant."},
                                {"role": "user", "content": prompt},
                            ],
                        },
                    )
                if response.status_code >= 400:
                    continue
                payload = response.json()
                content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                if content:
                    return content, provider, model

            if provider in {"google", "gemini"}:
                if not settings.google_api_key:
                    continue
                url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=settings.google_api_key)
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    response = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                    )
                if response.status_code >= 400:
                    continue
                payload = response.json()
                candidates = payload.get("candidates") or []
                parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
                content = " ".join(str(part.get("text") or "") for part in parts).strip()
                if content:
                    return content, "gemini", model
        except Exception:
            continue

    raise HTTPException(status_code=503, detail="llm_unavailable")


def _build_plan(user_text: str, decision: RouterDecision) -> AgentPlan:
    requirements = [AgentRequirement(summary=decision.reason)]
    workflow_steps = {
        MODE_LLM_ONLY: ["1. LLM 응답 생성"],
        MODE_LLM_THEN_SKILL: ["1. LLM 결과 생성", "2. Notion 페이지 생성"],
        MODE_SKILL_THEN_LLM: ["1. Linear 이슈 조회", "2. LLM으로 해결 방법 정리"],
    }.get(decision.mode, ["1. 처리"])
    notes = ["planner=router_v2", f"router_mode={decision.mode}"]
    return AgentPlan(
        user_text=user_text,
        requirements=requirements,
        target_services=decision.target_services,
        selected_tools=decision.selected_tools,
        workflow_steps=workflow_steps,
        tasks=[],
        notes=notes,
    )


def _notion_parent_payload() -> dict:
    settings = get_settings()
    parent_page_id = (settings.notion_default_parent_page_id or "").strip()
    return {"page_id": parent_page_id} if parent_page_id else {"workspace": True}


def _build_grounded_llm_prompt(*, user_text: str, mode: str) -> str:
    today_utc = datetime.now(timezone.utc).date().isoformat()
    realtime = _looks_realtime_request(user_text)
    guard = (
        "다음 규칙을 반드시 지켜 답변해줘.\n"
        "1) 확인되지 않은 사실/수치/날짜/고유명사를 임의로 만들지 마.\n"
        "2) 답변은 한국어로 간결하게 작성해.\n"
        f"3) 오늘 날짜 기준(UTC)은 {today_utc}.\n"
    )
    if realtime:
        guard += "4) 실시간 데이터가 필요한 요청인데 근거가 없으면 '실시간 조회 불가'라고 명시해.\n"
    else:
        guard += "4) 실시간 조회 관련 문구는 요청이 실시간 데이터일 때만 사용해.\n"
    if mode == MODE_LLM_THEN_SKILL:
        extra = (
            "5) 외부 서비스 조작 방법(클릭/메뉴얼) 설명을 쓰지 말고, "
            "실제로 저장/업데이트할 결과 본문만 작성해.\n"
        )
        return f"{guard}{extra}\n[사용자 요청]\n{user_text}"
    return f"{guard}\n[사용자 요청]\n{user_text}"


def _build_linear_append_generation_prompt(*, user_text: str) -> str:
    return (
        "다음 요청을 바탕으로 Linear 이슈 설명란에 바로 붙일 '최종 본문'만 작성해줘.\n"
        "규칙:\n"
        "- 단계/체크리스트/작업과정/머리말 금지\n"
        "- 4~8문장, 핵심만 간결하게\n"
        "- 확인되지 않은 사실은 단정하지 말 것\n"
        "- URL이 있으면 참고 링크로 1줄 포함 가능\n\n"
        f"[사용자 요청]\n{user_text}"
    )


def _looks_realtime_request(text: str) -> bool:
    lower = (text or "").lower()
    tokens = ("실시간", "현재", "오늘", "날씨", "시간", "환율", "주가", "경기", "schedule", "weather")
    return any(token in lower for token in tokens)


def _looks_unavailable_answer(text: str) -> bool:
    lower = (text or "").lower()
    tokens = ("실시간 조회 불가", "실시간 정보를 제공할 수 없", "확인할 수 없", "조회할 수 없", "cannot provide")
    return any(token in lower for token in tokens)


def _extract_first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s\)\]\}\>,]+", text or "", flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).rstrip(").,!?\"'`")


def _is_translation_intent(text: str) -> bool:
    lower = (text or "").lower()
    tokens = ("번역", "translate", "translated", "한국어로", "영어로", "일본어로")
    return any(token in lower for token in tokens)


def _build_url_translation_prompt(*, user_text: str, source_url: str, source_title: str, source_text: str) -> str:
    return (
        "아래 URL 본문을 요청 언어로 번역해줘.\n"
        "규칙:\n"
        "- 요약/의역/해설 금지, 원문 문단 구조를 최대한 유지\n"
        "- 원문에 없는 내용 추가 금지\n"
        "- 번역문만 출력\n\n"
        f"[사용자 요청]\n{user_text}\n\n"
        f"[원문 URL]\n{source_url}\n\n"
        f"[원문 제목]\n{source_title or '-'}\n\n"
        f"[원문 본문]\n{source_text}"
    )


def _linear_issues_to_context(tool_result: dict) -> str:
    nodes = _linear_issue_nodes(tool_result)
    if not nodes:
        return "조회된 이슈가 없습니다."
    lines: list[str] = []
    for idx, node in enumerate(nodes[:5], start=1):
        identifier = str(node.get("identifier") or "-")
        title = str(node.get("title") or "(제목 없음)")
        description = str(node.get("description") or "")
        lines.append(f"{idx}. [{identifier}] {title}")
        if description:
            lines.append(f"설명: {description[:1200]}")
    return "\n".join(lines)


def _linear_issue_count(tool_result: dict) -> int:
    return len(_linear_issue_nodes(tool_result))


def _linear_issue_nodes(tool_result: dict) -> list[dict]:
    data = tool_result.get("data") or {}
    nodes = (((data.get("issues") or {}).get("nodes")) or [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def _linear_issue_links_block(tool_result: dict, *, limit: int = 10) -> str:
    nodes = _linear_issue_nodes(tool_result)
    lines: list[str] = []
    for node in nodes[: max(1, limit)]:
        issue_url = str(node.get("url") or "").strip()
        if not issue_url:
            continue
        identifier = str(node.get("identifier") or "").strip() or "-"
        title = str(node.get("title") or "").strip()
        if title:
            lines.append(f"- [{identifier}] {title}: {issue_url}")
        else:
            lines.append(f"- [{identifier}] {issue_url}")
    if not lines:
        return ""
    return "관련 이슈 링크:\n" + "\n".join(lines)


def _linear_issue_list_text(tool_result: dict, *, limit: int = 10) -> str:
    nodes = _linear_issue_nodes(tool_result)
    if not nodes:
        return "조회된 이슈가 없습니다."
    lines = [f"Linear 최근 이슈 {min(limit, len(nodes))}건"]
    for idx, node in enumerate(nodes[: max(1, limit)], start=1):
        identifier = str(node.get("identifier") or "-").strip()
        title = str(node.get("title") or "(제목 없음)").strip()
        state = str(((node.get("state") or {}).get("name") or "")).strip()
        issue_url = str(node.get("url") or "").strip()
        base = f"{idx}. [{identifier}] {title}"
        if state:
            base += f" ({state})"
        if issue_url:
            base += f"\n   {issue_url}"
        lines.append(base)
    return "\n".join(lines)


def _notion_page_list_text(tool_result: dict, *, limit: int = 10) -> str:
    pages = ((tool_result.get("data") or {}).get("results") or [])
    if not isinstance(pages, list) or not pages:
        return "조회된 페이지가 없습니다."
    lines = [f"Notion 최근 페이지 {min(limit, len(pages))}건"]
    for idx, page in enumerate(pages[: max(1, limit)], start=1):
        if not isinstance(page, dict):
            continue
        title = _extract_notion_page_title_from_search_result(page) or "(제목 없음)"
        page_url = str(page.get("url") or "").strip()
        line = f"{idx}. {title}"
        if page_url:
            line += f"\n   {page_url}"
        lines.append(line)
    return "\n".join(lines)


async def _linear_search_with_issue_ref_fallback(*, user_id: str, issue_ref: str) -> dict:
    query = (issue_ref or "").strip()
    searched = await execute_tool(
        user_id=user_id,
        tool_name="linear_search_issues",
        payload={"query": query, "first": 10},
    )
    if _linear_issue_count(searched) > 0:
        return searched

    listed = await execute_tool(
        user_id=user_id,
        tool_name="linear_list_issues",
        payload={"first": 20},
    )
    ref_norm = query.lower()
    listed_nodes = _linear_issue_nodes(listed)
    exact = [node for node in listed_nodes if str(node.get("identifier") or "").strip().lower() == ref_norm]
    if not exact:
        return searched

    # Title 기반 재검색으로 설명/본문 필드를 최대한 확보한다.
    issue_title = str(exact[0].get("title") or "").strip()
    if issue_title:
        retry = await execute_tool(
            user_id=user_id,
            tool_name="linear_search_issues",
            payload={"query": issue_title, "first": 10},
        )
        if _linear_issue_count(retry) > 0:
            return retry

    return {"data": {"issues": {"nodes": exact}}}


def _notion_blocks_to_context(tool_result: dict) -> str:
    data = tool_result.get("data") or {}
    blocks = data.get("results") or []
    if not isinstance(blocks, list):
        return "페이지 본문을 찾지 못했습니다."
    lines: list[str] = []
    for block in blocks[:80]:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if not block_type:
            continue
        payload = block.get(block_type) or {}
        if not isinstance(payload, dict):
            continue
        rich_text = payload.get("rich_text") or []
        if not isinstance(rich_text, list):
            continue
        text = "".join(str(part.get("plain_text") or "") for part in rich_text if isinstance(part, dict)).strip()
        if text:
            lines.append(text)
    if not lines:
        return "페이지 본문을 찾지 못했습니다."
    return "\n".join(lines)


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip().lower()


def _extract_notion_page_title_from_search_result(page: dict) -> str:
    props = page.get("properties") or {}
    for value in props.values():
        if isinstance(value, dict) and value.get("type") == "title":
            chunks = value.get("title", [])
            return "".join(chunk.get("plain_text", "") for chunk in chunks).strip()
    return ""


def _extract_notion_title_property_key(page: dict) -> str | None:
    props = page.get("properties") or {}
    if not isinstance(props, dict):
        return None
    for key, value in props.items():
        if isinstance(value, dict) and value.get("type") == "title":
            return str(key).strip() or None
    return None


async def _resolve_notion_page_for_update(*, user_id: str, title: str) -> tuple[str, str, str | None]:
    result = await execute_tool(
        user_id=user_id,
        tool_name="notion_search",
        payload={"query": title, "page_size": 5},
    )
    pages = ((result.get("data") or {}).get("results") or [])
    if not pages:
        raise NeedsInputSignal(
            missing_fields=["target.page_id"],
            questions=[f"'{title}' 페이지를 찾지 못했습니다. 정확한 페이지 제목을 알려주세요."],
        )

    candidates: list[dict] = []
    target_norm = _normalize_title(title)
    exact_matches: list[dict] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_title = _extract_notion_page_title_from_search_result(page)
        page_id = str(page.get("id") or "").strip()
        page_url = str(page.get("url") or "").strip()
        if not page_id:
            continue
        candidate = {
            "label": page_title or "(제목 없음)",
            "page_id": page_id,
            "url": page_url,
            "title_property_key": _extract_notion_title_property_key(page),
        }
        candidates.append(candidate)
        if target_norm and _normalize_title(page_title) == target_norm:
            exact_matches.append(candidate)

    selected: dict | None = None
    if len(exact_matches) == 1:
        selected = exact_matches[0]
    elif len(exact_matches) > 1:
        raise NeedsInputSignal(
            missing_fields=["target.page_id"],
            questions=[f"'{title}'와 일치하는 페이지가 여러 개 있습니다. 대상을 선택해 주세요."],
            choices={"candidates": exact_matches[:5]},
        )
    elif len(candidates) == 1:
        selected = candidates[0]
    elif len(candidates) > 1:
        raise NeedsInputSignal(
            missing_fields=["target.page_id"],
            questions=[f"'{title}' 검색 결과가 여러 개입니다. 대상 페이지를 선택해 주세요."],
            choices={"candidates": candidates[:5]},
        )

    if not selected:
        raise NeedsInputSignal(
            missing_fields=["target.page_id"],
            questions=["업데이트할 Notion 페이지를 선택해 주세요."],
        )
    page_id = str(selected.get("page_id") or "").strip()
    page_url = str(selected.get("url") or "").strip()
    if not page_id:
        raise NeedsInputSignal(
            missing_fields=["target.page_id"],
            questions=["업데이트할 Notion 페이지 ID를 확인해 주세요."],
        )
    title_property_key = str(selected.get("title_property_key") or "").strip() or None
    return page_id, page_url, title_property_key


async def _resolve_linear_issue_id_for_update(*, user_id: str, issue_ref: str) -> tuple[str, str, str]:
    result = await _linear_search_with_issue_ref_fallback(user_id=user_id, issue_ref=issue_ref)
    nodes = _linear_issue_nodes(result)
    if not nodes:
        raise NeedsInputSignal(
            missing_fields=["target.issue_ref"],
            questions=[f"'{issue_ref}' 이슈를 찾지 못했습니다. 이슈 키(예: OPT-35)를 확인해 주세요."],
        )

    issue_ref_lower = issue_ref.strip().lower()
    exact: list[dict] = []
    candidates: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        identifier = str(node.get("identifier") or "").strip().lower()
        issue_id = str(node.get("id") or "").strip()
        title = str(node.get("title") or "").strip()
        description = str(node.get("description") or "")
        if not issue_id:
            continue
        issue_url = str(node.get("url") or "").strip()
        candidate = {
            "label": f"{identifier.upper() if identifier else issue_id} {title}".strip(),
            "issue_id": issue_id,
            "issue_url": issue_url,
            "description": description,
        }
        candidates.append(candidate)
        if issue_ref_lower and issue_ref_lower == identifier:
            exact.append(candidate)

    if len(exact) == 1:
        return (
            str(exact[0].get("issue_id") or ""),
            str(exact[0].get("issue_url") or ""),
            str(exact[0].get("description") or ""),
        )
    if len(exact) > 1 or len(candidates) > 1:
        raise NeedsInputSignal(
            missing_fields=["target.issue_id"],
            questions=["업데이트할 Linear 이슈를 선택해 주세요."],
            choices={"candidates": (exact or candidates)[:5]},
        )
    if len(candidates) == 1:
        return (
            str(candidates[0].get("issue_id") or ""),
            str(candidates[0].get("issue_url") or ""),
            str(candidates[0].get("description") or ""),
        )
    raise NeedsInputSignal(
        missing_fields=["target.issue_id"],
        questions=["업데이트할 Linear 이슈를 확인해 주세요."],
    )


async def _resolve_linear_team_id_for_create(*, user_id: str, team_ref: str | None) -> str:
    result = await execute_tool(
        user_id=user_id,
        tool_name="linear_list_teams",
        payload={"first": 20},
    )
    nodes = (((result.get("data") or {}).get("teams") or {}).get("nodes") or [])
    if not nodes:
        raise NeedsInputSignal(
            missing_fields=["team_id"],
            questions=["Linear 팀을 찾지 못했습니다. 팀 키(예: OPS)를 알려주세요."],
        )

    normalized_ref = (team_ref or "").strip().lower()
    candidates: list[dict] = []
    exact: list[dict] = []
    if normalized_ref:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            key = str(node.get("key") or "").strip().lower()
            name = str(node.get("name") or "").strip().lower()
            team_id = str(node.get("id") or "").strip()
            if not team_id:
                continue
            label = f"{(key or '').upper()} {name}".strip()
            candidates.append({"label": label, "team_id": team_id})
            if normalized_ref in {key, name}:
                exact.append({"label": label, "team_id": team_id})
        if len(exact) == 1:
            return str(exact[0].get("team_id") or "")
        if len(exact) > 1 or len(candidates) > 1:
            raise NeedsInputSignal(
                missing_fields=["team_id"],
                questions=["이슈를 생성할 Linear 팀을 선택해 주세요."],
                choices={"candidates": (exact or candidates)[:5]},
            )
        if len(candidates) == 1:
            return str(candidates[0].get("team_id") or "")

    all_candidates: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        team_id = str(node.get("id") or "").strip()
        if not team_id:
            continue
        key = str(node.get("key") or "").strip()
        name = str(node.get("name") or "").strip()
        all_candidates.append({"label": f"{key} {name}".strip(), "team_id": team_id})
    if len(all_candidates) == 1:
        return str(all_candidates[0].get("team_id") or "")
    raise NeedsInputSignal(
        missing_fields=["team_id"],
        questions=["이슈를 생성할 Linear 팀을 선택해 주세요."],
        choices={"candidates": all_candidates[:5]},
    )


def _build_needs_input_message(*, questions: list[str], choices: dict | None) -> str:
    lines: list[str] = ["입력값이 더 필요합니다."]
    for question in questions[:3]:
        lines.append(f"- {question}")
    candidates = (choices or {}).get("candidates") if isinstance(choices, dict) else None
    if isinstance(candidates, list) and candidates:
        lines.append("선택 가능한 항목:")
        for idx, item in enumerate(candidates[:5], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip() or str(item)
            lines.append(f"{idx}. {label}")
    return "\n".join(lines)


async def try_run_v2_orchestration(
    *,
    user_text: str,
    connected_services: list[str],
    user_id: str,
) -> AgentRunResult | None:
    contract_total, contract_failures = validate_all_contracts()
    if contract_total <= 0 or contract_failures:
        error_detail = "skill_contracts_invalid"
        if contract_total <= 0:
            error_detail = "skill_contracts_missing"
        execution = AgentExecutionResult(
            success=False,
            user_message="스킬 계약 검증에 실패해 V2 실행을 중단했습니다. 관리자에게 문의해주세요.",
            summary="V2 스킬 계약 검증 실패",
            artifacts={"error_code": error_detail},
            steps=[AgentExecutionStep(name="skill_contract_validation", status="error", detail=error_detail)],
        )
        fallback_plan = AgentPlan(
            user_text=user_text,
            requirements=[AgentRequirement(summary="skill_contract_validation")],
            target_services=[],
            selected_tools=[],
            workflow_steps=["1. contract validation"],
            tasks=[],
            notes=["planner=router_v2", "router_mode=LLM_ONLY", "router_source=contracts_invalid"],
        )
        if contract_failures:
            fallback_plan.notes.append(f"contract_failures={len(contract_failures)}")
        return AgentRunResult(
            ok=False,
            stage="planning",
            plan=fallback_plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    settings = get_settings()
    decision: RouterDecision
    router_source = "rule"
    router_llm_provider: str | None = None
    router_llm_model: str | None = None
    router_llm_fallback_reason: str | None = None

    if bool(getattr(settings, "skill_router_v2_llm_enabled", False)):
        llm_decision, router_llm_provider, router_llm_model = await _request_router_decision_with_llm(
            user_text=user_text,
            connected_services=connected_services,
        )
        if llm_decision is not None:
            decision = _normalize_router_arguments(decision=llm_decision, user_text=user_text)
            router_source = "llm"
        else:
            decision = _normalize_router_arguments(decision=route_request_v2(user_text, connected_services), user_text=user_text)
            router_source = "llm_fallback_rule"
            router_llm_fallback_reason = "invalid_payload_or_parse_failed"
    else:
        decision = _normalize_router_arguments(decision=route_request_v2(user_text, connected_services), user_text=user_text)

    decision, override_reason = _apply_decision_safety_overrides(
        decision=decision,
        user_text=user_text,
        connected_services=connected_services,
    )
    plan = _build_plan(user_text, decision)
    plan.notes.append(f"router_source={router_source}")
    if router_llm_fallback_reason:
        plan.notes.append(f"router_llm_fallback_reason={router_llm_fallback_reason}")
    if override_reason:
        plan.notes.append(f"router_decision_override={override_reason}")
    if router_llm_provider and router_llm_model:
        plan.notes.append(f"router_llm_provider={router_llm_provider}")
        plan.notes.append(f"router_llm_model={router_llm_model}")

    try:
        if decision.mode == MODE_LLM_ONLY:
            answer, provider, model = await _request_llm_text(
                prompt=_build_grounded_llm_prompt(user_text=user_text, mode=MODE_LLM_ONLY)
            )
            plan.notes.append(f"llm_provider={provider}")
            plan.notes.append(f"llm_model={model}")
            execution = AgentExecutionResult(
                success=True,
                user_message=answer,
                summary="LLM 응답 생성 완료",
                artifacts={"router_mode": decision.mode, "llm_provider": provider, "llm_model": model},
                steps=[AgentExecutionStep(name="llm_only", status="success", detail=f"provider={provider}:{model}")],
            )
            return AgentRunResult(
                ok=True,
                stage="execution",
                plan=plan,
                result_summary=execution.summary,
                execution=execution,
                plan_source="router_v2",
            )

        if decision.mode == MODE_LLM_THEN_SKILL:
            skill_name = str(decision.skill_name or "").strip() or infer_skill_name_from_runtime_tools(
                decision.selected_tools
            )
            llm_text = ""
            provider = ""
            model = ""
            source_url = ""
            notion_update_new_title = ""
            notion_update_body_text = ""
            linear_update_new_title = ""
            linear_update_description_text = ""
            linear_update_state_id = ""
            linear_update_priority: int | None = None
            if skill_name == "notion.page_update":
                notion_update_new_title = _extract_notion_update_new_title(user_text) or ""
                notion_update_body_text = _extract_notion_update_body_text(user_text) or ""
                if not notion_update_new_title and not notion_update_body_text and _needs_notion_update_clarification(user_text):
                    raise NeedsInputSignal(
                        missing_fields=["patch"],
                        questions=[
                            "무엇을 업데이트할지 알려주세요. 예: 제목을 \"스프린트 보고서\"로 변경 / 본문에 배포 회고 추가"
                        ],
                    )
            if skill_name == "linear.issue_update":
                linear_update_new_title = _extract_linear_update_new_title(user_text) or ""
                linear_update_description_text = _extract_linear_update_description_text(user_text) or ""
                linear_update_state_id = _extract_linear_update_state_id(user_text) or ""
                linear_update_priority = _extract_linear_update_priority(user_text)
            linear_update_append_intent = skill_name == "linear.issue_update" and _is_linear_description_append_intent(user_text)
            if skill_name == "notion.page_create" and _is_translation_intent(user_text):
                maybe_url = _extract_first_url(user_text)
                if maybe_url:
                    fetched = await execute_tool(
                        user_id=user_id,
                        tool_name="http_fetch_url_text",
                        payload={"url": maybe_url, "max_chars": 12000},
                    )
                    fetched_data = fetched.get("data") or {}
                    source_url = str(fetched_data.get("final_url") or fetched_data.get("url") or maybe_url).strip()
                    source_title = str(fetched_data.get("title") or "").strip()
                    source_text = str(fetched_data.get("text") or "").strip()
                    if not source_text:
                        raise HTTPException(status_code=400, detail="validation_error")
                    llm_text, provider, model = await _request_llm_text(
                        prompt=_build_url_translation_prompt(
                            user_text=user_text,
                            source_url=source_url,
                            source_title=source_title,
                            source_text=source_text,
                        )
                    )

            linear_update_has_explicit_patch = bool(
                linear_update_new_title
                or linear_update_description_text
                or linear_update_state_id
                or linear_update_priority is not None
            )
            linear_update_allow_generated_description = (
                skill_name == "linear.issue_update"
                and not linear_update_has_explicit_patch
                and linear_update_append_intent
            )

            if skill_name == "linear.issue_update" and not (
                linear_update_has_explicit_patch or linear_update_allow_generated_description
            ):
                pass
            elif not llm_text and not (
                (skill_name == "notion.page_update" and (notion_update_new_title or notion_update_body_text))
                or (skill_name == "linear.issue_update" and linear_update_has_explicit_patch)
            ):
                prompt = _build_grounded_llm_prompt(user_text=user_text, mode=MODE_LLM_THEN_SKILL)
                if linear_update_allow_generated_description:
                    prompt = _build_linear_append_generation_prompt(user_text=user_text)
                llm_text, provider, model = await _request_llm_text(
                    prompt=prompt
                )
            if provider and model:
                plan.notes.append(f"llm_provider={provider}")
                plan.notes.append(f"llm_model={model}")

            if _looks_realtime_request(user_text) and _looks_unavailable_answer(llm_text):
                execution = AgentExecutionResult(
                    success=False,
                    user_message=llm_text,
                    summary="실시간 조회 불가로 외부 서비스 반영 생략",
                    artifacts={
                        "router_mode": decision.mode,
                        "error_code": "realtime_data_unavailable",
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(name="skip_skill_apply", status="error", detail="realtime_data_unavailable"),
                    ],
                )
                return AgentRunResult(
                    ok=False,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "notion.page_create":
                title = str(decision.arguments.get("notion_page_title") or "").strip()
                if not title:
                    title = _extract_notion_page_title_for_create(user_text) or ""
                if not title:
                    title = "new page"
                children = [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": llm_text[:1800],
                                    },
                                }
                            ]
                        },
                    }
                ]
                result = await execute_tool(
                    user_id=user_id,
                    tool_name="notion_create_page",
                    payload={
                        "parent": _notion_parent_payload(),
                        "properties": {
                            "title": {"title": [{"type": "text", "text": {"content": title[:100]}}]},
                        },
                        "children": children,
                    },
                )
                page_url = str((result.get("data") or {}).get("url") or "").strip()
                msg = llm_text
                if page_url:
                    msg += f"\n\nNotion 페이지: {page_url}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=msg,
                    summary="LLM 생성 후 Notion 반영 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "created_page_url": page_url,
                        "source_url": source_url,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(name="skill_notion_create_page", status="success", detail="notion_create_page"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "notion.page_update":
                page_title = str(decision.arguments.get("notion_page_title") or "").strip()
                if not page_title:
                    raise NeedsInputSignal(
                        missing_fields=["target.page_title"],
                        questions=["업데이트할 Notion 페이지 제목을 알려주세요. 예: 제목: 스프린트 회고"],
                    )
                page_id, page_url, title_property_key = await _resolve_notion_page_for_update(
                    user_id=user_id, title=page_title
                )
                if notion_update_new_title:
                    prop_key = title_property_key or "title"
                    await execute_tool(
                        user_id=user_id,
                        tool_name="notion_update_page",
                        payload={
                            "page_id": page_id,
                            "properties": {
                                prop_key: {
                                    "title": [
                                        {"type": "text", "text": {"content": notion_update_new_title[:100]}}
                                    ]
                                }
                            },
                        },
                    )
                    msg = f"\"{page_title}\" 페이지 제목이 \"{notion_update_new_title[:100]}\"로 업데이트되었습니다."
                    if page_url:
                        msg += f"\n\n업데이트 대상 페이지: {page_title}\n링크: {page_url}"
                    execution = AgentExecutionResult(
                        success=True,
                        user_message=msg,
                        summary="Notion 페이지 제목 업데이트 완료",
                        artifacts={
                            "router_mode": decision.mode,
                            "updated_page_id": page_id,
                            "updated_page_url": page_url,
                        },
                        steps=[
                            AgentExecutionStep(
                                name="skill_notion_update_page_title",
                                status="success",
                                detail=f"page_title={page_title};new_title={notion_update_new_title[:60]}",
                            ),
                        ],
                    )
                    return AgentRunResult(
                        ok=True,
                        stage="execution",
                        plan=plan,
                        result_summary=execution.summary,
                        execution=execution,
                        plan_source="router_v2",
                    )
                children = [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": (notion_update_body_text or llm_text)[:1800],
                                    },
                                }
                            ]
                        },
                    }
                ]
                await execute_tool(
                    user_id=user_id,
                    tool_name="notion_append_block_children",
                    payload={"block_id": page_id, "children": children},
                )
                if notion_update_body_text:
                    msg = f"\"{page_title}\" 페이지 본문에 \"{notion_update_body_text}\"를 추가했습니다."
                else:
                    msg = f"{llm_text}"
                msg += f"\n\n업데이트 대상 페이지: {page_title}"
                if page_url:
                    msg += f"\n링크: {page_url}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=msg,
                    summary="LLM 생성 후 Notion 페이지 업데이트 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "updated_page_id": page_id,
                        "updated_page_url": page_url,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(
                            name="skill_notion_append_block_children",
                            status="success",
                            detail=f"page_title={page_title}",
                        ),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "linear.issue_update":
                issue_ref = str(decision.arguments.get("linear_issue_ref") or "").strip()
                if not issue_ref:
                    raise NeedsInputSignal(
                        missing_fields=["target.issue_ref"],
                        questions=["업데이트할 Linear 이슈 키를 알려주세요. 예: OPT-35"],
                    )
                if (
                    not linear_update_new_title
                    and not linear_update_description_text
                    and not linear_update_state_id
                    and linear_update_priority is None
                    and _needs_linear_update_clarification(user_text)
                ):
                    raise NeedsInputSignal(
                        missing_fields=["patch"],
                        questions=[
                            "어떤 항목을 업데이트할까요? 예: 제목을 \"...\"로 변경 / 설명 업데이트: ... / state_id: <id> / priority: 0~4"
                        ],
                    )
                issue_id, resolved_issue_url, current_issue_description = await _resolve_linear_issue_id_for_update(
                    user_id=user_id,
                    issue_ref=issue_ref,
                )
                patch_payload: dict = {"issue_id": issue_id}
                if linear_update_new_title:
                    patch_payload["title"] = linear_update_new_title[:120]
                if linear_update_description_text:
                    if linear_update_append_intent:
                        patch_payload["description"] = _merge_linear_description(
                            current=current_issue_description,
                            addition=linear_update_description_text,
                        )
                    else:
                        patch_payload["description"] = linear_update_description_text
                if linear_update_state_id:
                    patch_payload["state_id"] = linear_update_state_id
                if linear_update_priority is not None:
                    patch_payload["priority"] = linear_update_priority
                if (
                    "title" not in patch_payload
                    and "description" not in patch_payload
                    and "state_id" not in patch_payload
                    and "priority" not in patch_payload
                ):
                    if linear_update_allow_generated_description:
                        patch_payload["description"] = _merge_linear_description(
                            current=current_issue_description,
                            addition=llm_text,
                        )
                    else:
                        raise NeedsInputSignal(
                            missing_fields=["patch"],
                            questions=[
                                "어떤 항목을 업데이트할까요? 예: 제목을 \"...\"로 변경 / 설명 업데이트: ... / state_id: <id> / priority: 0~4"
                            ],
                        )
                update_result = await execute_tool(
                    user_id=user_id,
                    tool_name="linear_update_issue",
                    payload=patch_payload,
                )
                update_success = bool((((update_result.get("data") or {}).get("issueUpdate") or {}).get("success")))
                if not update_success and (
                    "title" in patch_payload
                    or "description" in patch_payload
                    or "state_id" in patch_payload
                    or "priority" in patch_payload
                ):
                    raise HTTPException(status_code=400, detail="linear_issue_update_failed")
                issue_url = str(
                    (((update_result.get("data") or {}).get("issueUpdate") or {}).get("issue") or {}).get("url") or ""
                ).strip()
                if not issue_url:
                    issue_url = resolved_issue_url
                if linear_update_new_title:
                    user_message = f"Linear 이슈 제목이 \"{linear_update_new_title[:120]}\"로 업데이트되었습니다.\n\n대상 이슈: {issue_ref}"
                elif linear_update_description_text:
                    user_message = f"Linear 이슈 설명이 업데이트되었습니다.\n\n대상 이슈: {issue_ref}"
                elif linear_update_state_id or linear_update_priority is not None:
                    updates: list[str] = []
                    if linear_update_state_id:
                        updates.append(f"state_id={linear_update_state_id}")
                    if linear_update_priority is not None:
                        updates.append(f"priority={linear_update_priority}")
                    user_message = f"Linear 이슈 속성이 업데이트되었습니다. ({', '.join(updates)})\n\n대상 이슈: {issue_ref}"
                else:
                    user_message = f"Linear 이슈 설명이 업데이트되었습니다.\n\n대상 이슈: {issue_ref}"
                if issue_url:
                    user_message += f"\n링크: {issue_url}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=user_message,
                    summary="LLM 생성 후 Linear 이슈 업데이트 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "updated_issue_id": issue_id,
                        "updated_issue_url": issue_url,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(name="skill_linear_update_issue", status="success", detail=f"issue_ref={issue_ref}"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "linear.issue_create":
                issue_title = str(decision.arguments.get("linear_issue_title") or "").strip()
                if not issue_title:
                    issue_title = _extract_linear_issue_title_for_create(user_text) or ""
                if not issue_title:
                    issue_title = "new issue"
                team_ref = str(decision.arguments.get("linear_team_ref") or "").strip() or None
                team_id = await _resolve_linear_team_id_for_create(user_id=user_id, team_ref=team_ref)
                result = await execute_tool(
                    user_id=user_id,
                    tool_name="linear_create_issue",
                    payload={"team_id": team_id, "title": issue_title[:120], "description": llm_text},
                )
                issue_url = str((((result.get("data") or {}).get("issueCreate") or {}).get("issue") or {}).get("url") or "").strip()
                msg = f"{llm_text}\n\nLinear 이슈 생성 완료: {issue_title[:120]}"
                if issue_url:
                    msg += f"\n링크: {issue_url}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=msg,
                    summary="LLM 생성 후 Linear 이슈 생성 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "created_issue_url": issue_url,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(
                            name="skill_linear_create_issue",
                            status="success",
                            detail=f"team_ref={team_ref or 'auto'}",
                        ),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "linear.issue_delete":
                issue_ref = str(decision.arguments.get("linear_issue_ref") or "").strip()
                if not issue_ref:
                    raise HTTPException(status_code=400, detail="validation_error")
                issue_id, _, _ = await _resolve_linear_issue_id_for_update(user_id=user_id, issue_ref=issue_ref)
                delete_result = await execute_tool(
                    user_id=user_id,
                    tool_name="linear_update_issue",
                    payload={"issue_id": issue_id, "archived": True},
                )
                archive_success = bool((((delete_result.get("data") or {}).get("issueArchive") or {}).get("success")))
                update_success = bool((((delete_result.get("data") or {}).get("issueUpdate") or {}).get("success")))
                if not archive_success and not update_success:
                    raise HTTPException(status_code=400, detail="linear_issue_delete_failed")
                execution = AgentExecutionResult(
                    success=True,
                    user_message=f"요청한 Linear 이슈를 삭제(archive) 처리했습니다.\n- 이슈: {issue_ref}",
                    summary="Linear 이슈 삭제 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "deleted_issue_id": issue_id,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(name="skill_linear_update_issue_delete", status="success", detail=f"issue_ref={issue_ref}"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "notion.page_delete":
                page_title = str(decision.arguments.get("notion_page_title") or "").strip()
                if not page_title:
                    raise NeedsInputSignal(
                        missing_fields=["target.page_title"],
                        questions=["삭제할 Notion 페이지 제목을 알려주세요. 예: 제목: 스프린트 회고"],
                    )
                page_id, page_url, _ = await _resolve_notion_page_for_update(user_id=user_id, title=page_title)
                await execute_tool(
                    user_id=user_id,
                    tool_name="notion_update_page",
                    payload={"page_id": page_id, "in_trash": True},
                )
                execution = AgentExecutionResult(
                    success=True,
                    user_message=f"요청한 Notion 페이지를 삭제(휴지통 이동)했습니다.\n- 제목: {page_title}" + (
                        f"\n- 링크: {page_url}" if page_url else ""
                    ),
                    summary="Notion 페이지 삭제 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "deleted_page_id": page_id,
                        "deleted_page_url": page_url,
                        "llm_provider": provider,
                        "llm_model": model,
                    },
                    steps=[
                        AgentExecutionStep(name="llm_generate", status="success", detail=f"provider={provider}:{model}"),
                        AgentExecutionStep(name="skill_notion_update_page_delete", status="success", detail=f"page_title={page_title}"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            raise HTTPException(status_code=400, detail="unsupported_skill")

        if decision.mode == MODE_SKILL_THEN_LLM:
            skill_name = str(decision.skill_name or "").strip() or infer_skill_name_from_runtime_tools(
                decision.selected_tools
            )
            if skill_name == "linear.issue_search" or ("linear" in decision.target_services and not skill_name):
                query = str(decision.arguments.get("linear_query") or "").strip()
                first = _safe_int(
                    decision.arguments.get("linear_first"),
                    default=_extract_count_limit(user_text, default=5),
                    minimum=1,
                    maximum=20,
                )
                issue_ref = _extract_linear_issue_reference(query or user_text)
                if issue_ref:
                    tool_result = await _linear_search_with_issue_ref_fallback(user_id=user_id, issue_ref=issue_ref)
                else:
                    if _is_linear_recent_list_intent(user_text) or not query:
                        tool_result = await execute_tool(
                            user_id=user_id,
                            tool_name="linear_list_issues",
                            payload={"first": first},
                        )
                    else:
                        tool_result = await execute_tool(
                            user_id=user_id,
                            tool_name="linear_search_issues",
                            payload={"query": query, "first": first},
                        )
                if _linear_issue_count(tool_result) <= 0:
                    raise NeedsInputSignal(
                        missing_fields=["target.issue_ref"],
                        questions=[f"'{query or issue_ref or user_text}' 이슈를 찾지 못했습니다. 이슈 키(예: OPT-35)를 확인해 주세요."],
                    )
                # "최근/목록/검색" 요청은 해설 생성 대신 결과 리스트를 직접 반환한다.
                if _is_linear_recent_list_intent(user_text) and not _is_analysis_intent(user_text):
                    execution = AgentExecutionResult(
                        success=True,
                        user_message=_linear_issue_list_text(tool_result, limit=first),
                        summary="Linear 최근 이슈 조회 완료",
                        artifacts={"router_mode": decision.mode},
                        steps=[
                            AgentExecutionStep(
                                name="skill_linear_issue_lookup",
                                status="success",
                                detail=f"query={query or issue_ref or '-'};first={first}",
                            )
                        ],
                    )
                    return AgentRunResult(
                        ok=True,
                        stage="execution",
                        plan=plan,
                        result_summary=execution.summary,
                        execution=execution,
                        plan_source="router_v2",
                    )
                issue_context = _linear_issues_to_context(tool_result)
                prompt = (
                    "다음 Linear 이슈 정보를 바탕으로 해결 방법을 한국어로 간결하게 정리해줘. "
                    "사실과 추론을 구분하고, 실행 가능한 체크리스트 형태로 답변해줘.\n\n"
                    f"[사용자 요청]\n{user_text}\n\n"
                    f"[Linear 이슈]\n{issue_context}"
                )
                answer, provider, model = await _request_llm_text(prompt=prompt)
                plan.notes.append(f"llm_provider={provider}")
                plan.notes.append(f"llm_model={model}")
                links_block = _linear_issue_links_block(tool_result, limit=10)
                user_message = answer
                if links_block:
                    user_message = f"{answer}\n\n{links_block}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=user_message,
                    summary="Linear 조회 후 LLM 정리 완료",
                    artifacts={"router_mode": decision.mode, "llm_provider": provider, "llm_model": model},
                    steps=[
                        AgentExecutionStep(
                            name="skill_linear_issue_lookup",
                            status="success",
                            detail=f"query={query or issue_ref or '-'};first={first}",
                        ),
                        AgentExecutionStep(name="llm_solve", status="success", detail=f"provider={provider}:{model}"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            if skill_name == "notion.page_search" or ("notion" in decision.target_services and not skill_name):
                if _is_notion_recent_list_intent(user_text):
                    first = _safe_int(
                        decision.arguments.get("notion_first"),
                        default=_extract_count_limit(user_text, default=5),
                        minimum=1,
                        maximum=20,
                    )
                    tool_result = await execute_tool(
                        user_id=user_id,
                        tool_name="notion_search",
                        payload={"page_size": first},
                    )
                    execution = AgentExecutionResult(
                        success=True,
                        user_message=_notion_page_list_text(tool_result, limit=first),
                        summary="Notion 최근 페이지 조회 완료",
                        artifacts={"router_mode": decision.mode},
                        steps=[
                            AgentExecutionStep(
                                name="skill_notion_search",
                                status="success",
                                detail=f"query=;page_size={first}",
                            )
                        ],
                    )
                    return AgentRunResult(
                        ok=True,
                        stage="execution",
                        plan=plan,
                        result_summary=execution.summary,
                        execution=execution,
                        plan_source="router_v2",
                    )
                page_title = str(decision.arguments.get("notion_page_title") or "").strip()
                if not page_title:
                    raise NeedsInputSignal(
                        missing_fields=["target.page_title"],
                        questions=["조회할 Notion 페이지 제목을 알려주세요. 예: 제목: 스프린트 회고"],
                    )
                page_id, page_url, _ = await _resolve_notion_page_for_update(user_id=user_id, title=page_title)
                block_result = await execute_tool(
                    user_id=user_id,
                    tool_name="notion_retrieve_block_children",
                    payload={"block_id": page_id, "page_size": 50},
                )
                page_context = _notion_blocks_to_context(block_result)
                prompt = (
                    "다음 Notion 페이지 본문을 바탕으로 사용자의 요청에 맞게 한국어로 정리해줘. "
                    "본문에 없는 내용은 추측하지 말고, 필요한 경우 확인 질문을 제안해줘.\n\n"
                    f"[사용자 요청]\n{user_text}\n\n"
                    f"[페이지 제목]\n{page_title}\n\n"
                    f"[본문]\n{page_context}"
                )
                answer, provider, model = await _request_llm_text(prompt=prompt)
                plan.notes.append(f"llm_provider={provider}")
                plan.notes.append(f"llm_model={model}")
                user_message = answer
                if page_url:
                    user_message += f"\n\n참조 페이지: {page_url}"
                execution = AgentExecutionResult(
                    success=True,
                    user_message=user_message,
                    summary="Notion 조회 후 LLM 정리 완료",
                    artifacts={
                        "router_mode": decision.mode,
                        "llm_provider": provider,
                        "llm_model": model,
                        "source_page_id": page_id,
                        "source_page_url": page_url,
                    },
                    steps=[
                        AgentExecutionStep(name="skill_notion_search", status="success", detail=f"title={page_title}"),
                        AgentExecutionStep(name="skill_notion_retrieve_block_children", status="success", detail=f"page_id={page_id}"),
                        AgentExecutionStep(name="llm_solve", status="success", detail=f"provider={provider}:{model}"),
                    ],
                )
                return AgentRunResult(
                    ok=True,
                    stage="execution",
                    plan=plan,
                    result_summary=execution.summary,
                    execution=execution,
                    plan_source="router_v2",
                )

            raise HTTPException(status_code=400, detail="unsupported_service")

    except NeedsInputSignal as signal:
        needs_input_message = _build_needs_input_message(questions=signal.questions, choices=signal.choices)
        execution = AgentExecutionResult(
            success=False,
            user_message=needs_input_message,
            summary="추가 입력이 필요합니다.",
            artifacts={
                "error_code": "validation_error",
                "needs_input": "true",
                "missing_fields_json": json.dumps(signal.missing_fields, ensure_ascii=False),
                "questions_json": json.dumps(signal.questions, ensure_ascii=False),
                "choices_json": json.dumps(signal.choices, ensure_ascii=False),
            },
            steps=[AgentExecutionStep(name="router_v2_needs_input", status="error", detail="needs_input")],
        )
        return AgentRunResult(
            ok=False,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )
    except HTTPException as exc:
        detail = str(exc.detail or "unknown_error")
        detail_hint = detail
        if len(detail_hint) > 220:
            detail_hint = detail_hint[:220].rstrip() + "..."
        execution = AgentExecutionResult(
            success=False,
            user_message=(
                "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.\n"
                f"(error: {detail_hint})"
            ),
            summary="V2 오케스트레이션 실행 실패",
            artifacts={"error_code": detail, "router_mode": decision.mode},
            steps=[AgentExecutionStep(name="router_v2", status="error", detail=detail)],
        )
        return AgentRunResult(
            ok=False,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    return None
