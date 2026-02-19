from __future__ import annotations

import re
from datetime import datetime, timezone
from json import JSONDecodeError

import httpx
from fastapi import HTTPException
from supabase import create_client

from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan
from app.core.config import get_settings
from app.security.token_vault import TokenVault


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


def _extract_requested_count(plan: AgentPlan, default_count: int = 3) -> int:
    for req in plan.requirements:
        if req.quantity and req.quantity > 0:
            return max(1, min(10, req.quantity))
    return default_count


def _extract_output_title(user_text: str, default_title: str = "Metel 자동 요약 회의록") -> str:
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
        candidate = match.group(1).strip(" \"'`")
        candidate = re.sub(r"^(노션|notion)\s*", "", candidate, flags=re.IGNORECASE).strip()
        if "으로" in user_text and candidate.endswith("으"):
            candidate = candidate[:-1].strip()
        if candidate and len(candidate) <= 100:
            return candidate
    return default_title


def _extract_target_page_title(user_text: str) -> str | None:
    patterns = [
        r"(?i)(?:노션에서\s*)?(.+?)의\s*(?:내용|본문)",
        r"(?i)(?:노션에서\s*)?(.+?)\s*페이지(?:의)?\s*(?:내용|본문)",
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


def _extract_requested_line_count(user_text: str, default_count: int = 10) -> int:
    match = re.search(r"(\d{1,2})\s*(줄|line|lines)", user_text, flags=re.IGNORECASE)
    if match:
        return max(1, min(50, int(match.group(1))))
    return default_count


def _load_notion_access_token(user_id: str) -> str:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    token_result = (
        supabase.table("oauth_tokens")
        .select("access_token_encrypted")
        .eq("user_id", user_id)
        .eq("provider", "notion")
        .limit(1)
        .execute()
    )
    rows = token_result.data or []
    if not rows:
        raise HTTPException(status_code=400, detail="notion_not_connected")

    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail="notion_token_missing")

    return TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)


async def _notion_search_recent_pages(token: str, page_size: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": page_size,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="notion_search_failed")
    try:
        payload = response.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="notion_parse_failed") from exc
    return payload.get("results", [])


async def _notion_search_pages_by_query(token: str, query: str, page_size: int = 10) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": page_size,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="notion_search_failed")
    try:
        payload = response.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="notion_parse_failed") from exc
    return payload.get("results", [])


async def _notion_retrieve_page_blocks(token: str, page_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
            },
            params={"page_size": 20},
        )
    if response.status_code >= 400:
        return []
    try:
        payload = response.json()
    except JSONDecodeError:
        return []
    return payload.get("results", [])


async def _notion_create_page(token: str, title: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "parent": {"workspace": True},
                "properties": {
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": title},
                            }
                        ]
                    }
                },
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="notion_create_failed")
    try:
        return response.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="notion_parse_failed") from exc


async def _notion_append_summary_blocks(token: str, page_id: str, markdown: str) -> None:
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

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={"children": paragraphs},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="notion_append_failed")


def _requires_summary(plan: AgentPlan) -> bool:
    return any("요약" in req.summary for req in plan.requirements) or "요약" in plan.user_text


def _requires_creation(plan: AgentPlan) -> bool:
    return any("생성" in req.summary for req in plan.requirements) or any(
        keyword in plan.user_text for keyword in ("생성", "만들", "작성", "create")
    )


def _requires_top_lines(plan: AgentPlan) -> bool:
    text = plan.user_text
    return (
        any(keyword in text for keyword in ("상위", "줄", "line", "lines"))
        and any(keyword in text for keyword in ("내용", "본문", "출력", "보여", "조회"))
    )


async def _execute_notion_plan(user_id: str, plan: AgentPlan) -> AgentExecutionResult:
    steps: list[AgentExecutionStep] = []
    token = _load_notion_access_token(user_id)
    steps.append(AgentExecutionStep(name="token_load", status="success", detail="Notion 토큰 로드 완료"))

    normalized_pages: list[dict] = []

    if _requires_top_lines(plan):
        target_title = _extract_target_page_title(plan.user_text)
        if not target_title:
            return AgentExecutionResult(
                success=False,
                summary="대상 페이지 제목을 추출하지 못했습니다.",
                user_message=(
                    "요청은 이해했지만 대상 페이지 제목을 찾지 못했습니다.\n"
                    "예: '노션에서 Metel test page의 내용 중 상위 10줄 출력'"
                ),
                steps=steps + [AgentExecutionStep(name="extract_title", status="error", detail="title_missing")],
            )
        raw_pages = await _notion_search_pages_by_query(token, target_title, page_size=10)
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

        blocks = await _notion_retrieve_page_blocks(token, selected_page["id"])
        plain = _extract_plain_text_from_blocks(blocks)
        raw_lines = [line.strip() for line in plain.splitlines() if line.strip()]
        line_count = _extract_requested_line_count(plan.user_text, default_count=10)
        top_lines = raw_lines[:line_count]
        steps.append(
            AgentExecutionStep(
                name="extract_lines",
                status="success",
                detail=f"본문 라인 {len(raw_lines)}개 중 상위 {len(top_lines)}개 추출",
            )
        )

        if not top_lines:
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

    count = _extract_requested_count(plan, default_count=3)
    pages = await _notion_search_recent_pages(token, page_size=count)
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
            blocks = await _notion_retrieve_page_blocks(token, page["id"])
            plain = _extract_plain_text_from_blocks(blocks)
            short = _simple_korean_summary(plain)
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
        created = await _notion_create_page(token, output_title)
        created_page_id = created.get("id")
        created_page_url = created.get("url")
        steps.append(AgentExecutionStep(name="create_page", status="success", detail=f"페이지 생성: {output_title}"))

        if created_page_id:
            await _notion_append_summary_blocks(token, created_page_id, "\n".join(summary_lines))
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
        return AgentExecutionResult(
            success=False,
            summary=f"작업 실행 중 오류: {exc.detail}",
            user_message=(
                "요청을 실행하던 중 오류가 발생했습니다.\n"
                f"- 오류 코드: {exc.detail}\n"
                "잠시 후 다시 시도하거나 요청을 더 구체적으로 입력해주세요."
            ),
            steps=[AgentExecutionStep(name="execution", status="error", detail=str(exc.detail))],
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return AgentExecutionResult(
            success=False,
            summary=f"예상치 못한 오류: {exc}",
            user_message="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            steps=[AgentExecutionStep(name="execution", status="error", detail="internal_error")],
        )
