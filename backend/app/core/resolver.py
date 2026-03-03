from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


ToolExecutor = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ResolverException(Exception):
    error_code: str
    message: str
    data: dict[str, Any] | None = None


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _extract_notion_page_title(item: dict[str, Any]) -> str:
    properties = item.get("properties")
    if not isinstance(properties, dict):
        return ""
    for prop in properties.values():
        if not isinstance(prop, dict):
            continue
        if prop.get("type") != "title":
            continue
        chunks = prop.get("title")
        if not isinstance(chunks, list):
            continue
        text = "".join(str(chunk.get("plain_text") or "") for chunk in chunks if isinstance(chunk, dict)).strip()
        if text:
            return text
    return ""


def _pick_single_notion_page(query: str, results: list[dict[str, Any]]) -> str:
    candidates = [row for row in results if isinstance(row, dict) and row.get("object") == "page" and row.get("id")]
    if not candidates:
        raise ResolverException(
            error_code="resolve_not_found",
            message="resolve_not_found",
            data={"target": "notion_page", "query": query},
        )
    if len(candidates) == 1:
        return str(candidates[0]["id"])

    query_norm = _normalize_text(query)
    exact = [row for row in candidates if _normalize_text(_extract_notion_page_title(row)) == query_norm]
    if len(exact) == 1:
        return str(exact[0]["id"])
    if len(exact) > 1:
        candidates = exact

    raise ResolverException(
        error_code="resolve_ambiguous",
        message="resolve_ambiguous",
        data={
            "target": "notion_page",
            "query": query,
            "candidate_ids": [str(row.get("id")) for row in candidates[:5]],
        },
    )


def _pick_single_linear_team(query: str, teams: list[dict[str, Any]]) -> str:
    items = [row for row in teams if isinstance(row, dict) and row.get("id")]
    if not items:
        raise ResolverException(
            error_code="resolve_not_found",
            message="resolve_not_found",
            data={"target": "linear_team", "query": query},
        )

    query_norm = _normalize_text(query)
    matches = [
        row
        for row in items
        if _normalize_text(str(row.get("name") or "")) == query_norm
        or _normalize_text(str(row.get("key") or "")) == query_norm
    ]
    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        items = matches
    elif len(items) == 1:
        return str(items[0]["id"])

    raise ResolverException(
        error_code="resolve_ambiguous",
        message="resolve_ambiguous",
        data={
            "target": "linear_team",
            "query": query,
            "candidate_ids": [str(row.get("id")) for row in items[:5]],
        },
    )


async def _resolve_notion_page_id(
    *,
    user_id: str,
    tool_name: str,
    payload: dict[str, Any],
    execute_tool: ToolExecutor,
) -> dict[str, Any]:
    if tool_name not in {"notion_update_page", "notion_retrieve_page"}:
        return payload
    page_id = str(payload.get("page_id") or "").strip()
    if page_id:
        return payload

    query = str(payload.get("page_title") or payload.get("page_name") or "").strip()
    if not query:
        return payload

    search_result = await execute_tool(user_id=user_id, tool_name="notion_search", payload={"query": query, "page_size": 10})
    data = search_result.get("data") if isinstance(search_result, dict) else None
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        rows = []

    resolved_page_id = _pick_single_notion_page(query, rows)
    normalized = dict(payload)
    normalized["page_id"] = resolved_page_id
    return normalized


async def _resolve_linear_team_id(
    *,
    user_id: str,
    tool_name: str,
    payload: dict[str, Any],
    execute_tool: ToolExecutor,
) -> dict[str, Any]:
    if tool_name != "linear_create_issue":
        return payload
    team_id = str(payload.get("team_id") or "").strip()
    if team_id:
        return payload

    query = str(payload.get("team_name") or "").strip()
    if not query:
        return payload

    team_result = await execute_tool(user_id=user_id, tool_name="linear_list_teams", payload={"first": 20})
    data = team_result.get("data") if isinstance(team_result, dict) else None
    teams_node = data.get("teams") if isinstance(data, dict) else None
    rows = teams_node.get("nodes") if isinstance(teams_node, dict) else None
    if not isinstance(rows, list):
        rows = []

    resolved_team_id = _pick_single_linear_team(query, rows)
    normalized = dict(payload)
    normalized["team_id"] = resolved_team_id
    return normalized


async def resolve_tool_payload(
    *,
    user_id: str,
    tool_name: str,
    payload: dict[str, Any],
    execute_tool: ToolExecutor,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized = await _resolve_notion_page_id(
        user_id=user_id,
        tool_name=tool_name,
        payload=normalized,
        execute_tool=execute_tool,
    )
    normalized = await _resolve_linear_team_id(
        user_id=user_id,
        tool_name=tool_name,
        payload=normalized,
        execute_tool=execute_tool,
    )
    return normalized
