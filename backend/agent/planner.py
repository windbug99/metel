from __future__ import annotations

import re

from agent.guide_retriever import GuideNotFoundError, get_planning_context
from agent.registry import ToolDefinition, load_registry
from agent.service_resolver import resolve_services
from agent.types import AgentPlan, AgentRequirement


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(개|건|페이지|page|pages|줄|line|lines)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _extract_requirements(user_text: str) -> list[AgentRequirement]:
    normalized = user_text.strip()
    quantity = _extract_quantity(normalized)

    requirements: list[AgentRequirement] = []
    if any(keyword in normalized for keyword in ("요약", "summary", "정리")):
        requirements.append(AgentRequirement(summary="대상 콘텐츠 요약", quantity=quantity))
    if any(keyword in normalized for keyword in ("생성", "만들", "작성", "create")):
        requirements.append(AgentRequirement(summary="결과물 생성", quantity=1))
    if any(keyword in normalized for keyword in ("추가", "업데이트", "갱신", "append", "update")):
        requirements.append(AgentRequirement(summary="기존 결과물 수정/추가", quantity=1))
    if any(keyword in normalized for keyword in ("조회", "검색", "찾", "list", "search")):
        requirements.append(AgentRequirement(summary="대상 데이터 조회", quantity=quantity))
    if any(keyword in normalized for keyword in ("내용", "본문", "상위", "줄", "출력", "보여")):
        requirements.append(AgentRequirement(summary="페이지 본문 일부 추출", quantity=quantity))
    if any(keyword in normalized for keyword in ("제목 변경", "제목 수정", "rename", "바꿔", "변경")) and "제목" in normalized:
        requirements.append(AgentRequirement(summary="페이지 메타데이터 업데이트", quantity=1))
    if any(keyword in normalized for keyword in ("삭제", "지워", "아카이브", "archive")):
        requirements.append(AgentRequirement(summary="페이지 아카이브(삭제)", quantity=1))
    if any(keyword in normalized for keyword in ("데이터소스", "data source", "data_source")):
        requirements.append(AgentRequirement(summary="데이터소스 질의", quantity=quantity))

    if not requirements:
        requirements.append(AgentRequirement(summary="사용자 요청 분석 및 실행 계획 수립", quantity=quantity))
    return requirements


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^0-9a-zA-Z가-힣_ ]+", " ", text.lower())
    return {token for token in cleaned.split() if len(token) >= 2}


def _select_tools(user_text: str, tools: list[ToolDefinition], max_tools: int = 5) -> list[str]:
    if not tools:
        return []

    query_tokens = _tokenize(user_text)
    scored: list[tuple[str, int]] = []
    for tool in tools:
        corpus = f"{tool.tool_name} {tool.description}"
        tool_tokens = _tokenize(corpus)
        overlap = len(query_tokens & tool_tokens)

        # Lightweight verb heuristics to better map Korean natural language.
        if "요약" in user_text and ("retrieve" in tool.tool_name or "search" in tool.tool_name):
            overlap += 1
        if any(keyword in user_text for keyword in ("생성", "만들", "작성")) and (
            "create" in tool.tool_name or "append" in tool.tool_name
        ):
            overlap += 2
        if any(keyword in user_text for keyword in ("조회", "검색", "목록", "최근")) and (
            "search" in tool.tool_name or "get" in tool.tool_name or "retrieve" in tool.tool_name
        ):
            overlap += 1
        if any(keyword in user_text for keyword in ("삭제", "지워", "아카이브", "archive")) and "update" in tool.tool_name:
            overlap += 2

        scored.append((tool.tool_name, overlap))

    scored.sort(key=lambda item: item[1], reverse=True)
    selected = [name for name, score in scored if score > 0][:max_tools]
    if selected:
        return selected
    return [tool.tool_name for tool in tools[: min(max_tools, len(tools))]]


def build_agent_plan(user_text: str, connected_services: list[str]) -> AgentPlan:
    requirements = _extract_requirements(user_text)
    target_services = resolve_services(user_text, connected_services)

    registry = load_registry()
    available_tools = registry.list_available_tools(connected_services=target_services or connected_services)
    selected_tools = _select_tools(user_text, available_tools)

    notes: list[str] = []
    for service in target_services:
        try:
            guide_context = get_planning_context(service, max_chars=1200)
            if guide_context:
                notes.append(f"{service} guide loaded")
        except GuideNotFoundError:
            notes.append(f"{service} guide missing")

    workflow_steps = [
        "요청문 분석 및 작업 요구사항 도출",
        "작업 요구사항 기반 타겟 서비스 선정",
        "타겟 서비스의 실행 가능한 API(tool) 선정",
        "선정된 API 순서 기반 워크플로우 생성",
        "워크플로우 기반 작업 진행",
        "결과 정리",
        "텔레그램 사용자 결과 전달",
    ]
    if selected_tools:
        workflow_steps.append("실행 예정 API 순서: " + " -> ".join(selected_tools))

    return AgentPlan(
        user_text=user_text,
        requirements=requirements,
        target_services=target_services,
        selected_tools=selected_tools,
        workflow_steps=workflow_steps,
        notes=notes,
    )
