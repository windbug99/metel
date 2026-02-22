from __future__ import annotations

import base64
import re
from json import JSONDecodeError
from typing import Any, Awaitable, Callable

import httpx
from fastapi import HTTPException
from supabase import create_client

from agent.registry import ToolDefinition, load_registry
from app.core.config import get_settings
from app.security.token_vault import TokenVault


def _load_oauth_access_token(user_id: str, provider: str) -> str:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("access_token_encrypted")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=400, detail=f"{provider}_not_connected")

    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail=f"{provider}_token_missing")

    # NOTE:
    # Current prototype stores encrypted token in a shared column; notion key is used as vault key.
    # When provider-specific keys are introduced, switch this branch by provider.
    return TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)


def _notion_headers(token: str) -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": settings.notion_api_version,
    }


def _notion_oauth_headers() -> dict[str, str]:
    settings = get_settings()
    client_id = (settings.notion_client_id or "").strip()
    client_secret = (settings.notion_client_secret or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="notion_oauth_config_missing")
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


def _parse_response_data(response: httpx.Response) -> dict[str, Any]:
    try:
        return {"ok": True, "data": response.json()}
    except JSONDecodeError:
        return {"ok": True, "data": {"raw_text": response.text}}


def _extract_path_params(path: str) -> list[str]:
    return re.findall(r"{([a-zA-Z0-9_]+)}", path)


def _build_path(path: str, payload: dict[str, Any]) -> str:
    rendered = path
    for key in _extract_path_params(path):
        value = payload.get(key)
        if value is None or value == "":
            raise HTTPException(status_code=400, detail=f"missing_path_param:{key}")
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def _strip_path_params(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    used = set(_extract_path_params(path))
    return {k: v for k, v in payload.items() if k not in used}


def _validate_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_payload_by_schema(tool: ToolDefinition, payload: dict[str, Any]) -> None:
    schema = tool.input_schema or {}
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for req in required:
        if payload.get(req) is None:
            raise HTTPException(status_code=400, detail=f"{tool.tool_name}:VALIDATION_REQUIRED:{req}")

    for key, value in payload.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            continue
        expected_type = spec.get("type")
        if expected_type and not _validate_type(value, expected_type):
            raise HTTPException(status_code=400, detail=f"{tool.tool_name}:VALIDATION_TYPE:{key}")

        if expected_type == "integer":
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if minimum is not None and value < minimum:
                raise HTTPException(status_code=400, detail=f"{tool.tool_name}:VALIDATION_MIN:{key}")
            if maximum is not None and value > maximum:
                raise HTTPException(status_code=400, detail=f"{tool.tool_name}:VALIDATION_MAX:{key}")

        enum_values = spec.get("enum")
        if enum_values and value not in enum_values:
            raise HTTPException(status_code=400, detail=f"{tool.tool_name}:VALIDATION_ENUM:{key}")


def _default_notion_parent() -> dict[str, Any]:
    settings = get_settings()
    parent_page_id = (settings.notion_default_parent_page_id or "").strip()
    if parent_page_id:
        return {"page_id": parent_page_id}
    return {"workspace": True}


def _normalize_notion_create_page_payload(payload: dict[str, Any]) -> dict[str, Any]:
    parent = payload.get("parent")
    if not isinstance(parent, dict):
        payload["parent"] = _default_notion_parent()
        return payload

    # LLM frequently emits placeholders from docs/examples.
    placeholder_values = {"your_database_id_here", "database_id_here", "your_page_id_here", "page_id_here"}
    database_id = (parent.get("database_id") or "").strip() if isinstance(parent.get("database_id"), str) else ""
    page_id = (parent.get("page_id") or "").strip() if isinstance(parent.get("page_id"), str) else ""
    workspace = parent.get("workspace")
    data_source_id = (parent.get("data_source_id") or "").strip() if isinstance(parent.get("data_source_id"), str) else ""

    invalid_db = database_id.lower() in placeholder_values
    invalid_page = page_id.lower() in placeholder_values
    has_valid_shape = bool(workspace is True or data_source_id or (database_id and not invalid_db) or (page_id and not invalid_page))
    if not has_valid_shape:
        payload["parent"] = _default_notion_parent()
    return payload


def _normalize_notion_payload(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)

    # LLM often emits `sort` while Notion query endpoints expect `sorts`.
    if tool_name in {"notion_query_data_source", "notion_query_database"}:
        sort_alias = normalized.pop("sort", None)
        if "sorts" not in normalized and sort_alias is not None:
            if isinstance(sort_alias, list):
                normalized["sorts"] = sort_alias
            elif isinstance(sort_alias, dict):
                normalized["sorts"] = [sort_alias]

    # Invalid/empty cursors frequently cause repetitive autonomous failures.
    if "start_cursor" in normalized:
        cursor = normalized.get("start_cursor")
        if not isinstance(cursor, str) or not cursor.strip():
            normalized.pop("start_cursor", None)

    return normalized


async def _execute_notion_http(user_id: str, tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    token = _load_oauth_access_token(user_id=user_id, provider="notion")
    path = _build_path(tool.path, payload)
    body_or_query = _strip_path_params(tool.path, payload)
    url = f"{tool.base_url}{path}"

    headers = _notion_headers(token)
    method = tool.method.upper()
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=body_or_query)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json"
            response = await client.request(method, url, headers=headers, json=body_or_query)

    if response.status_code >= 400:
        mapped = tool.error_map.get(str(response.status_code), "TOOL_FAILED")
        # Preserve compact error code prefix for existing handlers,
        # and append upstream diagnostics for faster debugging.
        upstream_code = ""
        upstream_message = ""
        upstream_request_id = response.headers.get("x-notion-request-id", "")
        try:
            err_payload = response.json()
            upstream_code = str(err_payload.get("code", "") or "")
            upstream_message = str(err_payload.get("message", "") or "")
            if not upstream_request_id:
                upstream_request_id = str(err_payload.get("request_id", "") or "")
        except JSONDecodeError:
            upstream_message = response.text[:300]

        extra = (
            f"|status={response.status_code}"
            f"|code={upstream_code}"
            f"|message={upstream_message}"
            f"|request_id={upstream_request_id}"
        )
        raise HTTPException(status_code=400, detail=f"{tool.tool_name}:{mapped}{extra}")
    return _parse_response_data(response)


async def _execute_notion_oauth_http(tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{tool.base_url}{tool.path}"
    headers = _notion_oauth_headers()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        mapped = tool.error_map.get(str(response.status_code), "TOOL_FAILED")
        raise HTTPException(status_code=400, detail=f"{tool.tool_name}:{mapped}|status={response.status_code}")
    return _parse_response_data(response)


async def _execute_spotify_http(user_id: str, tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    token = _load_oauth_access_token(user_id=user_id, provider="spotify")
    path = _build_path(tool.path, payload)
    body_or_query = _strip_path_params(tool.path, payload)
    url = f"{tool.base_url}{path}"

    headers = {
        "Authorization": f"Bearer {token}",
    }
    method = tool.method.upper()
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=body_or_query)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json"
            response = await client.request(method, url, headers=headers, json=body_or_query)

    if response.status_code >= 400:
        mapped = tool.error_map.get(str(response.status_code), "TOOL_FAILED")
        upstream_message = ""
        try:
            err_payload = response.json()
            upstream_message = str(err_payload.get("error", {}).get("message", "") or "")
        except JSONDecodeError:
            upstream_message = response.text[:300]
        raise HTTPException(
            status_code=400,
            detail=f"{tool.tool_name}:{mapped}|status={response.status_code}|message={upstream_message}",
        )
    return _parse_response_data(response)


def _linear_query_and_variables(tool_name: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if tool_name == "linear_get_viewer":
        return (
            """
            query Viewer {
              viewer {
                id
                name
                email
              }
            }
            """,
            {},
        )
    if tool_name == "linear_list_issues":
        first = int(payload.get("first", 5))
        return (
            """
            query Issues($first: Int!) {
              issues(first: $first, orderBy: updatedAt) {
                nodes {
                  id
                  identifier
                  title
                  url
                  priority
                  state {
                    name
                  }
                  assignee {
                    name
                  }
                }
              }
            }
            """,
            {"first": max(1, min(20, first))},
        )
    if tool_name == "linear_search_issues":
        first = int(payload.get("first", 5))
        query = str(payload.get("query", "")).strip()
        return (
            """
            query SearchIssues($query: String!, $first: Int!) {
              issues(
                first: $first,
                orderBy: updatedAt,
                filter: {
                  title: { containsIgnoreCase: $query }
                }
              ) {
                nodes {
                  id
                  identifier
                  title
                  url
                  state {
                    name
                  }
                }
              }
            }
            """,
            {"query": query, "first": max(1, min(20, first))},
        )
    if tool_name == "linear_create_issue":
        input_data: dict[str, Any] = {
            "teamId": str(payload.get("team_id", "")),
            "title": str(payload.get("title", "")),
            "description": str(payload.get("description", "")),
        }
        if payload.get("priority") is not None:
            input_data["priority"] = int(payload.get("priority", 0))
        return (
            """
            mutation CreateIssue($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  url
                }
              }
            }
            """,
            {"input": input_data},
        )
    if tool_name == "linear_list_teams":
        first = int(payload.get("first", 10))
        return (
            """
            query Teams($first: Int!) {
              teams(first: $first) {
                nodes {
                  id
                  key
                  name
                }
              }
            }
            """,
            {"first": max(1, min(20, first))},
        )
    if tool_name == "linear_update_issue":
        issue_id = str(payload.get("issue_id", "")).strip()
        input_data: dict[str, Any] = {"id": issue_id}
        if payload.get("title") is not None:
            input_data["title"] = str(payload.get("title", ""))
        if payload.get("description") is not None:
            input_data["description"] = str(payload.get("description", ""))
        if payload.get("priority") is not None:
            input_data["priority"] = int(payload.get("priority", 0))
        if payload.get("state_id") is not None:
            input_data["stateId"] = str(payload.get("state_id", ""))
        return (
            """
            mutation UpdateIssue($input: IssueUpdateInput!) {
              issueUpdate(input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  url
                  state {
                    name
                  }
                }
              }
            }
            """,
            {"input": input_data},
        )
    if tool_name == "linear_create_comment":
        return (
            """
            mutation CreateComment($input: CommentCreateInput!) {
              commentCreate(input: $input) {
                success
                comment {
                  id
                  body
                  url
                }
              }
            }
            """,
            {
                "input": {
                    "issueId": str(payload.get("issue_id", "")),
                    "body": str(payload.get("body", "")),
                }
            },
        )
    raise HTTPException(status_code=400, detail=f"{tool_name}:NOT_IMPLEMENTED")


async def _execute_linear_http(user_id: str, tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    token = _load_oauth_access_token(user_id=user_id, provider="linear")
    query, variables = _linear_query_and_variables(tool.tool_name, payload)
    url = f"{tool.base_url}/graphql"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json={"query": query, "variables": variables})

    if response.status_code >= 400:
        mapped = tool.error_map.get(str(response.status_code), "TOOL_FAILED")
        raise HTTPException(
            status_code=400,
            detail=f"{tool.tool_name}:{mapped}|status={response.status_code}|message={response.text[:300]}",
        )

    try:
        data = response.json()
    except JSONDecodeError:
        raise HTTPException(status_code=400, detail=f"{tool.tool_name}:TOOL_FAILED|invalid_json")

    if data.get("errors"):
        errors = data.get("errors") or []
        first = errors[0] if isinstance(errors, list) and errors else {}
        message = str(first.get("message") or str(errors))[:300] if isinstance(first, dict) else str(errors)[:300]
        code = ""
        if isinstance(first, dict):
            code = str((first.get("extensions") or {}).get("code") or "")
        detail = f"{tool.tool_name}:TOOL_FAILED|message={message}"
        if code:
            detail = f"{detail}|code={code}"
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "data": data.get("data", {})}


def _build_default_headers_for_service(user_id: str, tool: ToolDefinition) -> dict[str, str]:
    headers: dict[str, str] = {}
    if tool.service == "notion":
        token = _load_oauth_access_token(user_id=user_id, provider="notion")
        headers.update(_notion_headers(token))
    elif tool.service == "spotify":
        token = _load_oauth_access_token(user_id=user_id, provider="spotify")
        headers["Authorization"] = f"Bearer {token}"
    elif tool.required_scopes:
        # Generic OAuth-style provider: when scopes are required, expect provider token.
        token = _load_oauth_access_token(user_id=user_id, provider=tool.service)
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _execute_generic_http(user_id: str, tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    path = _build_path(tool.path, payload)
    body_or_query = _strip_path_params(tool.path, payload)
    url = f"{tool.base_url}{path}"
    headers = _build_default_headers_for_service(user_id=user_id, tool=tool)
    method = tool.method.upper()

    async with httpx.AsyncClient(timeout=20) as client:
        if method == "GET":
            response = await client.get(url, headers=headers, params=body_or_query)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json"
            response = await client.request(method, url, headers=headers, json=body_or_query)

    if response.status_code >= 400:
        mapped = tool.error_map.get(str(response.status_code), "TOOL_FAILED")
        raise HTTPException(status_code=400, detail=f"{tool.tool_name}:{mapped}")
    return _parse_response_data(response)


async def _execute_notion_service(user_id: str, tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    if tool.tool_name.startswith("notion_oauth_token_"):
        return await _execute_notion_oauth_http(tool=tool, payload=payload)
    return await _execute_notion_http(user_id=user_id, tool=tool, payload=payload)


ServiceExecutor = Callable[[str, ToolDefinition, dict[str, Any]], Awaitable[dict[str, Any]]]


_SERVICE_EXECUTORS: dict[str, ServiceExecutor] = {
    "notion": _execute_notion_service,
    "spotify": _execute_spotify_http,
    "linear": _execute_linear_http,
}


def _normalize_payload_for_tool(tool: ToolDefinition, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if tool.service != "notion":
        return normalized
    normalized = _normalize_notion_payload(tool.tool_name, normalized)
    if tool.tool_name == "notion_create_page":
        normalized = _normalize_notion_create_page_payload(normalized)
    return normalized


async def execute_tool(user_id: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    registry = load_registry()
    tool = registry.get_tool(tool_name)
    payload = _normalize_payload_for_tool(tool, payload)
    _validate_payload_by_schema(tool, payload)
    executor = _SERVICE_EXECUTORS.get(tool.service)
    if executor:
        return await executor(user_id, tool, payload)
    return await _execute_generic_http(user_id=user_id, tool=tool, payload=payload)
