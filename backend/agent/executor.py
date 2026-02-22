from __future__ import annotations

import json
import re
from html import unescape
from datetime import datetime, timezone
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from agent.intent_keywords import (
    contains_any,
    is_create_intent,
    is_linear_issue_create_intent,
    is_read_intent,
    is_summary_intent,
    is_update_intent,
)
from agent.planner import build_execution_tasks
from agent.slot_collector import collect_slots_from_user_reply
from agent.slot_schema import get_action_slot_schema, validate_slots
from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan, AgentTask
from app.core.config import get_settings


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


@dataclass(frozen=True)
class CopyRequest:
    source_service: str
    source_ref: str
    target_service: str
    target_ref: str
    target_field: str


def _map_execution_error(detail: str) -> tuple[str, str, str]:
    code = detail or "unknown_error"
    lower = code.lower()
    upstream_message_match = re.search(r"\|message=([^|]+)", code)
    upstream_message = upstream_message_match.group(1).strip() if upstream_message_match else ""

    if "notion_not_connected" in lower or lower.endswith("_not_connected"):
        return (
            "서비스 연결이 필요합니다.",
            "요청한 서비스가 연결되어 있지 않습니다. 대시보드에서 연동 후 다시 시도해주세요.",
            "service_not_connected",
        )
    if "token_missing" in lower or lower.endswith("_token_missing"):
        return (
            "연동 토큰을 찾지 못했습니다.",
            "연동 토큰 정보를 찾지 못했습니다. 연동을 해제 후 다시 연결해주세요.",
            "token_missing",
        )
    if "auth_required" in lower or "auth_forbidden" in lower:
        return (
            "외부 서비스 권한 오류가 발생했습니다.",
            "권한이 부족하거나 만료되었습니다. 연동 권한을 다시 확인해주세요.",
            "auth_error",
        )
    if "rate_limited" in lower:
        return (
            "요청 한도를 초과했습니다.",
            "외부 API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
            "rate_limited",
        )
    if "not_found" in lower:
        return (
            "요청한 대상을 찾지 못했습니다.",
            "요청한 페이지/데이터를 찾지 못했습니다. 제목이나 ID를 확인해주세요.",
            "not_found",
        )
    if "validation_" in lower or "missing_path_param" in lower:
        field_hint = ""
        field_match = re.search(r"validation_[a-z]+:([a-zA-Z0-9_]+)", lower)
        if field_match:
            field_hint = f"\n세부: `{field_match.group(1)}` 값 형식을 확인해주세요."
        path_match = re.search(r"missing_path_param:([a-zA-Z0-9_]+)", lower)
        if path_match:
            field_hint = f"\n세부: `{path_match.group(1)}` 값이 필요합니다."
        return (
            "요청 형식이 올바르지 않습니다.",
            f"요청 파라미터가 올바르지 않습니다. 제목/개수/ID 형식을 확인해주세요.{field_hint}",
            "validation_error",
        )
    if "tool_failed" in lower or "notion_api_failed" in lower or "notion_parse_failed" in lower:
        hint = ""
        if upstream_message:
            hint = f"\n세부: {upstream_message[:200]}"
        return (
            "외부 서비스 처리 중 오류가 발생했습니다.",
            f"외부 서비스 응답 처리에 실패했습니다. 잠시 후 다시 시도해주세요.{hint}",
            "upstream_error",
        )
    return (
        "작업 실행 중 오류가 발생했습니다.",
        "요청을 실행하던 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "execution_error",
    )


def _extract_page_title(page: dict) -> str:
    properties = page.get("properties", {})
    for value in properties.values():
        if value.get("type") == "title":
            chunks = value.get("title", [])
            text = "".join(chunk.get("plain_text", "") for chunk in chunks).strip()
            if text:
                return text
    return "(제목 없음)"


def _extract_plain_text_from_blocks(blocks: list[dict]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if not block_type:
            continue
        data = block.get(block_type, {})
        rich_text = data.get("rich_text", [])
        text = "".join(chunk.get("plain_text", "") for chunk in rich_text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip().lower()


def _simple_korean_summary(text: str, max_chars: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return "본문 텍스트를 찾지 못했습니다."
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


def _extract_summary_line_count(user_text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(줄|라인|line|lines|문장|sentence|sentences)", user_text, flags=re.IGNORECASE)
    if not match:
        return None
    return max(1, min(10, int(match.group(1))))


def _split_sentences_for_format(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[\.\?\!])\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def _split_into_chunks(text: str, target_count: int) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    if target_count <= 1:
        return [compact]
    words = compact.split(" ")
    if len(words) <= target_count:
        return [word for word in words if word]
    chunk_size = max(1, len(words) // target_count)
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(current) >= chunk_size and len(chunks) < target_count - 1:
            chunks.append(" ".join(current).strip())
            current = []
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _format_summary_output(text: str, requested_lines: int | None) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "본문 텍스트를 찾지 못했습니다."
    if not requested_lines:
        return cleaned
    compact = re.sub(r"\s+", " ", cleaned).strip()
    if requested_lines == 1:
        return compact
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        lines = [compact]
    if len(lines) < requested_lines:
        sentence_lines = _split_sentences_for_format(compact)
        if len(sentence_lines) >= requested_lines:
            lines = sentence_lines[:requested_lines]
        else:
            chunked = _split_into_chunks(compact, requested_lines)
            if chunked:
                lines = chunked
    if len(lines) < requested_lines:
        filler = lines[-1] if lines else compact
        while len(lines) < requested_lines:
            lines.append(filler)
    lines = lines[:requested_lines]
    return "\n".join(f"{idx}. {line}" for idx, line in enumerate(lines, start=1))


def _validate_summary_output(summary: str, user_text: str, requested_lines: int | None) -> tuple[bool, str]:
    cleaned = (summary or "").strip()
    if not cleaned:
        return False, "empty_summary"

    compact = re.sub(r"\s+", " ", cleaned).strip()
    char_limit = _extract_summary_char_limit(user_text)
    if char_limit and len(compact) > char_limit:
        return False, "char_limit_exceeded"

    lower = compact.lower()
    forbidden_tokens = (
        "ignore previous",
        "system prompt",
        "developer message",
        "<script",
        "</script>",
    )
    if any(token in lower for token in forbidden_tokens):
        return False, "forbidden_token_detected"

    if requested_lines and requested_lines > 1:
        line_count = len([line for line in cleaned.splitlines() if line.strip()])
        if line_count != requested_lines:
            return False, "line_count_mismatch"
        line_pattern = re.compile(r"^\s*\d+\.\s+.+$")
        for line in cleaned.splitlines():
            if line.strip() and not line_pattern.match(line):
                return False, "line_format_invalid"

    return True, "ok"


def _clip_summary_to_char_limit(summary: str, user_text: str) -> str:
    char_limit = _extract_summary_char_limit(user_text)
    if not char_limit:
        return summary
    compact = re.sub(r"\s+", " ", summary).strip()
    if len(compact) <= char_limit:
        return compact
    return compact[:char_limit].rstrip()


async def _request_summary_with_provider(
    *,
    provider: str,
    model: str,
    text: str,
    line_count: int | None,
    openai_api_key: str | None,
    google_api_key: str | None,
) -> str | None:
    line_rule = (
        f"반드시 정확히 {line_count}줄로 출력하세요. 각 줄은 핵심만 간결하게 작성하세요."
        if line_count
        else "3문장 이내로 간결하게 요약하세요."
    )
    prompt = (
        "다음 Notion 페이지 본문을 한국어로 요약하세요.\n"
        f"{line_rule}\n"
        "원문 사실을 벗어나지 말고, 추측하지 마세요.\n\n"
        f"[본문]\n{text}"
    )
    if provider == "openai":
        if not openai_api_key:
            return None
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "당신은 요약 도우미입니다."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip() or None
    if provider == "gemini":
        if not google_api_key:
            return None
        url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=google_api_key)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code >= 400:
            return None
        data = resp.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text_out = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        return text_out or None
    return None


async def _summarize_text_with_llm(text: str, user_text: str) -> tuple[str, str]:
    line_count = _extract_summary_line_count(user_text)
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

    for provider, model in attempts:
        for attempt_idx in range(2):
            try:
                summary = await _request_summary_with_provider(
                    provider=provider,
                    model=model,
                    text=text,
                    line_count=line_count,
                    openai_api_key=settings.openai_api_key,
                    google_api_key=settings.google_api_key,
                )
                if not summary:
                    continue
                formatted = _format_summary_output(summary, line_count)
                formatted = _clip_summary_to_char_limit(formatted, user_text)
                ok, reason = _validate_summary_output(formatted, user_text, line_count)
                if ok:
                    mode = f"llm:{provider}:{model}"
                    if attempt_idx == 1:
                        mode += ":retry1"
                    return formatted, mode
                if attempt_idx == 1:
                    break
                continue
            except Exception:
                continue

    fallback_char_limit = _extract_summary_char_limit(user_text) or 700
    fallback = _simple_korean_summary(text, max_chars=max(50, min(700, fallback_char_limit)))
    formatted_fallback = _format_summary_output(fallback, line_count)
    formatted_fallback = _clip_summary_to_char_limit(formatted_fallback, user_text)
    ok, reason = _validate_summary_output(formatted_fallback, user_text, line_count)
    if ok:
        return formatted_fallback, "fallback"
    return "요약 결과를 생성하지 못했습니다.", f"fallback_invalid:{reason}"


def _extract_requested_count(plan: AgentPlan, default_count: int = 3) -> int:
    for req in plan.requirements:
        if req.quantity and req.quantity > 0:
            return max(1, min(10, req.quantity))
    return default_count


def _normalize_issue_nodes_from_result(result: dict) -> list[dict]:
    data = result.get("data") or {}
    nodes = (((data.get("issues") or {}).get("nodes")) or [])
    normalized: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        normalized.append(
            {
                "id": node.get("id") or "",
                "identifier": node.get("identifier") or "",
                "title": node.get("title") or "(제목 없음)",
                "url": node.get("url") or "",
                "state": ((node.get("state") or {}).get("name")) or "",
            }
        )
    return normalized


def _format_issue_text_for_summary(issues: list[dict]) -> str:
    if not issues:
        return "요약할 이슈가 없습니다."
    lines: list[str] = []
    for idx, issue in enumerate(issues, start=1):
        lines.append(
            f"{idx}. [{issue.get('identifier') or '-'}] {issue.get('title') or '(제목 없음)'} "
            f"(상태: {issue.get('state') or '-'})"
        )
    return "\n".join(lines)


def _split_summary_sentences(text: str) -> list[str]:
    stripped = re.sub(r"^\s*\d+\.\s*", "", text.strip(), flags=re.MULTILINE)
    by_lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(by_lines) >= 2:
        return by_lines
    compact = re.sub(r"\s+", " ", stripped).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[\.\?\!])\s+", compact)
    parts = [part.strip() for part in parts if part.strip()]
    return parts or [compact]


def _enforce_sentence_count(text: str, sentence_count: int) -> str:
    sentences = _split_summary_sentences(text)
    if not sentences:
        return "요약 결과가 비어 있습니다."

    clipped = sentences[: max(1, sentence_count)]
    normalized: list[str] = []
    for sentence in clipped:
        item = sentence.strip()
        if not item:
            continue
        if item[-1] not in ".!?":
            item = f"{item}."
        normalized.append(item)
    return " ".join(normalized).strip()


def _find_task(tasks: list[AgentTask], *, task_type: str, service: str | None = None, tool_token: str | None = None) -> AgentTask | None:
    for task in tasks:
        if task.task_type.upper() != task_type.upper():
            continue
        if service and (task.service or "").lower() != service.lower():
            continue
        if tool_token and tool_token.lower() not in (task.tool_name or "").lower():
            continue
        return task
    return None


def _supports_linear_summary_to_notion_flow(plan: AgentPlan) -> bool:
    tasks = plan.tasks or []
    if not tasks:
        return False
    linear_task = _find_task(tasks, task_type="TOOL", service="linear", tool_token="issues")
    llm_task = _find_task(tasks, task_type="LLM")
    notion_task = _find_task(tasks, task_type="TOOL", service="notion", tool_token="create_page")
    if not linear_task or not llm_task or not notion_task:
        return False
    task_ids = [item.id for item in tasks]
    try:
        return task_ids.index(linear_task.id) < task_ids.index(llm_task.id) < task_ids.index(notion_task.id)
    except ValueError:
        return False


def _is_tool_task(task: AgentTask) -> bool:
    return task.task_type.upper() == "TOOL"


def _is_llm_task(task: AgentTask) -> bool:
    return task.task_type.upper() == "LLM"


def _has_task_orchestration_candidate(plan: AgentPlan) -> bool:
    tasks = plan.tasks or []
    if not tasks:
        return False
    if not any(_is_tool_task(task) for task in tasks):
        return False
    return all(task.task_type.upper() in {"TOOL", "LLM"} for task in tasks)


def _ensure_common_tool_tasks(plan: AgentPlan) -> AgentPlan:
    if plan.tasks:
        return plan
    synthesized = build_execution_tasks(
        user_text=plan.user_text,
        target_services=plan.target_services,
        selected_tools=plan.selected_tools,
    )
    if synthesized:
        plan.tasks = synthesized
        plan.notes.append("tasks_synthesized_for_common_slot_loop")
    return plan


def _extract_page_url_from_tool_result(result: dict) -> str:
    data = result.get("data")
    if isinstance(data, dict):
        return str(data.get("url") or "")
    return ""


def _extract_linear_issue_url_from_tool_result(result: dict) -> str:
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return ""
    for key in ("issueCreate", "issueUpdate"):
        payload = data.get(key) or {}
        issue = payload.get("issue") if isinstance(payload, dict) else {}
        if not isinstance(issue, dict):
            continue
        candidate = str(issue.get("url") or "").strip()
        if candidate:
            return candidate
    return ""


def _extract_upstream_message(detail: str) -> str:
    match = re.search(r"\|message=([^|]+)", detail or "")
    if not match:
        return ""
    return unescape(match.group(1).strip())


def _task_output_as_text(value: dict) -> str:
    if "summary_text" in value:
        return str(value.get("summary_text") or "")
    result = value.get("tool_result")
    if not isinstance(result, dict):
        return ""
    issues = _normalize_issue_nodes_from_result(result)
    if issues:
        return _format_issue_text_for_summary(issues)
    notion_results = ((result.get("data") or {}).get("results") or [])
    if isinstance(notion_results, list) and notion_results:
        lines: list[str] = []
        for idx, item in enumerate(notion_results[:20], start=1):
            if not isinstance(item, dict):
                continue
            title = _extract_page_title(item)
            url = item.get("url") or ""
            lines.append(f"{idx}. {title}")
            if url:
                lines.append(f"   {url}")
        if lines:
            return "\n".join(lines)
    data = result.get("data")
    if isinstance(data, dict):
        try:
            return json.dumps(data, ensure_ascii=False)
        except TypeError:
            return str(data)
    return ""


def _collect_dependency_text(task: AgentTask, task_outputs: dict[str, dict]) -> str:
    chunks: list[str] = []
    for dep in task.depends_on:
        output = task_outputs.get(dep)
        if not output:
            continue
        text = _task_output_as_text(output).strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks).strip()


def _build_task_tool_payload(
    *,
    plan: AgentPlan,
    task: AgentTask,
    task_outputs: dict[str, dict],
) -> dict:
    tool_name = (task.tool_name or "").strip()
    payload = dict(task.payload or {})

    if "linear_search_issues" in tool_name:
        payload.setdefault("first", 5)
        payload.setdefault("query", _extract_linear_search_query(plan.user_text) or "")
        if not payload["query"]:
            payload.pop("query", None)
        return payload

    if "linear_list_issues" in tool_name:
        payload.setdefault("first", 5)
        return payload

    if "notion_create_page" in tool_name:
        title_hint = str(payload.get("title_hint") or _extract_output_title(plan.user_text, "Metel 자동 요약")).strip()[:100]
        dependency_text = _collect_dependency_text(task, task_outputs)
        children = []
        if dependency_text:
            children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:1800]}}]},
                }
                for line in dependency_text.splitlines()
                if line.strip()
            ][:80]
        return {
            "parent": _notion_create_parent_payload(),
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title_hint}}]},
            },
            **({"children": children} if children else {}),
        }

    if "notion_query_data_source" in tool_name:
        parsed_id, parsed_page_size, _ = _extract_data_source_query_request(plan.user_text)
        data_source_id = str(payload.get("data_source_id") or parsed_id or "").strip()
        page_size = int(payload.get("page_size") or parsed_page_size or 5)
        return {
            "data_source_id": data_source_id,
            "page_size": max(1, min(20, page_size)),
        }

    return payload


def _slot_prompt_example(tool_name: str, slot_name: str) -> str:
    schema = get_action_slot_schema(tool_name)
    if not schema:
        return f"{slot_name}: <값>"
    aliases = schema.aliases.get(slot_name) or ()
    hint = aliases[0] if aliases else slot_name
    rule = schema.validation_rules.get(slot_name) or {}
    slot_type = str(rule.get("type", "")).strip().lower()
    if slot_type == "integer":
        return f"{hint}: 5"
    if slot_type == "boolean":
        return f"{hint}: true"
    return f'{hint}: "값"'


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _first_notion_page_id(result: dict) -> str:
    data = result.get("data") or {}
    if isinstance(data, dict):
        page_id = str(data.get("id") or "").strip()
        if page_id:
            return page_id
        results = data.get("results") or []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                candidate = str(item.get("id") or "").strip()
                if candidate:
                    return candidate
    return ""


def _first_linear_issue_id(result: dict) -> str:
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return ""
    issues = ((data.get("issues") or {}).get("nodes") or [])
    if isinstance(issues, list):
        for item in issues:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("id") or "").strip()
            if candidate:
                return candidate
    for key in ("issueCreate", "issueUpdate"):
        payload = data.get(key) or {}
        issue = payload.get("issue") if isinstance(payload, dict) else {}
        if isinstance(issue, dict):
            candidate = str(issue.get("id") or "").strip()
            if candidate:
                return candidate
    return ""


def _first_linear_team_id(result: dict) -> str:
    data = result.get("data") or {}
    teams = ((data.get("teams") or {}).get("nodes") or []) if isinstance(data, dict) else []
    if isinstance(teams, list):
        for item in teams:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("id") or "").strip()
            if candidate:
                return candidate
    return ""


def _update_slot_context_from_tool_result(slot_context: dict[str, str], tool_name: str, tool_result: dict) -> None:
    if "notion" in tool_name:
        page_id = _first_notion_page_id(tool_result)
        if page_id:
            slot_context["recent_notion_page_id"] = page_id
    if "linear" in tool_name:
        issue_id = _first_linear_issue_id(tool_result)
        if issue_id:
            slot_context["recent_linear_issue_id"] = issue_id
        team_id = _first_linear_team_id(tool_result)
        if team_id:
            slot_context["recent_linear_team_id"] = team_id


async def _resolve_notion_page_id_from_title(
    *,
    user_id: str,
    plan: AgentPlan,
    page_title: str,
    steps: list[AgentExecutionStep],
) -> str:
    title = (page_title or "").strip()
    if not title:
        return ""
    result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "search", "notion_search"),
        payload={"query": title, "page_size": 5},
    )
    pages = ((result.get("data") or {}).get("results") or [])
    steps.append(AgentExecutionStep(name="slot_fill_notion_search", status="success", detail=f"count={len(pages)}"))
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "").strip()
        if page_id:
            return page_id
    return ""


def _extract_first_quoted_text(user_text: str) -> str | None:
    for a, b in re.findall(r'"([^"]+)"|\'([^\']+)\'', user_text or ""):
        value = (a or b or "").strip()
        if value:
            return value
    return None


def _is_llm_planner_plan(plan: AgentPlan) -> bool:
    return any(str(note or "").strip() == "planner=llm" for note in (plan.notes or []))


def _merge_keyed_slots_from_user_text(*, action: str, user_text: str, filled: dict) -> dict:
    schema = get_action_slot_schema(action)
    if not schema:
        return filled
    collected = collect_slots_from_user_reply(
        action=action,
        user_text=user_text,
        collected_slots=filled,
    )
    merged = dict(filled)
    for key, value in collected.collected_slots.items():
        if value in (None, ""):
            continue
        merged[key] = value
    return merged


async def _autofill_task_payload(
    *,
    user_id: str,
    plan: AgentPlan,
    task: AgentTask,
    payload: dict,
    steps: list[AgentExecutionStep],
    slot_context: dict[str, str],
) -> dict:
    tool_name = (task.tool_name or "").strip().lower()
    filled = dict(payload or {})
    user_text = plan.user_text or ""
    settings = get_settings()
    allow_user_text_reparse = bool(getattr(settings, "rule_reparse_for_llm_plan_enabled", False)) or not _is_llm_planner_plan(plan)
    if allow_user_text_reparse:
        # Common slot fill path for all actions with schema; regex branches below are fallback only.
        filled = _merge_keyed_slots_from_user_text(action=tool_name, user_text=user_text, filled=filled)

    if "notion_search" in tool_name and _missing(filled.get("query")) and allow_user_text_reparse:
        query = _extract_target_page_title(user_text) or _extract_first_quoted_text(user_text) or ""
        if query:
            filled["query"] = query

    if "notion_query_data_source" in tool_name and _missing(filled.get("data_source_id")) and allow_user_text_reparse:
        parsed_id, parsed_page_size, _ = _extract_data_source_query_request(user_text)
        if parsed_id:
            filled["data_source_id"] = parsed_id
        if _missing(filled.get("page_size")):
            filled["page_size"] = parsed_page_size

    if "notion_update_page" in tool_name and _missing(filled.get("page_id")):
        page_id = slot_context.get("recent_notion_page_id", "")
        if not page_id and allow_user_text_reparse:
            rename_title, _ = _extract_page_rename_request(user_text)
            move_title, _ = _extract_move_request(user_text)
            archive_title = _extract_page_archive_target(user_text)
            candidate_title = rename_title or move_title or archive_title or _extract_first_quoted_text(user_text) or ""
            if candidate_title:
                page_id = await _resolve_notion_page_id_from_title(
                    user_id=user_id,
                    plan=plan,
                    page_title=candidate_title,
                    steps=steps,
                )
        if page_id:
            filled["page_id"] = page_id

    if "notion_append_block_children" in tool_name and _missing(filled.get("block_id")):
        page_id = slot_context.get("recent_notion_page_id", "")
        if not page_id and allow_user_text_reparse:
            target_title, content = _extract_append_target_and_content(user_text)
            candidate_title = target_title or _extract_first_quoted_text(user_text) or ""
            if candidate_title:
                page_id = await _resolve_notion_page_id_from_title(
                    user_id=user_id,
                    plan=plan,
                    page_title=candidate_title,
                    steps=steps,
                )
            if _missing(filled.get("children")) and content:
                filled["children"] = [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": content[:1800]}}]},
                    }
                ]
        if page_id:
            filled["block_id"] = page_id

    if "linear_create_issue" in tool_name:
        if _missing(filled.get("title")) and allow_user_text_reparse:
            title_match = re.search(
                r'(?i)(?:제목|title)\s*[:：]\s*(.+?)(?:\s*(?:,|;)?\s*(?:팀|team|내용|설명|description|priority|우선순위)\s*[:：]|$)',
                user_text,
            )
            if title_match:
                filled["title"] = title_match.group(1).strip(" \"'`,")

        team_reference = str(filled.get("team_id") or "").strip()
        team_id = ""
        if team_reference and _looks_like_linear_team_id(team_reference):
            team_id = team_reference
        else:
            team_id = slot_context.get("recent_linear_team_id", "")
            if not team_id and (allow_user_text_reparse or bool(team_reference)):
                if not team_reference:
                    team_reference = _extract_linear_team_reference(user_text) or ""
                if team_reference:
                    team_id = await _resolve_linear_team_id_from_reference(
                        user_id=user_id,
                        plan=plan,
                        team_reference=team_reference,
                        steps=steps,
                    )
        if team_id:
            filled["team_id"] = team_id
        elif team_reference:
            # Do not pass unresolved team alias/key as team_id to API.
            filled.pop("team_id", None)

    if "linear_update_issue" in tool_name:
        issue_ref = str(filled.get("issue_id") or "").strip()
        if not issue_ref:
            issue_ref = slot_context.get("recent_linear_issue_id", "")
        if not issue_ref and allow_user_text_reparse:
            issue_ref = _extract_linear_issue_reference_for_update(user_text) or _extract_linear_issue_reference(user_text) or ""
        if issue_ref:
            issue_id = issue_ref
            unresolved_from_reference = False
            if not _looks_like_linear_internal_issue_id(issue_ref):
                issue_id = await _resolve_linear_issue_id_from_reference(
                    user_id=user_id,
                    plan=plan,
                    issue_reference=issue_ref,
                    steps=steps,
                    step_name="slot_fill_linear_search_issue_for_update",
                )
                unresolved_from_reference = not bool(issue_id)
            if issue_id:
                filled["issue_id"] = issue_id
            elif unresolved_from_reference:
                # Prevent sending identifier-like value as internal issue id to update API.
                filled.pop("issue_id", None)

    if "linear_create_comment" in tool_name:
        issue_ref = str(filled.get("issue_id") or "").strip()
        if not issue_ref:
            issue_ref = slot_context.get("recent_linear_issue_id", "")
        if not issue_ref and allow_user_text_reparse:
            issue_ref = _extract_linear_issue_reference(user_text) or ""
        if issue_ref:
            issue_id = issue_ref
            if not _looks_like_linear_internal_issue_id(issue_ref):
                issue_id = await _resolve_linear_issue_id_from_reference(
                    user_id=user_id,
                    plan=plan,
                    issue_reference=issue_ref,
                    steps=steps,
                    step_name="slot_fill_linear_search_issue_for_comment",
                )
            if issue_id:
                filled["issue_id"] = issue_id
        if _missing(filled.get("body")) and allow_user_text_reparse:
            body = _extract_linear_comment_body(user_text)
            if body:
                filled["body"] = body

    if "linear_search_issues" in tool_name and _missing(filled.get("query")) and allow_user_text_reparse:
        query = _extract_linear_search_query(user_text) or ""
        if query:
            filled["query"] = query

    return filled


async def _execute_task_orchestration(user_id: str, plan: AgentPlan) -> AgentExecutionResult | None:
    if not _has_task_orchestration_candidate(plan):
        return None

    tasks = plan.tasks or []
    task_outputs: dict[str, dict] = {}
    steps: list[AgentExecutionStep] = []
    slot_context: dict[str, str] = {}
    validated_payloads: list[dict[str, object]] = []

    for task in tasks:
        missing_deps = [dep for dep in task.depends_on if dep not in task_outputs]
        if missing_deps:
            return None

        if _is_tool_task(task):
            tool_name = (task.tool_name or "").strip()
            if not tool_name:
                return None
            payload = _build_task_tool_payload(plan=plan, task=task, task_outputs=task_outputs)
            payload = await _autofill_task_payload(
                user_id=user_id,
                plan=plan,
                task=task,
                payload=payload,
                steps=steps,
                slot_context=slot_context,
            )
            normalized, missing_slots, validation_errors = validate_slots(tool_name, payload)
            payload = normalized
            if validation_errors:
                return AgentExecutionResult(
                    success=False,
                    summary="도구 실행 입력 검증에 실패했습니다.",
                    user_message=(
                        "입력 형식이 올바르지 않습니다.\n"
                        f"- action: {tool_name}\n"
                        f"- 오류: {validation_errors[0]}"
                    ),
                    artifacts={
                        "error_code": "validation_error",
                        "slot_action": tool_name,
                        "slot_task_id": task.id,
                        "validation_error": validation_errors[0],
                        "validated_payload_json": json.dumps(payload, ensure_ascii=False),
                    },
                    steps=steps + [AgentExecutionStep(name=task.id, status="error", detail=f"validation:{validation_errors[0]}")],
                )
            if missing_slots:
                missing_slot = missing_slots[0]
                return AgentExecutionResult(
                    success=False,
                    summary="필수 입력 슬롯이 누락되었습니다.",
                    user_message=(
                        f"`{missing_slot}` 값을 먼저 알려주세요.\n"
                        f"예: {_slot_prompt_example(tool_name, missing_slot)}"
                    ),
                    artifacts={
                        "error_code": "validation_error",
                        "slot_action": tool_name,
                        "slot_task_id": task.id,
                        "missing_slot": missing_slot,
                        "missing_slots": ",".join(missing_slots),
                        "slot_payload_json": json.dumps(payload, ensure_ascii=False),
                    },
                    steps=steps + [AgentExecutionStep(name=task.id, status="error", detail=f"missing_slot:{missing_slot}")],
                )
            if "linear_update_issue" in tool_name:
                has_update_field = any(
                    payload.get(key) not in (None, "")
                    for key in ("title", "description", "state_id", "priority")
                )
                if not has_update_field:
                    return AgentExecutionResult(
                        success=False,
                        summary="Linear 이슈 수정 입력이 부족합니다.",
                        user_message=(
                            "`issue_id`와 변경할 필드가 필요합니다.\n"
                            f"예: {_slot_prompt_example(tool_name, 'description')}"
                        ),
                        artifacts={
                            "error_code": "validation_error",
                            "slot_action": tool_name,
                            "slot_task_id": task.id,
                            "missing_slot": "description",
                            "missing_slots": "description",
                            "slot_payload_json": json.dumps(payload, ensure_ascii=False),
                        },
                        steps=steps + [AgentExecutionStep(name=task.id, status="error", detail="missing_update_fields")],
                    )
            validated_payloads.append({"task_id": task.id, "tool_name": tool_name, "payload": payload})
            try:
                tool_result = await execute_tool(user_id=user_id, tool_name=tool_name, payload=payload)
            except HTTPException as exc:
                # Linear update can fail when planner/slot stage keeps identifier-like issue text.
                # Retry once by re-resolving issue reference from user text.
                detail = str(exc.detail or "")
                if "linear_update_issue" in tool_name and "TOOL_FAILED" in detail:
                    issue_ref = _extract_linear_issue_reference_for_update(plan.user_text) or _extract_linear_issue_reference(plan.user_text) or ""
                    if issue_ref:
                        resolved_issue_id = await _resolve_linear_issue_id_from_reference(
                            user_id=user_id,
                            plan=plan,
                            issue_reference=issue_ref,
                            steps=steps,
                            step_name="linear_update_retry_issue_resolve",
                        )
                        if resolved_issue_id and resolved_issue_id != str(payload.get("issue_id") or ""):
                            retry_payload = dict(payload)
                            retry_payload["issue_id"] = resolved_issue_id
                            validated_payloads.append(
                                {"task_id": task.id, "tool_name": f"{tool_name}:retry", "payload": retry_payload}
                            )
                            tool_result = await execute_tool(user_id=user_id, tool_name=tool_name, payload=retry_payload)
                            payload = retry_payload
                            steps.append(
                                AgentExecutionStep(
                                    name=f"{task.id}_retry",
                                    status="success",
                                    detail=f"tool={tool_name} issue_id_re_resolved",
                                )
                            )
                        else:
                            raise
                    else:
                        raise
                else:
                    raise
            _update_slot_context_from_tool_result(slot_context=slot_context, tool_name=tool_name, tool_result=tool_result)
            task_outputs[task.id] = {"kind": "tool", "tool_name": tool_name, "tool_result": tool_result}
            steps.append(AgentExecutionStep(name=task.id, status="success", detail=f"tool={tool_name}"))
            continue

        if _is_llm_task(task):
            dependency_text = _collect_dependency_text(task, task_outputs)
            if not dependency_text:
                dependency_text = plan.user_text
            sentence_count = max(1, min(10, int((task.payload or {}).get("sentences", 3))))
            summary_raw, summarize_mode = await _summarize_text_with_llm(dependency_text, plan.user_text)
            summary_text = _enforce_sentence_count(summary_raw, sentence_count)
            task_outputs[task.id] = {
                "kind": "llm",
                "summary_text": summary_text,
                "sentence_count": sentence_count,
                "mode": summarize_mode,
            }
            steps.append(
                AgentExecutionStep(
                    name=task.id,
                    status="success",
                    detail=f"llm_summary sentences={sentence_count} mode={summarize_mode}",
                )
            )
            continue

        return None

    final_summary = "Task 기반 오케스트레이션 실행을 완료했습니다."
    final_user_message = "요청하신 작업을 완료했습니다."
    artifacts: dict[str, str] = {}

    for output in task_outputs.values():
        if output.get("kind") != "tool":
            continue
        tool_result = output.get("tool_result") or {}
        page_url = _extract_page_url_from_tool_result(tool_result)
        if page_url:
            artifacts["created_page_url"] = page_url
            final_user_message = f"{final_user_message}\n- 생성 페이지: {page_url}"
        issue_url = _extract_linear_issue_url_from_tool_result(tool_result)
        if issue_url and issue_url != artifacts.get("linear_issue_url"):
            artifacts["linear_issue_url"] = issue_url
            final_user_message = f"{final_user_message}\n- 이슈 링크: {issue_url}"

    llm_outputs = [output for output in task_outputs.values() if output.get("kind") == "llm"]
    if llm_outputs:
        last_summary = str(llm_outputs[-1].get("summary_text") or "").strip()
        if last_summary:
            final_user_message = f"{final_user_message}\n\n[요약]\n{last_summary}"
            artifacts["summary_sentence_count"] = str(llm_outputs[-1].get("sentence_count") or 0)
            final_summary = "TOOL/LLM 작업 오케스트레이션을 완료했습니다."
    if validated_payloads:
        artifacts["validated_payloads_json"] = json.dumps(validated_payloads, ensure_ascii=False)

    return AgentExecutionResult(
        success=True,
        summary=final_summary,
        user_message=final_user_message,
        artifacts=artifacts,
        steps=steps,
    )


def _extract_output_title(user_text: str, default_title: str = "Metel 자동 요약 회의록") -> str:
    def _sanitize_title(raw: str) -> str:
        cleaned = raw.strip(" \"'`")
        cleaned = re.sub(r"[\"'`]+", "", cleaned).strip()
        cleaned = re.sub(r"\s*(페이지|문서)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+(로|으로)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned

    patterns = [
        r"(?i)요약(?:해서|하여)\s*(.+?)\s*로\s*(?:새로\s*)?(?:생성|만들)",
        r"(?i)(.+?)로\s*(?:새로\s*)?(?:생성|만들)",
        r"(?i)(.+?)을\s*(?:새로\s*)?(?:생성|만들)",
        r"(?i)(.+?)\s*(?:페이지|문서)\s*(?:로\s*)?(?:생성|만들)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text)
        if not match:
            continue
        candidate = _sanitize_title(match.group(1))
        candidate = re.sub(r"^(노션|notion)\s*", "", candidate, flags=re.IGNORECASE).strip()
        if "으로" in user_text and candidate.endswith("으"):
            candidate = candidate[:-1].strip()
        if candidate and len(candidate) <= 100:
            return candidate
    return default_title


def _extract_nested_create_request(user_text: str) -> tuple[str | None, str | None]:
    patterns = [
        r'(?i)(?:노션에서\s*)?(?P<parent>.+?)\s*페이지\s*(?:아래|밑에|하위에)\s*(?P<child>.+?)\s*페이지?\s*(?:를|을)?\s*(?:새로\s*)?(?:생성|만들|작성)(?:해줘|해주세요|하세요)?',
        r'(?i)(?:노션에서\s*)?(?P<parent>.+?)\s*아래\s*(?P<child>.+?)\s*페이지?\s*(?:를|을)?\s*(?:새로\s*)?(?:생성|만들|작성)(?:해줘|해주세요|하세요)?',
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text.strip())
        if not match:
            continue
        parent = match.group("parent").strip(" \"'`")
        child = match.group("child").strip(" \"'`")
        parent = re.sub(r"^(노션|notion)\s*", "", parent, flags=re.IGNORECASE).strip()
        child = re.sub(r"^(노션|notion)\s*", "", child, flags=re.IGNORECASE).strip()
        if parent and child:
            return parent, child[:100]
    return None, None


def _extract_target_page_title(user_text: str) -> str | None:
    patterns = [
        r"(?i)(?:노션에서\s*)?(.+?)의\s*(?:내용|본문)",
        r"(?i)(?:노션에서\s*)?(.+?)\s*페이지(?:의)?\s*(?:내용|본문)",
        r"(?i)(?:노션에서\s*)?(.+?)\s*(?:페이지)?\s*요약(?:해줘|해|해서|해봐)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text)
        if not match:
            continue
        candidate = match.group(1).strip(" \"'`")
        candidate = re.sub(r"^(노션|notion)\s*", "", candidate, flags=re.IGNORECASE).strip()
        if candidate:
            return candidate
    return None


def _extract_requested_page_titles(user_text: str) -> list[str]:
    # Prefer explicit quoted titles in multi-page requests.
    quoted = [item.strip() for item in re.findall(r'"([^"]+)"|\'([^\']+)\'', user_text) for item in item if item.strip()]
    if quoted:
        return quoted

    # Fallback: "<title1>, <title2> 페이지를 요약..."
    match = re.search(r"(?i)노션에서\s+(.+?)\s*페이지(?:를|를\s*요약|를\s*조회|를\s*출력|를\s*읽)", user_text)
    if not match:
        return []
    raw = match.group(1).strip()
    if not raw:
        return []
    parts = [part.strip(" \"'`") for part in re.split(r",| 그리고 | 및 | 와 | 과 ", raw) if part.strip()]
    return [part for part in parts if part]


def _extract_append_target_and_content(user_text: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", " ", (user_text or "").strip())
    text_for_parse = re.sub(r"https?://\S+", "", text).strip()
    match = re.search(
        r'(?is)(?:노션에서\s*)?(?P<title>.+?)\s*(?:페이지)?에\s*(?P<content>.+?)\s*(?:을|를)?\s*추가(?:해줘|해|해줘요|해주세요|하세요)?$',
        text_for_parse,
    )
    if match:
        title = re.sub(r"^(노션|notion)\s*", "", match.group("title").strip(" \"'`"), flags=re.IGNORECASE).strip()
        content = match.group("content").strip(" \"'`")
        if content.endswith(("을", "를")) and len(content) > 1:
            content = content[:-1].strip()
        if title and content:
            return title, content

    # content-first form:
    # "다음 기사 내용을 180자로 요약해서 0219 페이지에 추가해줘"
    match = re.search(
        r'(?is)(?:노션에서\s*)?(?P<content>.+?)\s*(?P<title>[^ ]+)\s*(?:페이지)?에\s*(?:을|를)?\s*추가(?:해줘|해|해줘요|해주세요|하세요)?$',
        text_for_parse,
    )
    if match:
        title = re.sub(r"^(노션|notion)\s*", "", match.group("title").strip(" \"'`"), flags=re.IGNORECASE).strip()
        content = match.group("content").strip(" \"'`")
        if title and content:
            return title, content
    return None, None


def _extract_move_request(user_text: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", " ", (user_text or "").strip())
    patterns = [
        r'(?is)(?:노션에서\s*)?(?P<source>.+?)\s*(?:페이지)?를\s*(?P<parent>.+?)(?:의)?\s*(?:하위\s*페이지|하위|아래|밑)\s*(?:로|에)\s*(?:이동|옮겨|옮기|이동시키)(?:주세요|세요|해줘|해주세요|하세요|해)?',
        r'(?is)(?:노션에서\s*)?(?P<source>.+?)\s*(?:페이지)?를\s*(?P<parent>.+?)\s*(?:페이지)?\s*(?:하위\s*페이지|하위|아래|밑)\s*(?:로|에)\s*(?:이동|옮겨|옮기|이동시키)(?:주세요|세요|해줘|해주세요|하세요|해)?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        source = re.sub(r"^(노션|notion)\s*", "", match.group("source").strip(" \"'`"), flags=re.IGNORECASE).strip()
        parent = re.sub(r"^(노션|notion)\s*", "", match.group("parent").strip(" \"'`"), flags=re.IGNORECASE).strip()
        parent = re.sub(r"(?:페이지)?의$", "", parent).strip()
        if source and parent:
            return source, parent
    return None, None


def _extract_page_rename_request(user_text: str) -> tuple[str | None, str | None]:
    patterns = [
        r'(?i)(?:노션에서\s*)?"?(?P<title>.+?)"?\s*(?:페이지)?\s*제목(?:을)?\s*"?(?P<new_title>.+?)"?\s*로\s*(?:변경|수정|바꿔줘|바꿔|바꾸고|바꾸|rename)',
        r'(?i)(?:노션에서\s*)?"?(?P<title>.+?)"?의\s*제목(?:을)?\s*"?(?P<new_title>.+?)"?\s*로\s*(?:변경|수정|바꿔줘|바꿔|바꾸고|바꾸|rename)',
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text.strip())
        if not match:
            continue
        title = match.group("title").strip(" \"'`")
        title = re.sub(r"^(노션|notion)\s*", "", title, flags=re.IGNORECASE).strip()
        new_title = match.group("new_title").strip(" \"'`")
        if "으로" in user_text and new_title.endswith("으"):
            new_title = new_title[:-1].strip()
        if title and new_title:
            return title, new_title[:100]
    return None, None


def _extract_data_source_query_request(user_text: str) -> tuple[str | None, int, str | None]:
    id_match = re.search(r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})", user_text)
    data_source_id = id_match.group(1) if id_match else None
    count_match = re.search(
        r"(?i)(?:최근|상위|top)?\s*(\d{1,2})\s*(개|건|items?)\b",
        user_text,
    )
    count = int(count_match.group(1)) if count_match else 5
    if data_source_id:
        return data_source_id, max(1, min(20, count)), None

    token_match = re.search(r"(?i)(?:데이터소스|data[_ ]source)\s+([^\s]+)", user_text)
    if not token_match:
        return None, max(1, min(20, count)), "missing"

    candidate = token_match.group(1).strip(" \"'`,.;:()[]{}")
    if not candidate or candidate in {"조회", "목록", "검색", "불러", "보여", "최근", "상위"}:
        return None, max(1, min(20, count)), "missing"
    return None, max(1, min(20, count)), "invalid"


def _extract_page_archive_target(user_text: str) -> str | None:
    patterns = [
        r"(?i)(?:노션에서\s*)?(?P<title>.+?)\s*(?:페이지)?\s*(?:를|을)?\s*(?:삭제|지워줘|지워|아카이브|archive)(?:해줘|해)?",
        r"(?i)(?:노션에서\s*)?(?P<title>.+?)의\s*(?:페이지)?\s*(?:삭제|아카이브)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text.strip())
        if not match:
            continue
        title = match.group("title").strip(" \"'`")
        title = re.sub(r"^(노션|notion)\s*", "", title, flags=re.IGNORECASE).strip()
        if title:
            return title
    return None


def _extract_requested_line_count(user_text: str, default_count: int = 10) -> int:
    match = re.search(r"(\d{1,2})\s*(줄|line|lines)", user_text, flags=re.IGNORECASE)
    if match:
        return max(1, min(50, int(match.group(1))))
    return default_count


def _requires_page_content_read(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(keyword in text for keyword in ("내용", "본문")) and any(
        keyword in text for keyword in ("출력", "보여", "조회", "읽어")
    )


def _requires_append_to_page(plan: AgentPlan) -> bool:
    text = plan.user_text
    return "추가" in text and any(token in text for token in ("페이지에", "에 "))


def _requires_move_page(plan: AgentPlan) -> bool:
    text = plan.user_text
    if not any(token in text for token in ("페이지", "문서")):
        return False
    return any(token in text for token in ("하위로 이동", "아래로 이동", "밑으로 이동", "옮겨", "이동시키"))


def _extract_summary_char_limit(user_text: str) -> int | None:
    match = re.search(r"(\d{2,4})\s*자", user_text)
    if not match:
        return None
    return max(50, min(1000, int(match.group(1))))


async def _fetch_url_plain_text(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "metel-bot/1.0"})
        if response.status_code >= 400:
            return None
        html = response.text
        html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:12000] if text else None
    except Exception:
        return None


def _requires_page_title_update(plan: AgentPlan) -> bool:
    text = plan.user_text
    return "제목" in text and any(keyword in text for keyword in ("변경", "수정", "바꿔", "바꾸", "rename"))


def _requires_data_source_query(plan: AgentPlan) -> bool:
    text = plan.user_text
    return any(keyword in text for keyword in ("데이터소스", "data source", "data_source")) and any(
        keyword in text for keyword in ("조회", "목록", "query", "불러", "보여", "요약", "정리")
    )


def _requires_page_archive(plan: AgentPlan) -> bool:
    text = plan.user_text.strip()
    lower = text.lower()
    if not any(keyword in lower for keyword in ("페이지", "문서", "노션", "notion")):
        return False

    # Do not treat noun usage like "삭제 테스트 페이지" as delete intent.
    # Require explicit deletion action phrase.
    delete_intent_patterns = [
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*삭제(?:해줘|해|해주세요)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*지워(?:줘|줘요|라|해줘|해)\b",
        r"(?i)(?:페이지|문서)?\s*(?:를|을)?\s*아카이브(?:해줘|해|해주세요)\b",
        r"(?i)\b페이지\s*삭제\b",
        r"(?i)\barchive\b",
    ]
    return any(re.search(pattern, text) for pattern in delete_intent_patterns)


async def _notion_append_summary_blocks(user_id: str, plan: AgentPlan, page_id: str, markdown: str) -> None:
    chunks = [line for line in markdown.splitlines() if line.strip()]
    paragraphs = []
    for line in chunks[:30]:
        paragraphs.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": line[:1800]},
                        }
                    ]
                },
            }
        )
    if not paragraphs:
        return

    await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "append_block_children", "notion_append_block_children"),
        payload={
            "block_id": page_id,
            "children": paragraphs,
        },
    )


def _requires_summary(plan: AgentPlan) -> bool:
    return any("요약" in req.summary for req in plan.requirements) or is_summary_intent(plan.user_text)


def _extract_spotify_recent_track_count(user_text: str, default_count: int = 10) -> int:
    match = re.search(r"(\d{1,2})\s*(곡|트랙|개|songs?|tracks?)", user_text, flags=re.IGNORECASE)
    if not match:
        return default_count
    return max(1, min(50, int(match.group(1))))


def _extract_spotify_output_page_title(user_text: str, default_title: str = "spotify10") -> str:
    text = re.sub(r"\s+", " ", user_text.strip())
    patterns = [
        r'(?i)노션에\s+"(?P<title>[^"]+)"\s*(?:새로운|새로|new)?\s*페이지',
        r"(?i)노션에\s+'(?P<title>[^']+)'\s*(?:새로운|새로|new)?\s*페이지",
        r"(?i)노션에\s+(?P<title>[^\s]+)\s*(?:새로운|새로|new)?\s*페이지",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        title = match.group("title").strip(" \"'`")
        if title:
            return title[:100]
    return default_title


def _extract_linear_search_query(user_text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', user_text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    korean_front_match = re.search(
        r"(?i)(?:linear|리니어)(?:에서)?\s+(.+?)\s*(?:의)?\s*이슈(?:를)?\s*(?:검색|search)",
        user_text.strip(),
    )
    if korean_front_match:
        candidate = korean_front_match.group(1).strip(" \"'`")
        if candidate:
            return candidate
    match = re.search(r"(?i)(?:linear|리니어).*(?:검색|search)\s+(.+)$", user_text.strip())
    if not match:
        return None
    candidate = match.group(1).strip(" \"'`")
    return candidate or None


def _extract_linear_issue_reference(user_text: str) -> str | None:
    keyed = re.search(r"(?i)(?:issue_id|issueid|이슈ID|이슈_id)\s*[:=]?\s*([^\s,]+)", user_text.strip())
    if keyed:
        value = keyed.group(1).strip(" \"'`,.;:()[]{}")
        if value:
            return value
    # Title/reference form: "이슈: 구글로그인 구현" / "issue: login"
    title_like = re.search(
        r"(?i)(?:이슈|issue)\s*[:：]\s*(.+?)(?:\s+(?:설명|description|본문|내용|제목|title|상태|state_id)\s*[:：]|$)",
        user_text.strip(),
    )
    if title_like:
        value = title_like.group(1).strip(" \"'`,.;:()[]{}")
        if value:
            return value
    uuid_like = re.search(r"([0-9a-fA-F]{8,}-[0-9a-fA-F-]{8,})", user_text)
    if uuid_like:
        return uuid_like.group(1).strip()
    identifier_like = re.search(r"\b([A-Za-z]{2,10}-\d{1,6})\b", user_text)
    if identifier_like:
        return identifier_like.group(1).strip()
    return None


def _looks_like_linear_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{2,10}-\d{1,6}", (value or "").strip()))


def _looks_like_linear_internal_issue_id(value: str) -> bool:
    normalized = (value or "").strip()
    return bool(re.fullmatch(r"[0-9a-fA-F]{8,}-[0-9a-fA-F-]{8,}", normalized))


async def _resolve_linear_issue_id_from_reference(
    *,
    user_id: str,
    plan: AgentPlan,
    issue_reference: str,
    steps: list[AgentExecutionStep],
    step_name: str,
) -> str:
    ref = (issue_reference or "").strip()
    if not ref:
        return ""
    # Internal id (UUID-like) can be used as-is.
    if re.fullmatch(r"[0-9a-fA-F]{8,}-[0-9a-fA-F-]{8,}", ref):
        return ref

    # Resolve identifier/key/name via search.
    nodes: list[dict] = []
    search_failed = False
    try:
        result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "linear_search_issues", "linear_search_issues"),
            payload={"query": ref, "first": 20},
        )
        nodes = (((result.get("data") or {}).get("issues") or {}).get("nodes") or [])
        steps.append(AgentExecutionStep(name=step_name, status="success", detail=f"count={len(nodes)}"))
    except HTTPException as exc:
        search_failed = True
        steps.append(AgentExecutionStep(name=step_name, status="error", detail=str(exc.detail)))

    if _looks_like_linear_identifier(ref):
        # Fallback for environments where search filter may not match identifier directly.
        listed = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "linear_list_issues", "linear_list_issues"),
            payload={"first": 20},
        )
        nodes = (((listed.get("data") or {}).get("issues") or {}).get("nodes") or [])
        steps.append(
            AgentExecutionStep(
                name=f"{step_name}_fallback_list",
                status="success",
                detail=f"count={len(nodes)}",
            )
        )
    ref_lower = ref.lower()
    for node in nodes:
        issue_id = str(node.get("id") or "").strip()
        identifier = str(node.get("identifier") or "").strip().lower()
        title = str(node.get("title") or "").strip().lower()
        if not issue_id:
            continue
        if ref_lower in {identifier, issue_id.lower(), title}:
            return issue_id
    for node in nodes:
        issue_id = str(node.get("id") or "").strip()
        identifier = str(node.get("identifier") or "").strip().lower()
        title = str(node.get("title") or "").strip().lower()
        if not issue_id:
            continue
        if ref_lower in identifier or ref_lower in title:
            return issue_id
    return ""


def _extract_linear_comment_body(user_text: str) -> str | None:
    patterns = [
        r'(?is)(?:댓글|코멘트|comment)\s*(?:내용)?\s*[:：]\s*(.+)$',
        r'(?is)(?:댓글|코멘트|comment)\s*(?:을|를)?\s*(?:생성|추가|작성)\s*[:：]?\s*(.+)$',
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text.strip())
        if not match:
            continue
        body = match.group(1).strip(" \"'`")
        if body:
            return body
    return None


def _extract_linear_update_fields(user_text: str) -> dict:
    fields: dict[str, str] = {}
    title_match = re.search(r'(?i)(?:제목|title)\s*[:：]\s*(.+?)(?:\s+(?:설명|description|본문|내용|상태|state_id)\s*[:：]|$)', user_text)
    if title_match:
        fields["title"] = title_match.group(1).strip(" \"'`")
    description_match = re.search(r'(?i)(?:설명|description|본문|내용)\s*[:：]\s*(.+?)(?:\s+(?:제목|title|상태|state_id)\s*[:：]|$)', user_text)
    if description_match:
        fields["description"] = description_match.group(1).strip(" \"'`")
    state_match = re.search(r'(?i)(?:상태|state_id)\s*[:：]\s*([0-9a-fA-F\-]{8,})', user_text)
    if state_match:
        fields["state_id"] = state_match.group(1).strip()
    return {k: v for k, v in fields.items() if v}


def _extract_notion_page_title_from_reference(text: str) -> str | None:
    raw = (text or "").strip()
    patterns = [
        r"(?i)(?:notion|노션)(?:의|에서)?\s*(.+?)\s*페이지(?:의)?\s*(?:내용|본문)",
        r"(?i)(?:notion|노션)(?:의|에서)?\s*(.+?)\s*페이지",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if not match:
            continue
        title = match.group(1).strip(" \"'`")
        title = re.sub(r"^(노션|notion)\s*", "", title, flags=re.IGNORECASE).strip()
        if title:
            return title
    return None


def _description_requests_notion_page_content(description: str) -> bool:
    text = (description or "").lower()
    has_notion = ("notion" in text) or ("노션" in text)
    has_page = ("페이지" in text) or ("page" in text)
    has_content = ("내용" in text) or ("본문" in text) or ("content" in text)
    return has_notion and has_page and has_content


def _extract_linear_issue_reference_for_update(user_text: str) -> str | None:
    explicit = _extract_linear_issue_reference(user_text)
    if explicit:
        return explicit
    match = re.search(r"(?i)(?:linear|리니어)(?:의|에서)?\s*(.+?)\s*이슈", user_text.strip())
    if not match:
        return None
    candidate = match.group(1).strip(" \"'`,.;:()[]{}")
    return candidate or None


def _pick_best_notion_page_by_title(pages: list[dict], title: str) -> dict | None:
    normalized_target = _normalize_title(title)
    if not normalized_target:
        return None
    normalized_pages = [
        {
            "id": page.get("id"),
            "title": _extract_page_title(page),
            "url": page.get("url"),
        }
        for page in pages
        if isinstance(page, dict) and page.get("id")
    ]
    for page in normalized_pages:
        if _normalize_title(page["title"]) == normalized_target:
            return page
    for page in normalized_pages:
        if normalized_target in _normalize_title(page["title"]):
            return page
    return normalized_pages[0] if normalized_pages else None


def _extract_copy_request(plan: AgentPlan) -> CopyRequest | None:
    text = (plan.user_text or "").strip()
    lower = text.lower()
    has_notion = ("notion" in lower) or ("노션" in text)
    has_linear = ("linear" in lower) or ("리니어" in text)
    if not (has_notion and has_linear):
        return None
    if not contains_any(text, ("설명", "디스크립션", "description")):
        return None
    source_ref = _extract_notion_page_title_from_reference(text) or _extract_target_page_title(text)
    target_ref = _extract_linear_issue_reference_for_update(text)
    if not source_ref or not target_ref:
        return None
    return CopyRequest(
        source_service="notion",
        source_ref=source_ref,
        target_service="linear",
        target_ref=target_ref,
        target_field="description",
    )


async def _copy_read_from_notion(
    *,
    user_id: str,
    plan: AgentPlan,
    source_ref: str,
    steps: list[AgentExecutionStep],
) -> tuple[str | None, str | None]:
    search_result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_service_tool(plan, "notion", "search", "notion_search"),
        payload={"query": source_ref, "page_size": 10},
    )
    pages = ((search_result.get("data") or {}).get("results") or [])
    steps.append(AgentExecutionStep(name="copy_read_notion_search", status="success", detail=f"count={len(pages)}"))
    selected_page = _pick_best_notion_page_by_title(pages, source_ref)
    if not selected_page:
        return None, "copy_source_not_found"

    block_result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_service_tool(plan, "notion", "retrieve_block_children", "notion_retrieve_block_children"),
        payload={"block_id": selected_page["id"], "page_size": 50},
    )
    blocks = (block_result.get("data") or {}).get("results", [])
    steps.append(AgentExecutionStep(name="copy_read_notion_blocks", status="success", detail=f"blocks={len(blocks)}"))
    plain = _extract_plain_text_from_blocks(blocks).strip()
    if not plain:
        return None, "copy_source_empty"
    return plain[:12000], None


async def _copy_write_to_linear_description(
    *,
    user_id: str,
    plan: AgentPlan,
    target_ref: str,
    content: str,
    steps: list[AgentExecutionStep],
) -> tuple[dict | None, str | None]:
    issue_id = await _resolve_linear_issue_id_from_reference(
        user_id=user_id,
        plan=plan,
        issue_reference=target_ref,
        steps=steps,
        step_name="copy_target_linear_issue_search",
    )
    if not issue_id:
        return None, "copy_target_not_found"

    updated = await execute_tool(
        user_id=user_id,
        tool_name=_pick_service_tool(plan, "linear", "update_issue", "linear_update_issue"),
        payload={"issue_id": issue_id, "description": content},
    )
    issue = ((updated.get("data") or {}).get("issueUpdate") or {}).get("issue") or {}
    steps.append(AgentExecutionStep(name="copy_target_linear_update", status="success", detail=f"id={issue.get('id')}"))
    return issue, None


async def _execute_cross_service_copy_flow(user_id: str, plan: AgentPlan) -> AgentExecutionResult | None:
    request = _extract_copy_request(plan)
    if not request:
        return None

    steps: list[AgentExecutionStep] = [AgentExecutionStep(name="copy_pipeline_init", status="success", detail="notion->linear")]
    content, read_err = await _copy_read_from_notion(
        user_id=user_id,
        plan=plan,
        source_ref=request.source_ref,
        steps=steps,
    )
    if read_err or not content:
        return AgentExecutionResult(
            success=False,
            summary="서비스간 복사 소스 조회에 실패했습니다.",
            user_message="Notion 페이지 본문을 찾지 못했습니다. 페이지 제목을 더 구체적으로 입력해주세요.",
            artifacts={"error_code": "validation_error"},
            steps=steps + [AgentExecutionStep(name="copy_pipeline_read", status="error", detail=read_err or "copy_source_empty")],
        )

    issue, write_err = await _copy_write_to_linear_description(
        user_id=user_id,
        plan=plan,
        target_ref=request.target_ref,
        content=content,
        steps=steps,
    )
    if write_err or not issue:
        return AgentExecutionResult(
            success=False,
            summary="서비스간 복사 타겟 업데이트에 실패했습니다.",
            user_message="Linear 이슈를 찾지 못했거나 설명 업데이트에 실패했습니다. 이슈 제목/식별자를 확인해주세요.",
            artifacts={"error_code": "validation_error"},
            steps=steps + [AgentExecutionStep(name="copy_pipeline_write", status="error", detail=write_err or "copy_target_update_failed")],
        )

    return AgentExecutionResult(
        success=True,
        summary="Notion 본문을 Linear 이슈 설명으로 복사했습니다.",
        user_message=(
            "요청하신 서비스간 복사를 완료했습니다.\n"
            f"- Linear 이슈: {issue.get('identifier') or '-'}\n"
            f"- 제목: {issue.get('title') or '-'}\n"
            f"- 링크: {issue.get('url') or '-'}"
        ),
        artifacts={"updated_issue_id": issue.get("id") or "", "updated_issue_url": issue.get("url") or ""},
        steps=steps,
    )


async def _resolve_linear_update_description_from_notion(
    *,
    user_id: str,
    plan: AgentPlan,
    raw_description: str,
    steps: list[AgentExecutionStep],
) -> tuple[str | None, str | None]:
    if not _description_requests_notion_page_content(raw_description):
        return raw_description, None

    notion_title = _extract_notion_page_title_from_reference(raw_description) or _extract_target_page_title(plan.user_text)
    if not notion_title:
        return None, "missing_notion_page_title_for_description"

    search_result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_service_tool(plan, "notion", "search", "notion_search"),
        payload={"query": notion_title, "page_size": 10},
    )
    pages = ((search_result.get("data") or {}).get("results") or [])
    steps.append(AgentExecutionStep(name="notion_search_for_linear_description", status="success", detail=f"count={len(pages)}"))
    selected_page = _pick_best_notion_page_by_title(pages, notion_title)
    if not selected_page:
        return None, "notion_page_not_found_for_description"

    block_result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_service_tool(plan, "notion", "retrieve_block_children", "notion_retrieve_block_children"),
        payload={"block_id": selected_page["id"], "page_size": 50},
    )
    blocks = (block_result.get("data") or {}).get("results", [])
    steps.append(
        AgentExecutionStep(
            name="notion_retrieve_block_children_for_linear_description",
            status="success",
            detail=f"blocks={len(blocks)}",
        )
    )
    plain = _extract_plain_text_from_blocks(blocks).strip()
    if not plain:
        return None, "notion_page_content_empty_for_description"
    # Keep under a conservative limit for update payload.
    return plain[:12000], None


def _extract_linear_team_reference(user_text: str) -> str | None:
    patterns = [
        r"(?i)(?:team_id|teamid|team|팀(?:_id)?)\s*[:=]?\s*([^\s,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_text.strip())
        if not match:
            continue
        ref = match.group(1).strip(" \"'`")
        if ref:
            return ref
    return None


def _looks_like_linear_team_id(value: str) -> bool:
    normalized = (value or "").strip()
    # Linear IDs are opaque; accept UUID-like values or long id-like tokens.
    return bool(re.fullmatch(r"[0-9a-fA-F\-]{8,}", normalized))


async def _resolve_linear_team_id_from_reference(
    *,
    user_id: str,
    plan: AgentPlan,
    team_reference: str,
    steps: list[AgentExecutionStep],
) -> str:
    ref = (team_reference or "").strip()
    if not ref:
        return ""
    if _looks_like_linear_team_id(ref):
        return ref

    result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "linear_list_teams", "linear_list_teams"),
        payload={"first": 20},
    )
    nodes = (((result.get("data") or {}).get("teams") or {}).get("nodes") or [])
    steps.append(AgentExecutionStep(name="linear_list_teams_for_create", status="success", detail=f"count={len(nodes)}"))
    ref_lower = ref.lower()
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        key = str(node.get("key") or "").strip()
        name = str(node.get("name") or "").strip()
        if not node_id:
            continue
        if ref_lower in {node_id.lower(), key.lower(), name.lower()}:
            return node_id
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        key = str(node.get("key") or "").strip().lower()
        name = str(node.get("name") or "").strip().lower()
        if not node_id:
            continue
        if ref_lower in key or ref_lower in name:
            return node_id
    return ""


async def _execute_linear_plan(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    return AgentExecutionResult(
        success=False,
        summary="legacy_linear_executor_removed",
        user_message="레거시 Linear 실행기는 제거되었습니다.",
        artifacts={"error_code": "legacy_executor_removed"},
        steps=[AgentExecutionStep(name="legacy_linear_executor", status="error", detail="removed")],
    )


async def _execute_spotify_recent_tracks_to_notion(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    steps: list[AgentExecutionStep] = []
    steps.append(AgentExecutionStep(name="tool_runner_init", status="success", detail="Spotify+Notion Tool Runner 준비 완료"))

    track_count = _extract_spotify_recent_track_count(plan.user_text, default_count=10)
    output_title = _extract_spotify_output_page_title(plan.user_text, default_title=f"spotify{track_count}")

    recent = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "recently_played", "spotify_get_recently_played"),
        payload={"limit": track_count},
    )
    items = (recent.get("data") or {}).get("items", [])
    steps.append(AgentExecutionStep(name="spotify_recently_played", status="success", detail=f"items={len(items)}"))
    if not items:
        return AgentExecutionResult(
            success=False,
            summary="최근 재생곡을 찾지 못했습니다.",
            user_message="Spotify 최근 재생 기록이 없습니다. 최근 재생 후 다시 시도해주세요.",
            steps=steps,
        )

    tracks: list[tuple[str, str, str]] = []
    seen = set()
    for item in items:
        track = (item or {}).get("track") or {}
        track_name = (track.get("name") or "").strip()
        if not track_name:
            continue
        artists = [artist.get("name", "").strip() for artist in (track.get("artists") or []) if artist.get("name")]
        artist_name = ", ".join(artists) if artists else "Unknown Artist"
        external_url = (((track.get("external_urls") or {}).get("spotify")) or "").strip()
        key = (track_name.lower(), artist_name.lower())
        if key in seen:
            continue
        seen.add(key)
        tracks.append((track_name, artist_name, external_url))
        if len(tracks) >= track_count:
            break

    if not tracks:
        return AgentExecutionResult(
            success=False,
            summary="최근 재생 트랙 정보를 추출하지 못했습니다.",
            user_message="Spotify 최근 재생 트랙 이름을 추출하지 못했습니다. 잠시 후 다시 시도해주세요.",
            steps=steps,
        )

    create = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "create_page", "notion_create_page"),
        payload={
            "parent": _notion_create_parent_payload(),
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": output_title[:100]}}],
                }
            },
        },
    )
    page = create.get("data") or {}
    page_id = page.get("id")
    page_url = page.get("url")
    steps.append(AgentExecutionStep(name="create_page", status="success", detail=f"title={output_title}"))

    if page_id:
        lines: list[str] = [
            "Spotify recently played tracks",
            f"Collected count: {len(tracks)}",
            f"Generated at: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for idx, (track_name, artist_name, external_url) in enumerate(tracks, start=1):
            line = f"{idx}. {track_name} — {artist_name}"
            if external_url:
                line = f"{line} ({external_url})"
            lines.append(line)
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:1800]}}]},
            }
            for line in lines
            if line.strip()
        ][:80]
        await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "append_block_children", "notion_append_block_children"),
            payload={"block_id": page_id, "children": children},
        )
        steps.append(AgentExecutionStep(name="append_content", status="success", detail=f"blocks={len(children)}"))

    return AgentExecutionResult(
        success=True,
        summary="최근 재생곡 목록 Notion 페이지 생성을 완료했습니다.",
        user_message=(
            "Spotify 최근 재생곡 목록 페이지를 Notion에 생성했습니다.\n"
            f"- 요청 개수: {track_count}\n"
            f"- 반영 개수: {len(tracks)}\n"
            f"- 페이지 제목: {output_title}\n"
            f"- 페이지 링크: {page_url or '-'}"
        ),
        artifacts={
            "track_count": str(len(tracks)),
            "created_page_title": output_title,
            "created_page_url": page_url or "",
        },
        steps=steps,
    )


def _requires_creation(plan: AgentPlan) -> bool:
    if _requires_append_to_page(plan):
        return False
    return any("생성" in req.summary for req in plan.requirements) or is_create_intent(plan.user_text)


def _requires_top_lines(plan: AgentPlan) -> bool:
    text = plan.user_text
    return (
        any(keyword in text for keyword in ("상위", "줄", "line", "lines"))
        and any(keyword in text for keyword in ("내용", "본문", "출력", "보여", "조회"))
    )


def _requires_summary_only(plan: AgentPlan) -> bool:
    return _requires_summary(plan) and not _requires_creation(plan)


def _pick_tool(plan: AgentPlan, keyword: str, default_tool: str) -> str:
    for tool in plan.selected_tools:
        if keyword in tool:
            return tool
    return default_tool


def _pick_service_tool(plan: AgentPlan, service: str, keyword: str, default_tool: str) -> str:
    normalized = f"{service.lower()}_"
    for tool in plan.selected_tools:
        if tool.startswith(normalized) and keyword in tool:
            return tool
    return default_tool


def _pick_tool_or_none(plan: AgentPlan, keyword: str) -> str | None:
    for tool in plan.selected_tools:
        if keyword in tool:
            return tool
    return None


def _is_valid_notion_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F\-]{36}", value.strip()))


def _notion_create_parent_payload() -> dict:
    settings = get_settings()
    parent_page_id = (settings.notion_default_parent_page_id or "").strip()
    if parent_page_id:
        return {"page_id": parent_page_id}
    return {"workspace": True}


async def _read_page_lines_or_summary(
    *,
    user_id: str,
    plan: AgentPlan,
    steps: list[AgentExecutionStep],
    selected_page: dict,
) -> AgentExecutionResult:
    _ = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "retrieve_page", "notion_retrieve_page"),
        payload={"page_id": selected_page["id"]},
    )
    steps.append(AgentExecutionStep(name="retrieve_page", status="success", detail="페이지 메타데이터 조회 완료"))

    block_result = await execute_tool(
        user_id=user_id,
        tool_name=_pick_tool(plan, "retrieve_block_children", "notion_retrieve_block_children"),
        payload={"block_id": selected_page["id"], "page_size": 20},
    )
    blocks = (block_result.get("data") or {}).get("results", [])
    plain = _extract_plain_text_from_blocks(blocks)
    raw_lines = [line.strip() for line in plain.splitlines() if line.strip()]
    line_count = _extract_requested_line_count(plan.user_text, default_count=10)
    top_lines = raw_lines[:line_count]

    if not raw_lines:
        return AgentExecutionResult(
            success=False,
            summary="페이지 본문 텍스트를 찾지 못했습니다.",
            user_message=(
                f"'{selected_page['title']}' 페이지에서 텍스트 블록을 찾지 못했습니다.\n"
                f"페이지 링크: {selected_page['url']}"
            ),
            artifacts={"source_page_url": selected_page["url"]},
            steps=steps,
        )

    if _requires_summary_only(plan):
        summary, summarize_mode = await _summarize_text_with_llm("\n".join(raw_lines), plan.user_text)
        steps.append(
            AgentExecutionStep(
                name="summarize_page",
                status="success",
                detail=f"본문 {len(raw_lines)}라인 요약 ({summarize_mode})",
            )
        )
        return AgentExecutionResult(
            success=True,
            summary="요청한 특정 페이지 요약을 완료했습니다.",
            user_message=(
                f"요청하신 페이지 요약입니다.\n"
                f"- 페이지: {selected_page['title']}\n"
                f"- 링크: {selected_page['url']}\n\n"
                f"{summary}"
            ),
            artifacts={"source_page_url": selected_page["url"], "source_page_title": selected_page["title"]},
            steps=steps,
        )

    steps.append(
        AgentExecutionStep(
            name="extract_lines",
            status="success",
            detail=f"본문 라인 {len(raw_lines)}개 중 상위 {len(top_lines)}개 추출",
        )
    )
    output_lines = [f"{idx}. {line}" for idx, line in enumerate(top_lines, start=1)]
    return AgentExecutionResult(
        success=True,
        summary="요청한 페이지 상위 라인 추출을 완료했습니다.",
        user_message=(
            f"요청하신 페이지 상위 {len(top_lines)}줄입니다.\n"
            f"- 페이지: {selected_page['title']}\n"
            f"- 링크: {selected_page['url']}\n\n"
            + "\n".join(output_lines)
        ),
        artifacts={"source_page_url": selected_page["url"], "source_page_title": selected_page["title"]},
        steps=steps,
    )


async def _execute_notion_plan(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    return AgentExecutionResult(
        success=False,
        summary="legacy_notion_executor_removed",
        user_message="레거시 Notion 실행기는 제거되었습니다.",
        artifacts={"error_code": "legacy_executor_removed"},
        steps=[AgentExecutionStep(name="legacy_notion_executor", status="error", detail="removed")],
    )


async def execute_agent_plan(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    try:
        plan = _ensure_common_tool_tasks(plan)
        cross_copy_result = await _execute_cross_service_copy_flow(user_id=user_id, plan=plan)
        if cross_copy_result is not None:
            return cross_copy_result
        task_orchestration_result = await _execute_task_orchestration(user_id=user_id, plan=plan)
        if task_orchestration_result is not None:
            return task_orchestration_result
        return AgentExecutionResult(
            success=False,
            summary="작업 계획 실행 경로를 확정하지 못했습니다.",
            user_message="요청을 실행하기 위한 작업 계획 검증에 실패했습니다. 다시 시도해주세요.",
            artifacts={"error_code": "task_orchestration_unavailable"},
            steps=[AgentExecutionStep(name="task_orchestration", status="error", detail="no_executable_task_graph")],
        )
    except HTTPException as exc:
        summary, user_message, error_code = _map_execution_error(str(exc.detail))
        return AgentExecutionResult(
            success=False,
            summary=summary,
            user_message=user_message,
            artifacts={"error_code": error_code},
            steps=[AgentExecutionStep(name="execution", status="error", detail=str(exc.detail))],
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return AgentExecutionResult(
            success=False,
            summary=f"예상치 못한 오류: {exc}",
            user_message="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            steps=[AgentExecutionStep(name="execution", status="error", detail="internal_error")],
        )
