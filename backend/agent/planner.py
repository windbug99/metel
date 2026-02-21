from __future__ import annotations

import re

from agent.guide_retriever import GuideNotFoundError, get_planning_context
from agent.intent_keywords import (
    is_create_intent,
    is_data_source_intent,
    is_delete_intent,
    is_read_intent,
    is_summary_intent,
    is_update_intent,
    is_linear_issue_create_intent,
)
from agent.registry import ToolDefinition, load_registry
from agent.service_resolver import resolve_services
from agent.types import AgentPlan, AgentRequirement, AgentTask


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(개|건|페이지|page|pages|줄|line|lines)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _extract_requirements(user_text: str) -> list[AgentRequirement]:
    normalized = user_text.strip()
    quantity = _extract_quantity(normalized)

    requirements: list[AgentRequirement] = []
    if is_summary_intent(normalized):
        requirements.append(AgentRequirement(summary="대상 콘텐츠 요약", quantity=quantity))
    if is_create_intent(normalized):
        requirements.append(AgentRequirement(summary="결과물 생성", quantity=1))
    if any(keyword in normalized for keyword in ("추가", "append")) or is_update_intent(normalized):
        requirements.append(AgentRequirement(summary="기존 결과물 수정/추가", quantity=1))
    if is_read_intent(normalized):
        requirements.append(AgentRequirement(summary="대상 데이터 조회", quantity=quantity))
    if any(keyword in normalized for keyword in ("내용", "본문", "상위", "줄", "출력", "보여")):
        requirements.append(AgentRequirement(summary="페이지 본문 일부 추출", quantity=quantity))
    if any(keyword in normalized for keyword in ("제목 변경", "제목 수정", "rename")) and "제목" in normalized:
        requirements.append(AgentRequirement(summary="페이지 메타데이터 업데이트", quantity=1))
    if is_delete_intent(normalized):
        requirements.append(AgentRequirement(summary="페이지 아카이브(삭제)", quantity=1))
    if is_data_source_intent(normalized):
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
        if is_create_intent(user_text) and (
            "create" in tool.tool_name or "append" in tool.tool_name
        ):
            overlap += 2
        if is_read_intent(user_text) and (
            "search" in tool.tool_name or "get" in tool.tool_name or "retrieve" in tool.tool_name
        ):
            overlap += 1
        if is_delete_intent(user_text) and "update" in tool.tool_name:
            overlap += 2

        scored.append((tool.tool_name, overlap))

    scored.sort(key=lambda item: item[1], reverse=True)
    selected = [name for name, score in scored if score > 0][:max_tools]
    if selected:
        return selected
    return [tool.tool_name for tool in tools[: min(max_tools, len(tools))]]


def _pick_tool_name(selected_tools: list[str], *tokens: str) -> str | None:
    for tool_name in selected_tools:
        lower = tool_name.lower()
        if all(token.lower() in lower for token in tokens):
            return tool_name
    return None


def _extract_linear_query_from_text(user_text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', user_text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    match = re.search(r"(?i)(?:linear|리니어)(?:의|에서)?\s*(.+?)\s*(?:의)?\s*이슈", user_text.strip())
    if not match:
        return None
    candidate = match.group(1).strip(" \"'`")
    return candidate or None


def _extract_summary_sentence_count(user_text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(?:문장|sentence|sentences)", user_text, flags=re.IGNORECASE)
    if not match:
        return None
    return max(1, min(10, int(match.group(1))))


def _extract_output_title_hint(user_text: str) -> str | None:
    match = re.search(r"(?i)(?:notion|노션)(?:의)?\s*(.+?)\s*(?:새로운|신규|new)\s*페이지", user_text)
    if match:
        candidate = match.group(1).strip(" \"'`")
        if candidate:
            return candidate[:100]
    return None


def _extract_data_source_id_from_text(user_text: str) -> str | None:
    match = re.search(r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})", user_text)
    if not match:
        return None
    return match.group(1)


def build_execution_tasks(user_text: str, target_services: list[str], selected_tools: list[str]) -> list[AgentTask]:
    if not target_services:
        return []

    need_summary = is_summary_intent(user_text)
    need_creation = is_create_intent(user_text)
    sentence_count = _extract_summary_sentence_count(user_text) or 3

    tasks: list[AgentTask] = []

    if "notion" in target_services and is_data_source_intent(user_text):
        query_tool = _pick_tool_name(selected_tools, "notion", "query", "data_source") or "notion_query_data_source"
        data_source_id = _extract_data_source_id_from_text(user_text)
        if data_source_id:
            tasks.append(
                AgentTask(
                    id="task_notion_data_source_query",
                    title="Notion 데이터소스 조회",
                    task_type="TOOL",
                    service="notion",
                    tool_name=query_tool,
                    payload={"data_source_id": data_source_id, "page_size": 5},
                    output_schema={"type": "tool_result", "service": "notion", "tool": query_tool},
                )
            )

    if "linear" in target_services:
        if is_linear_issue_create_intent(user_text):
            create_tool = _pick_tool_name(selected_tools, "linear", "create", "issue") or "linear_create_issue"
            tasks.append(
                AgentTask(
                    id="task_linear_create_issue",
                    title="Linear 이슈 생성",
                    task_type="TOOL",
                    service="linear",
                    tool_name=create_tool,
                    payload={},
                    output_schema={"type": "tool_result", "service": "linear", "tool": create_tool},
                )
            )
        elif is_update_intent(user_text) and ("이슈" in user_text or "issue" in user_text.lower()):
            update_tool = _pick_tool_name(selected_tools, "linear", "update", "issue") or "linear_update_issue"
            tasks.append(
                AgentTask(
                    id="task_linear_update_issue",
                    title="Linear 이슈 수정",
                    task_type="TOOL",
                    service="linear",
                    tool_name=update_tool,
                    payload={},
                    output_schema={"type": "tool_result", "service": "linear", "tool": update_tool},
                )
            )
        else:
            search_tool = _pick_tool_name(selected_tools, "linear", "search", "issues")
            if not search_tool:
                search_tool = _pick_tool_name(selected_tools, "linear", "list", "issues")
            query = _extract_linear_query_from_text(user_text)
            linear_tool_name = search_tool or ("linear_search_issues" if query else "linear_list_issues")
            payload = {"first": 5}
            if "search" in linear_tool_name and query:
                payload["query"] = query
            tasks.append(
                AgentTask(
                    id="task_linear_issues",
                    title="Linear 이슈 조회",
                    task_type="TOOL",
                    service="linear",
                    tool_name=linear_tool_name,
                    payload=payload,
                    output_schema={"type": "tool_result", "service": "linear", "tool": linear_tool_name},
                )
            )

    if need_summary:
        summary_depends = [tasks[-1].id] if tasks else []
        tasks.append(
            AgentTask(
                id="task_llm_summary",
                title=f"{sentence_count}문장 요약",
                task_type="LLM",
                depends_on=summary_depends,
                instruction=f"주어진 입력을 한국어 {sentence_count}문장으로 요약하세요. 사실만 유지하고 추측하지 마세요.",
                payload={"sentences": sentence_count},
                output_schema={"type": "text", "sentences": sentence_count},
            )
        )

    if "notion" in target_services and need_creation and not is_linear_issue_create_intent(user_text):
        create_tool = _pick_tool_name(selected_tools, "notion", "create", "page")
        depends = [tasks[-1].id] if tasks else []
        tasks.append(
            AgentTask(
                id="task_notion_create_page",
                title="Notion 페이지 생성/저장",
                task_type="TOOL",
                service="notion",
                tool_name=create_tool or "notion_create_page",
                depends_on=depends,
                payload={"title_hint": _extract_output_title_hint(user_text) or "Metel 자동 요약"},
                output_schema={"type": "tool_result", "service": "notion", "tool": create_tool or "notion_create_page"},
            )
        )

    if tasks:
        return tasks

    # Fallback: preserve legacy execution by exposing selected tools as TOOL tasks.
    fallback_tasks: list[AgentTask] = []
    for idx, tool_name in enumerate(selected_tools, start=1):
        fallback_tasks.append(
            AgentTask(
                id=f"task_tool_{idx}",
                title=f"도구 실행: {tool_name}",
                task_type="TOOL",
                service=tool_name.split("_", 1)[0] if "_" in tool_name else None,
                tool_name=tool_name,
                output_schema={
                    "type": "tool_result",
                    "service": (tool_name.split("_", 1)[0] if "_" in tool_name else ""),
                    "tool": tool_name,
                },
            )
        )
    return fallback_tasks


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
    tasks = build_execution_tasks(user_text=user_text, target_services=target_services, selected_tools=selected_tools)
    if any(task.task_type == "LLM" for task in tasks):
        workflow_steps.append("API 비의존 작업은 LLM 작업으로 분류하여 실행")

    return AgentPlan(
        user_text=user_text,
        requirements=requirements,
        target_services=target_services,
        selected_tools=selected_tools,
        workflow_steps=workflow_steps,
        tasks=tasks,
        notes=notes,
    )
