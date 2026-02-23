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


def is_user_facing_tool(tool_name: str) -> bool:
    name = (tool_name or "").strip().lower()
    if not name:
        return False
    blocked_tokens = (
        "oauth",
        "token_exchange",
    )
    return not any(token in name for token in blocked_tokens)


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
    user_tools = [tool for tool in tools if is_user_facing_tool(tool.tool_name)]
    if not user_tools:
        return []

    query_tokens = _tokenize(user_text)
    scored: list[tuple[str, int]] = []
    for tool in user_tools:
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
    return [tool.tool_name for tool in user_tools[: min(max_tools, len(user_tools))]]


def _pick_tool_name(selected_tools: list[str], *tokens: str) -> str | None:
    for tool_name in selected_tools:
        lower = tool_name.lower()
        if all(token.lower() in lower for token in tokens):
            return tool_name
    return None


def _pick_tool_name_from_pool(tool_names: list[str], *tokens: str) -> str | None:
    if not tool_names:
        return None
    for tool_name in tool_names:
        lower = str(tool_name or "").strip().lower()
        if not lower:
            continue
        if all(token.lower() in lower for token in tokens):
            return str(tool_name)
    return None


def _pick_tool_name_for_service(selected_tools: list[str], service: str | None, *tokens: str) -> str | None:
    normalized_service = str(service or "").strip().lower()
    for tool_name in selected_tools:
        name = str(tool_name or "").strip()
        if not name:
            continue
        lower = name.lower()
        if normalized_service and _tool_service_name(name) != normalized_service:
            continue
        if all(token.lower() in lower for token in tokens):
            return name
    return None


def _tool_service_name(tool_name: str) -> str | None:
    name = str(tool_name or "").strip()
    if "_" not in name:
        return None
    return name.split("_", 1)[0].strip().lower() or None


def _pick_primary_tool_for_intent(user_text: str, selected_tools: list[str]) -> str | None:
    tools = [str(item or "").strip() for item in selected_tools if str(item or "").strip()]
    if not tools:
        return None

    def _first_match(*tokens: str) -> str | None:
        for tool in tools:
            lower = tool.lower()
            if all(token in lower for token in tokens):
                return tool
        return None

    if is_delete_intent(user_text):
        return (
            _first_match("delete")
            or _first_match("archive")
            or _first_match("update", "page")
            or _first_match("update")
            or tools[0]
        )
    if is_update_intent(user_text):
        return _first_match("update") or _first_match("append") or _first_match("comment") or tools[0]
    if is_create_intent(user_text):
        return _first_match("create") or _first_match("append") or tools[0]
    if is_read_intent(user_text) or is_summary_intent(user_text):
        return (
            _first_match("search")
            or _first_match("list")
            or _first_match("retrieve")
            or _first_match("query")
            or _first_match("get")
            or tools[0]
        )
    return tools[0]


def _extract_linear_query_from_text(user_text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', user_text)
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    match = re.search(r"(?i)(.+?)\s*(?:의)?\s*이슈", user_text.strip())
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
    match = re.search(r"(?i)(?:의)?\s*(.+?)\s*(?:새로운|신규|new)\s*페이지", user_text)
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

    registry = load_registry()
    available_tools = [
        tool.tool_name
        for tool in registry.list_available_tools(connected_services=target_services)
        if is_user_facing_tool(tool.tool_name)
    ]

    def _pick(tokens: tuple[str, ...]) -> str | None:
        return _pick_tool_name(selected_tools, *tokens) or _pick_tool_name_from_pool(available_tools, *tokens)

    tasks: list[AgentTask] = []
    primary_service = target_services[0] if target_services else None

    if is_data_source_intent(user_text):
        query_tool = _pick(("query", "data_source")) or _pick(("retrieve", "data_source"))
        service = _tool_service_name(query_tool or "")
        if query_tool:
            payload = {"page_size": 5}
            data_source_id = _extract_data_source_id_from_text(user_text)
            if data_source_id:
                payload["data_source_id"] = data_source_id
            task_id = f"task_{service}_data_source_query" if service else "task_data_source_query"
            tasks.append(
                AgentTask(
                    id=task_id,
                    title="데이터소스 조회",
                    task_type="TOOL",
                    service=service,
                    tool_name=query_tool,
                    payload=payload,
                    output_schema={"type": "tool_result", "service": service or "", "tool": query_tool},
                )
            )

    issue_create_tool = _pick(("create", "issue"))
    issue_update_tool = _pick(("update", "issue"))
    issue_search_tool = _pick(("search", "issues")) or _pick(("list", "issues"))

    if is_linear_issue_create_intent(user_text) and issue_create_tool:
        service = _tool_service_name(issue_create_tool)
        task_id = f"task_{service}_create_issue" if service else "task_create_issue"
        tasks.append(
            AgentTask(
                id=task_id,
                title="이슈 생성",
                task_type="TOOL",
                service=service,
                tool_name=issue_create_tool,
                payload={},
                output_schema={"type": "tool_result", "service": service or "", "tool": issue_create_tool},
            )
        )
    elif is_update_intent(user_text) and ("이슈" in user_text or "issue" in user_text.lower()) and issue_update_tool:
        service = _tool_service_name(issue_update_tool)
        task_id = f"task_{service}_update_issue" if service else "task_update_issue"
        tasks.append(
            AgentTask(
                id=task_id,
                title="이슈 수정",
                task_type="TOOL",
                service=service,
                tool_name=issue_update_tool,
                payload={},
                output_schema={"type": "tool_result", "service": service or "", "tool": issue_update_tool},
            )
        )
    elif issue_search_tool and (("이슈" in user_text) or ("issue" in user_text.lower()) or is_read_intent(user_text)):
        service = _tool_service_name(issue_search_tool)
        task_id = f"task_{service}_issues" if service else "task_issues"
        issue_query = _extract_linear_query_from_text(user_text)
        payload = {"first": 5}
        if "search" in issue_search_tool and issue_query:
            payload["query"] = issue_query
        tasks.append(
            AgentTask(
                id=task_id,
                title="이슈 조회",
                task_type="TOOL",
                service=service,
                tool_name=issue_search_tool,
                payload=payload,
                output_schema={"type": "tool_result", "service": service or "", "tool": issue_search_tool},
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

    if need_creation and not is_linear_issue_create_intent(user_text):
        # Prefer create_page tool; otherwise use generic create tool in selected set.
        create_page_tool = _pick(("create", "page"))
        fallback_create_tool = _pick(("create",))
        create_tool = create_page_tool or fallback_create_tool
        if create_tool:
            service = _tool_service_name(create_tool)
            task_id = f"task_{service}_create_page" if create_page_tool and service else "task_create_output"
            depends = [tasks[-1].id] if tasks else []
            payload = {"title_hint": _extract_output_title_hint(user_text) or "Metel 자동 요약"}
            if not create_page_tool:
                payload = {}
            tasks.append(
                AgentTask(
                    id=task_id,
                    title="결과물 생성/저장",
                    task_type="TOOL",
                    service=service,
                    tool_name=create_tool,
                    depends_on=depends,
                    payload=payload,
                    output_schema={"type": "tool_result", "service": service or "", "tool": create_tool},
                )
            )

    if tasks:
        # Contract safety: ensure at least one TOOL task exists.
        # Some summary-heavy prompts can yield only LLM tasks, which violates plan contract.
        has_tool = any(str(task.task_type or "").strip().upper() == "TOOL" for task in tasks)
        if has_tool:
            return tasks
        merged_tool_candidates = list(dict.fromkeys([*selected_tools, *available_tools]))
        primary = _pick_primary_tool_for_intent(user_text, merged_tool_candidates)
        if primary:
            service = _tool_service_name(primary)
            depends = [tasks[-1].id] if tasks else []
            tasks.append(
                AgentTask(
                    id="task_primary_tool",
                    title=f"도구 실행: {primary}",
                    task_type="TOOL",
                    service=service,
                    tool_name=primary,
                    depends_on=depends,
                    payload={},
                    output_schema={"type": "tool_result", "service": service or "", "tool": primary},
                )
            )
        return tasks

    # Generic synthesis path for newly-added services:
    # when selected tools exist but service-specific branches don't match,
    # pick one executable primary tool by intent.
    merged_tool_candidates = list(dict.fromkeys([*selected_tools, *available_tools]))
    primary = _pick_primary_tool_for_intent(user_text, merged_tool_candidates)
    if not primary:
        return []
    service = _tool_service_name(primary)
    return [
        AgentTask(
            id="task_primary_tool",
            title=f"도구 실행: {primary}",
            task_type="TOOL",
            service=service,
            tool_name=primary,
            payload={},
            output_schema={"type": "tool_result", "service": service or "", "tool": primary},
        )
    ]


def build_agent_plan(user_text: str, connected_services: list[str]) -> AgentPlan:
    requirements = _extract_requirements(user_text)
    target_services = resolve_services(user_text, connected_services)

    registry = load_registry()
    available_tools = registry.list_available_tools(connected_services=target_services or connected_services)
    available_tools = [tool for tool in available_tools if is_user_facing_tool(tool.tool_name)]
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
