from __future__ import annotations

import re
from html import unescape
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan
from app.core.config import get_settings


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def _map_execution_error(detail: str) -> tuple[str, str, str]:
    code = detail or "unknown_error"
    lower = code.lower()

    if "notion_not_connected" in lower:
        return (
            "Notion 연결이 필요합니다.",
            "Notion이 연결되어 있지 않습니다. 대시보드에서 Notion 연동 후 다시 시도해주세요.",
            "notion_not_connected",
        )
    if "token_missing" in lower:
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
        return (
            "요청 형식이 올바르지 않습니다.",
            "요청 파라미터가 올바르지 않습니다. 제목/개수/ID 형식을 확인해주세요.",
            "validation_error",
        )
    if "tool_failed" in lower or "notion_api_failed" in lower or "notion_parse_failed" in lower:
        return (
            "외부 서비스 처리 중 오류가 발생했습니다.",
            "외부 서비스 응답 처리에 실패했습니다. 잠시 후 다시 시도해주세요.",
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
    lines = lines[:requested_lines]
    return "\n".join(f"{idx}. {line}" for idx, line in enumerate(lines, start=1))


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
        try:
            summary = await _request_summary_with_provider(
                provider=provider,
                model=model,
                text=text,
                line_count=line_count,
                openai_api_key=settings.openai_api_key,
                google_api_key=settings.google_api_key,
            )
            if summary:
                return _format_summary_output(summary, line_count), f"llm:{provider}:{model}"
        except Exception:
            continue

    fallback = _simple_korean_summary(text, max_chars=700)
    return _format_summary_output(fallback, line_count), "fallback"


def _extract_requested_count(plan: AgentPlan, default_count: int = 3) -> int:
    for req in plan.requirements:
        if req.quantity and req.quantity > 0:
            return max(1, min(10, req.quantity))
    return default_count


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
        r'(?is)(?:노션에서\s*)?(?P<source>.+?)\s*(?:페이지)?를\s*(?P<parent>.+?)\s*(?:페이지)?\s*(?:하위|아래|밑)\s*로\s*(?:이동|옮겨|옮기)(?:해줘|해주세요|하세요)?',
        r'(?is)(?:노션에서\s*)?(?P<source>.+?)\s*(?:페이지)?를\s*(?P<parent>.+?)\s*(?:페이지)?\s*(?:하위|아래|밑)에\s*(?:이동|옮겨|옮기)(?:해줘|해주세요|하세요)?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        source = re.sub(r"^(노션|notion)\s*", "", match.group("source").strip(" \"'`"), flags=re.IGNORECASE).strip()
        parent = re.sub(r"^(노션|notion)\s*", "", match.group("parent").strip(" \"'`"), flags=re.IGNORECASE).strip()
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
        keyword in text for keyword in ("조회", "목록", "query", "불러", "보여")
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
    return any("요약" in req.summary for req in plan.requirements) or "요약" in plan.user_text


def _requires_creation(plan: AgentPlan) -> bool:
    if _requires_append_to_page(plan):
        return False
    return any("생성" in req.summary for req in plan.requirements) or any(
        keyword in plan.user_text for keyword in ("생성", "만들", "작성", "create")
    )


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
    steps: list[AgentExecutionStep] = []
    steps.append(AgentExecutionStep(name="tool_runner_init", status="success", detail="Notion Tool Runner 준비 완료"))

    normalized_pages: list[dict] = []

    if _requires_page_title_update(plan):
        target_title, new_title = _extract_page_rename_request(plan.user_text)
        if not target_title or not new_title:
            return AgentExecutionResult(
                success=False,
                summary="페이지 제목 변경 요청 파싱에 실패했습니다.",
                user_message=(
                    "제목 변경 요청을 이해하지 못했습니다.\n"
                    "예: '노션에서 Metel test page 페이지 제목을 주간 회의록으로 변경'"
                ),
                steps=steps + [AgentExecutionStep(name="parse_rename", status="error", detail="invalid_format")],
            )

        search_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": target_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        raw_pages = (search_result.get("data") or {}).get("results", [])
        normalized_pages = [
            {
                "id": page.get("id"),
                "title": _extract_page_title(page),
                "url": page.get("url"),
                "parent_type": ((page.get("parent") or {}).get("type") or ""),
            }
            for page in raw_pages
        ]
        if not normalized_pages:
            return AgentExecutionResult(
                success=False,
                summary="제목 변경 대상 페이지를 찾지 못했습니다.",
                user_message=f"'{target_title}' 페이지를 찾지 못했습니다.",
                steps=steps + [AgentExecutionStep(name="search_pages", status="error", detail="page_not_found")],
            )
        normalized_target = _normalize_title(target_title)
        selected_page = next(
            (page for page in normalized_pages if _normalize_title(page["title"]) == normalized_target),
            None,
        ) or next(
            (page for page in normalized_pages if normalized_target in _normalize_title(page["title"])),
            normalized_pages[0],
        )
        steps.append(AgentExecutionStep(name="select_page", status="success", detail=f"선택 페이지: {selected_page['title']}"))

        await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "update_page", "notion_update_page"),
            payload={
                "page_id": selected_page["id"],
                "properties": {
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": new_title},
                            }
                        ]
                    }
                },
            },
        )
        old_title = selected_page["title"]
        steps.append(AgentExecutionStep(name="update_page", status="success", detail=f"새 제목: {new_title}"))

        # Compound intent: rename + then read lines/summary from the same page.
        if _requires_top_lines(plan) or _requires_page_content_read(plan) or _requires_summary_only(plan):
            selected_page = dict(selected_page)
            selected_page["title"] = new_title
            content_result = await _read_page_lines_or_summary(
                user_id=user_id,
                plan=plan,
                steps=steps,
                selected_page=selected_page,
            )
            if content_result.success:
                content_result.summary = "페이지 제목 변경 및 본문 조회를 완료했습니다."
                content_result.user_message = (
                    "요청하신 페이지 제목을 먼저 변경한 뒤 본문을 조회했습니다.\n"
                    f"- 이전 제목: {old_title}\n"
                    f"- 새 제목: {new_title}\n"
                    f"- 페이지 링크: {selected_page['url']}\n\n"
                    f"{content_result.user_message}"
                )
                content_result.artifacts["new_title"] = new_title
            return content_result

        return AgentExecutionResult(
            success=True,
            summary="페이지 제목 변경을 완료했습니다.",
            user_message=(
                "요청하신 페이지 제목을 변경했습니다.\n"
                f"- 이전 제목: {selected_page['title']}\n"
                f"- 새 제목: {new_title}\n"
                f"- 페이지 링크: {selected_page['url']}"
            ),
            artifacts={"source_page_url": selected_page["url"], "new_title": new_title},
            steps=steps,
        )

    if _requires_data_source_query(plan):
        data_source_id, page_size, parse_error = _extract_data_source_query_request(plan.user_text)
        if not data_source_id and parse_error == "missing":
            return AgentExecutionResult(
                success=False,
                summary="데이터소스 ID를 찾지 못했습니다.",
                user_message=(
                    "데이터소스 조회를 위해 ID가 필요합니다.\n"
                    "예: '노션 데이터소스 <id> 최근 5개 조회'"
                ),
                artifacts={"error_code": "validation_error"},
                steps=steps + [AgentExecutionStep(name="parse_data_source_id", status="error", detail="id_missing")],
            )
        if not data_source_id and parse_error == "invalid":
            return AgentExecutionResult(
                success=False,
                summary="데이터소스 ID 형식이 올바르지 않습니다.",
                user_message=(
                    "데이터소스 ID 형식이 올바르지 않습니다.\n"
                    "UUID 형식으로 입력해주세요.\n"
                    "예: '노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 5개 조회'"
                ),
                artifacts={"error_code": "validation_error"},
                steps=steps + [AgentExecutionStep(name="parse_data_source_id", status="error", detail="id_invalid_format")],
            )
        query_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "query_data_source", "notion_query_data_source"),
            payload={
                "data_source_id": data_source_id,
                "page_size": page_size,
            },
        )
        results = (query_result.get("data") or {}).get("results", [])
        steps.append(
            AgentExecutionStep(
                name="query_data_source",
                status="success",
                detail=f"data_source={data_source_id}, count={len(results)}",
            )
        )
        if not results:
            return AgentExecutionResult(
                success=True,
                summary="데이터소스 조회는 성공했지만 결과가 비어 있습니다.",
                user_message=f"데이터소스 `{data_source_id}` 조회 결과가 없습니다.",
                steps=steps,
            )
        lines = ["데이터소스 조회 결과:"]
        for idx, item in enumerate(results[:page_size], start=1):
            lines.append(f"{idx}. {_extract_page_title(item)}")
            if item.get("url"):
                lines.append(f"   {item['url']}")
        return AgentExecutionResult(
            success=True,
            summary="데이터소스 조회를 완료했습니다.",
            user_message="\n".join(lines),
            steps=steps,
        )

    if _requires_move_page(plan):
        source_title, parent_title = _extract_move_request(plan.user_text)
        if not source_title or not parent_title:
            return AgentExecutionResult(
                success=False,
                summary="이동 요청 파싱에 실패했습니다.",
                user_message=(
                    "이동할 원본/상위 페이지 제목을 이해하지 못했습니다.\n"
                    "예: '0219 페이지를 Metel test page 페이지 하위로 이동시키세요'"
                ),
                artifacts={"error_code": "validation_error"},
                steps=steps + [AgentExecutionStep(name="parse_move", status="error", detail="title_missing")],
            )

        def _select_best(pages: list[dict], target: str) -> dict | None:
            if not pages:
                return None
            normalized_target = _normalize_title(target)
            return next(
                (page for page in pages if _normalize_title(page["title"]) == normalized_target),
                None,
            ) or next(
                (page for page in pages if normalized_target in _normalize_title(page["title"])),
                pages[0],
            )

        source_search = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": source_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        source_pages = [
            {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
            for page in (source_search.get("data") or {}).get("results", [])
        ]
        steps.append(
            AgentExecutionStep(
                name="search_source_page",
                status="success",
                detail=f"원본 페이지 조회 '{source_title}' 결과 {len(source_pages)}건",
            )
        )
        source_page = _select_best(source_pages, source_title)
        if not source_page:
            return AgentExecutionResult(
                success=False,
                summary="이동 원본 페이지를 찾지 못했습니다.",
                user_message=f"'{source_title}' 페이지를 찾지 못했습니다.",
                artifacts={"error_code": "not_found"},
                steps=steps,
            )

        parent_search = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": parent_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        parent_pages = [
            {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
            for page in (parent_search.get("data") or {}).get("results", [])
        ]
        steps.append(
            AgentExecutionStep(
                name="search_parent_page",
                status="success",
                detail=f"상위 페이지 조회 '{parent_title}' 결과 {len(parent_pages)}건",
            )
        )
        parent_page = _select_best(parent_pages, parent_title)
        if not parent_page:
            return AgentExecutionResult(
                success=False,
                summary="이동 대상 상위 페이지를 찾지 못했습니다.",
                user_message=f"'{parent_title}' 상위 페이지를 찾지 못했습니다.",
                artifacts={"error_code": "not_found"},
                steps=steps,
            )

        await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "update_page", "notion_update_page"),
            payload={
                "page_id": source_page["id"],
                "parent": {"page_id": parent_page["id"]},
            },
        )
        steps.append(
            AgentExecutionStep(
                name="move_page",
                status="success",
                detail=f"{source_page['title']} -> {parent_page['title']}",
            )
        )
        return AgentExecutionResult(
            success=True,
            summary="페이지 이동을 완료했습니다.",
            user_message=(
                "요청하신 페이지를 하위로 이동했습니다.\n"
                f"- 원본 페이지: {source_page['title']}\n"
                f"- 상위 페이지: {parent_page['title']}\n"
                f"- 원본 링크: {source_page['url']}\n"
                f"- 상위 링크: {parent_page['url']}"
            ),
            steps=steps,
        )

    if _requires_append_to_page(plan):
        target_title, append_content = _extract_append_target_and_content(plan.user_text)
        if not target_title:
            return AgentExecutionResult(
                success=False,
                summary="추가 대상 페이지 제목을 추출하지 못했습니다.",
                user_message=(
                    "요청은 이해했지만 대상 페이지 제목을 찾지 못했습니다.\n"
                    "예: '노션에서 Metel test page에 액션 아이템 추가해줘'"
                ),
                steps=steps + [AgentExecutionStep(name="extract_title", status="error", detail="title_missing")],
            )
        if not append_content:
            return AgentExecutionResult(
                success=False,
                summary="추가할 내용을 추출하지 못했습니다.",
                user_message=(
                    "추가할 내용을 찾지 못했습니다.\n"
                    "예: '노션에서 Metel test page에 액션 아이템 추가해줘'"
                ),
                steps=steps + [AgentExecutionStep(name="extract_content", status="error", detail="content_missing")],
            )

        # If user includes external URL + summary intent, summarize URL text first then append.
        urls = re.findall(r"https?://\S+", plan.user_text)
        if urls and "요약" in plan.user_text:
            source_text = await _fetch_url_plain_text(urls[0])
            if source_text:
                summary_text, summarize_mode = await _summarize_text_with_llm(source_text, plan.user_text)
                char_limit = _extract_summary_char_limit(plan.user_text)
                if char_limit:
                    summary_text = re.sub(r"\s+", " ", summary_text).strip()[:char_limit].rstrip()
                append_content = summary_text
                steps.append(
                    AgentExecutionStep(
                        name="summarize_external",
                        status="success",
                        detail=f"url={urls[0]} mode={summarize_mode}",
                    )
                )
            else:
                steps.append(
                    AgentExecutionStep(
                        name="summarize_external",
                        status="error",
                        detail="url_fetch_failed",
                    )
                )

        search_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": target_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        raw_pages = (search_result.get("data") or {}).get("results", [])
        normalized_pages = [
            {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
            for page in raw_pages
        ]
        steps.append(
            AgentExecutionStep(
                name="search_pages",
                status="success",
                detail=f"제목 기반 조회 '{target_title}' 결과 {len(normalized_pages)}건",
            )
        )
        if not normalized_pages:
            return AgentExecutionResult(
                success=False,
                summary="요청한 제목의 페이지를 찾지 못했습니다.",
                user_message=f"'{target_title}' 페이지를 찾지 못했습니다. 제목을 다시 확인해주세요.",
                steps=steps,
            )

        normalized_target = _normalize_title(target_title)
        selected_page = next(
            (page for page in normalized_pages if _normalize_title(page["title"]) == normalized_target),
            None,
        )
        if not selected_page:
            selected_page = next(
                (page for page in normalized_pages if normalized_target in _normalize_title(page["title"])),
                normalized_pages[0],
            )
        steps.append(
            AgentExecutionStep(
                name="select_page",
                status="success",
                detail=f"선택 페이지: {selected_page['title']}",
            )
        )

        _ = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "retrieve_page", "notion_retrieve_page"),
            payload={"page_id": selected_page["id"]},
        )
        steps.append(AgentExecutionStep(name="retrieve_page", status="success", detail="페이지 메타데이터 조회 완료"))

        children = []
        for line in [item.strip() for item in re.split(r"[\n,;]", append_content) if item.strip()]:
            children.append(
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
        await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "append_block_children", "notion_append_block_children"),
            payload={"block_id": selected_page["id"], "children": children},
        )
        steps.append(
            AgentExecutionStep(
                name="append_content",
                status="success",
                detail=f"본문 {len(children)}개 단락 추가",
            )
        )
        return AgentExecutionResult(
            success=True,
            summary="요청한 페이지에 내용을 추가했습니다.",
            user_message=(
                "요청하신 내용을 페이지에 추가했습니다.\n"
                f"- 페이지: {selected_page['title']}\n"
                f"- 링크: {selected_page['url']}\n"
                f"- 추가 내용: {append_content}"
            ),
            artifacts={"source_page_url": selected_page["url"], "source_page_title": selected_page["title"]},
            steps=steps,
        )

    if _requires_page_archive(plan):
        target_title = _extract_page_archive_target(plan.user_text)
        if not target_title:
            return AgentExecutionResult(
                success=False,
                summary="삭제 대상 페이지 제목을 추출하지 못했습니다.",
                user_message=(
                    "삭제할 페이지 제목을 찾지 못했습니다.\n"
                    "예: '노션에서 Metel test page 페이지 삭제해줘'"
                ),
                steps=steps + [AgentExecutionStep(name="extract_archive_title", status="error", detail="title_missing")],
            )

        search_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": target_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        raw_pages = (search_result.get("data") or {}).get("results", [])
        normalized_pages = [
            {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
            for page in raw_pages
        ]
        steps.append(
            AgentExecutionStep(
                name="search_pages",
                status="success",
                detail=f"삭제 대상 조회 '{target_title}' 결과 {len(normalized_pages)}건",
            )
        )
        if not normalized_pages:
            return AgentExecutionResult(
                success=False,
                summary="삭제 대상 페이지를 찾지 못했습니다.",
                user_message=f"'{target_title}' 페이지를 찾지 못했습니다.",
                steps=steps + [AgentExecutionStep(name="select_page", status="error", detail="page_not_found")],
            )

        normalized_target = _normalize_title(target_title)
        selected_page = next(
            (page for page in normalized_pages if _normalize_title(page["title"]) == normalized_target),
            None,
        ) or next(
            (page for page in normalized_pages if normalized_target in _normalize_title(page["title"])),
            normalized_pages[0],
        )
        # Prefer deletable page candidates when same-title pages include workspace-level pages.
        if selected_page.get("parent_type") == "workspace":
            alternative = next(
                (
                    page
                    for page in normalized_pages
                    if _normalize_title(page["title"]) == _normalize_title(selected_page["title"])
                    and page.get("parent_type") != "workspace"
                ),
                None,
            )
            if alternative:
                selected_page = alternative
        steps.append(
            AgentExecutionStep(
                name="select_page",
                status="success",
                detail=(
                    f"선택 페이지: {selected_page['title']} ({selected_page.get('id')}) "
                    f"parent={selected_page.get('parent_type') or 'unknown'}"
                ),
            )
        )
        selected_page_id = selected_page.get("id")
        if not _is_valid_notion_id(selected_page_id):
            return AgentExecutionResult(
                success=False,
                summary="삭제 대상 페이지 ID가 유효하지 않습니다.",
                user_message="삭제 대상 페이지 ID를 확인하지 못했습니다. 페이지 제목을 더 구체적으로 입력해주세요.",
                artifacts={"error_code": "validation_error"},
                steps=steps + [AgentExecutionStep(name="select_page", status="error", detail="invalid_page_id")],
            )
        selected_update_tool = _pick_tool_or_none(plan, "update_page")
        selected_delete_tool = _pick_tool_or_none(plan, "delete_block")
        update_tool = selected_update_tool or "notion_update_page"
        delete_tool = selected_delete_tool or "notion_delete_block"

        # If planner explicitly selected delete_block only, prefer that first.
        attempts: list[tuple[str, str, dict]] = []
        if selected_delete_tool and not selected_update_tool:
            attempts.append(("delete_block_primary", delete_tool, {"block_id": selected_page_id}))
            attempts.append(("update_archived_fallback", update_tool, {"page_id": selected_page_id, "archived": True}))
            attempts.append(("update_in_trash_fallback", update_tool, {"page_id": selected_page_id, "in_trash": True}))
        else:
            attempts.append(("update_archived_primary", update_tool, {"page_id": selected_page_id, "archived": True}))
            attempts.append(("update_in_trash_fallback", update_tool, {"page_id": selected_page_id, "in_trash": True}))
            attempts.append(("delete_block_fallback", delete_tool, {"block_id": selected_page_id}))

        archive_done = False
        last_error_detail = ""
        for attempt_name, tool_name, payload in attempts:
            try:
                await execute_tool(user_id=user_id, tool_name=tool_name, payload=payload)
                steps.append(AgentExecutionStep(name="archive_retry", status="success", detail=attempt_name))
                archive_done = True
                break
            except HTTPException as exc:
                last_error_detail = str(exc.detail)
                steps.append(AgentExecutionStep(name="archive_retry", status="error", detail=f"{attempt_name}:{last_error_detail}"))

        if not archive_done:
            # If page is already archived, treat as success for idempotent delete UX.
            retrieve = await execute_tool(
                user_id=user_id,
                tool_name=_pick_tool(plan, "retrieve_page", "notion_retrieve_page"),
                payload={"page_id": selected_page_id},
            )
            page_data = retrieve.get("data") or {}
            if page_data.get("archived") is True or page_data.get("in_trash") is True:
                steps.append(AgentExecutionStep(name="archive_retry", status="success", detail="already_archived"))
            else:
                if "archiving workspace level pages via api not supported" in (last_error_detail or "").lower():
                    return AgentExecutionResult(
                        success=False,
                        summary="Notion 제약으로 워크스페이스 최상위 페이지를 API로 삭제할 수 없습니다.",
                        user_message=(
                            "선택된 페이지가 Notion 워크스페이스 최상위 페이지라 API 삭제(아카이브)가 불가합니다.\n"
                            "- 해결 방법 1: Notion UI에서 직접 삭제\n"
                            "- 해결 방법 2: 페이지를 상위 페이지/데이터소스 하위로 옮긴 뒤 다시 요청\n"
                            "- 참고: 앞으로 자동 생성 페이지를 삭제 가능하게 하려면 "
                            "`NOTION_DEFAULT_PARENT_PAGE_ID`를 설정하세요."
                        ),
                        artifacts={"error_code": "validation_error"},
                        steps=steps,
                    )
                return AgentExecutionResult(
                    success=False,
                    summary="페이지 삭제(아카이브) 실행에 실패했습니다.",
                    user_message=(
                        "페이지 삭제(아카이브)에 실패했습니다. Notion 페이지 권한/상태를 확인해주세요.\n"
                        f"- 마지막 오류: {last_error_detail or 'unknown'}"
                    ),
                    artifacts={"error_code": "upstream_error"},
                    steps=steps,
                )
        steps.append(AgentExecutionStep(name="archive_page", status="success", detail=f"페이지 아카이브: {selected_page['title']}"))
        return AgentExecutionResult(
            success=True,
            summary="페이지 삭제(아카이브)를 완료했습니다.",
            user_message=(
                "요청하신 페이지를 아카이브했습니다.\n"
                f"- 페이지: {selected_page['title']}\n"
                f"- 링크: {selected_page['url']}"
            ),
            artifacts={"source_page_url": selected_page["url"], "archived": True},
            steps=steps,
        )

    target_title = _extract_target_page_title(plan.user_text)
    if target_title and (_requires_top_lines(plan) or _requires_page_content_read(plan) or _requires_summary_only(plan)):
        search_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": target_title,
                "page_size": 10,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        raw_pages = (search_result.get("data") or {}).get("results", [])
        normalized_pages = [
            {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
            for page in raw_pages
        ]
        steps.append(
            AgentExecutionStep(
                name="search_pages",
                status="success",
                detail=f"제목 기반 조회 '{target_title}' 결과 {len(normalized_pages)}건",
            )
        )

        if not normalized_pages:
            return AgentExecutionResult(
                success=False,
                summary="요청한 제목의 페이지를 찾지 못했습니다.",
                user_message=f"'{target_title}' 페이지를 찾지 못했습니다. 제목을 다시 확인해주세요.",
                steps=steps,
            )

        normalized_target = _normalize_title(target_title)
        selected_page = next(
            (page for page in normalized_pages if _normalize_title(page["title"]) == normalized_target),
            None,
        )
        if not selected_page:
            selected_page = next(
                (page for page in normalized_pages if normalized_target in _normalize_title(page["title"])),
                normalized_pages[0],
            )
        steps.append(
            AgentExecutionStep(
                name="select_page",
                status="success",
                detail=f"선택 페이지: {selected_page['title']}",
            )
        )
        return await _read_page_lines_or_summary(
            user_id=user_id,
            plan=plan,
            steps=steps,
            selected_page=selected_page,
        )

    if _requires_top_lines(plan) or _requires_page_content_read(plan):
        return AgentExecutionResult(
            success=False,
            summary="대상 페이지 제목을 추출하지 못했습니다.",
            user_message=(
                "요청은 이해했지만 대상 페이지 제목을 찾지 못했습니다.\n"
                "예: '노션에서 Metel test page의 내용 중 상위 10줄 출력'"
            ),
            steps=steps + [AgentExecutionStep(name="extract_title", status="error", detail="title_missing")],
        )

    if _requires_creation(plan) and not _requires_summary(plan):
        parent_title, child_title = _extract_nested_create_request(plan.user_text)
        parent_page_id = None
        parent_page_url = None

        if parent_title:
            search_result = await execute_tool(
                user_id=user_id,
                tool_name=_pick_tool(plan, "search", "notion_search"),
                payload={
                    "query": parent_title,
                    "page_size": 10,
                    "filter": {"property": "object", "value": "page"},
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                },
            )
            raw_pages = (search_result.get("data") or {}).get("results", [])
            normalized_pages = [
                {"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")}
                for page in raw_pages
            ]
            steps.append(
                AgentExecutionStep(
                    name="search_pages",
                    status="success",
                    detail=f"상위 페이지 조회 '{parent_title}' 결과 {len(normalized_pages)}건",
                )
            )
            if not normalized_pages:
                return AgentExecutionResult(
                    success=False,
                    summary="상위 페이지를 찾지 못했습니다.",
                    user_message=f"'{parent_title}' 상위 페이지를 찾지 못했습니다.",
                    artifacts={"error_code": "not_found"},
                    steps=steps,
                )
            normalized_target = _normalize_title(parent_title)
            selected_parent = next(
                (page for page in normalized_pages if _normalize_title(page["title"]) == normalized_target),
                None,
            ) or next(
                (page for page in normalized_pages if normalized_target in _normalize_title(page["title"])),
                normalized_pages[0],
            )
            parent_page_id = selected_parent["id"]
            parent_page_url = selected_parent["url"]
            steps.append(
                AgentExecutionStep(
                    name="select_parent_page",
                    status="success",
                    detail=f"상위 페이지: {selected_parent['title']} ({parent_page_id})",
                )
            )

        output_title = child_title or _extract_output_title(plan.user_text, default_title="Metel 새 페이지")
        parent_payload = {"page_id": parent_page_id} if parent_page_id else _notion_create_parent_payload()
        create_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "create_page", "notion_create_page"),
            payload={
                "parent": parent_payload,
                "properties": {
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": output_title},
                            }
                        ]
                    }
                },
            },
        )
        created = create_result.get("data") or {}
        created_page_url = created.get("url")
        steps.append(AgentExecutionStep(name="create_page", status="success", detail=f"페이지 생성: {output_title}"))
        return AgentExecutionResult(
            success=True,
            summary="페이지 생성을 완료했습니다.",
            user_message=(
                "요청하신 페이지를 생성했습니다.\n"
                f"- 제목: {output_title}\n"
                f"- 링크: {created_page_url}\n"
                + (f"- 상위 페이지: {parent_page_url}\n" if parent_page_url else "")
            ),
            artifacts={"created_page_url": created_page_url or "", "created_page_title": output_title},
            steps=steps,
        )

    count = _extract_requested_count(plan, default_count=3)
    requested_titles = _extract_requested_page_titles(plan.user_text)
    if requested_titles and _requires_creation(plan):
        output_title = _extract_output_title(plan.user_text, default_title="")
        if output_title:
            requested_titles = [title for title in requested_titles if _normalize_title(title) != _normalize_title(output_title)]
    if requested_titles:
        gathered_pages: list[dict] = []
        for title in requested_titles:
            search_result = await execute_tool(
                user_id=user_id,
                tool_name=_pick_tool(plan, "search", "notion_search"),
                payload={
                    "query": title,
                    "page_size": 5,
                    "filter": {"property": "object", "value": "page"},
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                },
            )
            pages = (search_result.get("data") or {}).get("results", [])
            normalized = [{"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")} for page in pages]
            if not normalized:
                continue
            normalized_target = _normalize_title(title)
            selected = next(
                (page for page in normalized if _normalize_title(page["title"]) == normalized_target),
                None,
            ) or next(
                (page for page in normalized if normalized_target in _normalize_title(page["title"])),
                normalized[0],
            )
            if not any(item["id"] == selected["id"] for item in gathered_pages):
                gathered_pages.append(selected)
        normalized_pages = gathered_pages
        steps.append(
            AgentExecutionStep(
                name="search_pages",
                status="success",
                detail=f"요청 제목 기반 조회 {len(normalized_pages)}건 ({', '.join(requested_titles)})",
            )
        )
    else:
        search_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "search", "notion_search"),
            payload={
                "query": "",
                "page_size": count,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )
        pages = (search_result.get("data") or {}).get("results", [])
        normalized_pages = [{"id": page.get("id"), "title": _extract_page_title(page), "url": page.get("url")} for page in pages]
        steps.append(AgentExecutionStep(name="search_pages", status="success", detail=f"최근 페이지 {len(normalized_pages)}건 조회"))

    if not normalized_pages:
        return AgentExecutionResult(
            success=False,
            summary="조회된 페이지가 없어 작업을 완료하지 못했습니다.",
            user_message="최근 Notion 페이지를 찾지 못했습니다. 페이지를 만든 뒤 다시 요청해주세요.",
            steps=steps,
        )

    if _requires_summary(plan) and _requires_creation(plan):
        summary_lines = ["# 최근 페이지 요약", f"생성 시각: {datetime.now(timezone.utc).isoformat()}"]
        for idx, page in enumerate(normalized_pages, start=1):
            block_result = await execute_tool(
                user_id=user_id,
                tool_name=_pick_tool(plan, "retrieve_block_children", "notion_retrieve_block_children"),
                payload={"block_id": page["id"], "page_size": 20},
            )
            blocks = (block_result.get("data") or {}).get("results", [])
            plain = _extract_plain_text_from_blocks(blocks)
            short, _ = await _summarize_text_with_llm(plain, "핵심 요약 1~2문장")
            summary_lines.extend(
                [
                    "",
                    f"{idx}. {page['title']}",
                    f"- 원본: {page['url']}",
                    f"- 요약: {short}",
                ]
            )
        steps.append(AgentExecutionStep(name="summarize_pages", status="success", detail="페이지 요약 생성"))

        output_title = _extract_output_title(plan.user_text)
        create_result = await execute_tool(
            user_id=user_id,
            tool_name=_pick_tool(plan, "create_page", "notion_create_page"),
            payload={
                "parent": _notion_create_parent_payload(),
                "properties": {
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": output_title},
                            }
                        ]
                    }
                },
            },
        )
        created = create_result.get("data") or {}
        created_page_id = created.get("id")
        created_page_url = created.get("url")
        steps.append(AgentExecutionStep(name="create_page", status="success", detail=f"페이지 생성: {output_title}"))

        if created_page_id:
            await _notion_append_summary_blocks(user_id, plan, created_page_id, "\n".join(summary_lines))
            steps.append(AgentExecutionStep(name="append_content", status="success", detail="요약 본문 추가 완료"))

        return AgentExecutionResult(
            success=True,
            summary="요청한 요약/생성 작업을 완료했습니다.",
            user_message=(
                "요청하신 작업을 완료했습니다.\n"
                f"- 기준 페이지 수: {len(normalized_pages)}\n"
                f"- 생성 페이지 제목: {output_title}\n"
                f"- 생성 페이지 링크: {created_page_url}"
            ),
            artifacts={"created_page_url": created_page_url or "", "created_page_title": output_title},
            steps=steps,
        )

    # Fallback: page list only
    lines = ["최근 Notion 페이지 조회 결과:"]
    for idx, page in enumerate(normalized_pages, start=1):
        lines.append(f"{idx}. {page['title']}")
        lines.append(f"   {page['url']}")
    return AgentExecutionResult(
        success=True,
        summary="페이지 조회 작업을 완료했습니다.",
        user_message="\n".join(lines),
        steps=steps,
    )


async def execute_agent_plan(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    try:
        if "notion" in plan.target_services:
            return await _execute_notion_plan(user_id, plan)
        return AgentExecutionResult(
            success=False,
            summary="현재 실행 가능한 타겟 서비스가 없습니다.",
            user_message="현재 요청은 실행 가능한 서비스가 없어 처리하지 못했습니다.",
            steps=[AgentExecutionStep(name="service_check", status="error", detail="지원 서비스 미매칭")],
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
