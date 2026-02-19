from __future__ import annotations

import re
from json import JSONDecodeError
from typing import Any

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
        raise HTTPException(status_code=400, detail=f"{tool.tool_name}:{mapped}")
    return _parse_response_data(response)


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


async def execute_tool(user_id: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    registry = load_registry()
    tool = registry.get_tool(tool_name)
    _validate_payload_by_schema(tool, payload)
    if tool.service == "notion":
        return await _execute_notion_http(user_id=user_id, tool=tool, payload=payload)
    if tool.service == "spotify":
        return await _execute_spotify_http(user_id=user_id, tool=tool, payload=payload)
    return await _execute_generic_http(user_id=user_id, tool=tool, payload=payload)
