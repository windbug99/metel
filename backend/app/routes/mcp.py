from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from supabase import create_client

from agent.registry import ToolDefinition, load_registry
from agent.tool_runner import execute_tool
from app.core.api_keys import API_KEY_PREFIX, hash_api_key
from app.core.config import get_settings

router = APIRouter(prefix="/mcp", tags=["mcp"])

_PHASE1_SERVICES = {"notion", "linear"}
_RATE_LIMIT_PER_MINUTE = 30


def _jsonrpc_error(
    *,
    req_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    if data:
        payload["error"]["data"] = data
    return JSONResponse(status_code=status_code, content=payload)


def _extract_oauth_scope_map(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    scopes: dict[str, set[str]] = {}
    for row in rows:
        provider = str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        items = row.get("granted_scopes")
        if not isinstance(items, list):
            continue
        scopes[provider] = {str(item).strip() for item in items if str(item).strip()}
    return scopes


async def _authenticate_api_key(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_api_key")

    raw_key = authorization.removeprefix("Bearer ").strip()
    if not raw_key.startswith(API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="invalid_api_key_format")

    key_hash = hash_api_key(raw_key)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    result = (
        supabase.table("api_keys")
        .select("id,user_id,is_active,allowed_tools")
        .eq("key_hash", key_hash)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    api_key = rows[0]
    if not api_key.get("is_active"):
        raise HTTPException(status_code=401, detail="api_key_revoked")

    (
        supabase.table("api_keys")
        .update({"last_used_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", api_key["id"])
        .execute()
    )
    return api_key


def _map_tool_error(exc: HTTPException) -> tuple[int, str, dict[str, Any] | None]:
    detail = str(exc.detail or "")
    if detail.startswith("Unknown tool:"):
        return 4041, "tool_not_found", None
    if ":VALIDATION_REQUIRED:" in detail:
        field = detail.rsplit(":", 1)[-1]
        return 4001, "missing_required_field", {"field": field}
    if ":VALIDATION_TYPE:" in detail:
        field = detail.rsplit(":", 1)[-1]
        return 4002, "invalid_field_type", {"field": field}
    if detail.endswith("_not_connected"):
        provider = detail.removesuffix("_not_connected")
        return 4003, "oauth_not_connected", {"provider": provider}
    return 5001, "tool_execution_failed", {"detail": detail}


def _log_tool_call(
    *,
    supabase,
    request_id: str,
    user_id: str,
    api_key_id: str,
    tool_name: str,
    status: str,
    error_code: str | None,
    latency_ms: int,
) -> None:
    supabase.table("tool_calls").insert(
        {
            "request_id": request_id,
            "user_id": user_id,
            "api_key_id": api_key_id,
            "tool_name": tool_name,
            "status": status,
            "error_code": error_code,
            "latency_ms": latency_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def _is_rate_limited(*, supabase, api_key_id: str) -> bool:
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    query = (
        supabase.table("tool_calls")
        .select("id", count="exact")
        .eq("api_key_id", api_key_id)
        .gte("created_at", since)
        .limit(_RATE_LIMIT_PER_MINUTE + 1)
        .execute()
    )
    count = getattr(query, "count", None)
    if isinstance(count, int):
        return count >= _RATE_LIMIT_PER_MINUTE
    rows = query.data or []
    return len(rows) >= _RATE_LIMIT_PER_MINUTE


def _phase1_filter_tools(tools: list[ToolDefinition]) -> list[ToolDefinition]:
    return [tool for tool in tools if tool.service in _PHASE1_SERVICES]


def _api_key_allowed_set(api_key: dict[str, Any]) -> set[str] | None:
    raw = api_key.get("allowed_tools")
    if not isinstance(raw, list):
        return None
    allowed = {str(item).strip() for item in raw if str(item).strip()}
    return allowed or None


def _apply_allowed_tools(tools: list[ToolDefinition], api_key: dict[str, Any]) -> list[ToolDefinition]:
    allowed = _api_key_allowed_set(api_key)
    if not allowed:
        return tools
    return [tool for tool in tools if tool.tool_name in allowed]


@router.post("/list_tools")
async def mcp_list_tools(
    request: Request,
    authorization: str | None = Header(default=None),
):
    body = await request.json()
    req_id = body.get("id")
    if body.get("method") != "list_tools":
        return _jsonrpc_error(req_id=req_id, code=4000, message="invalid_method", data={"expected": "list_tools"})

    api_key = await _authenticate_api_key(authorization)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    token_rows = (
        supabase.table("oauth_tokens")
        .select("provider,granted_scopes")
        .eq("user_id", api_key["user_id"])
        .execute()
    ).data or []
    connected_services = sorted({str(row.get("provider") or "").strip().lower() for row in token_rows if row.get("provider")})
    scope_map = _extract_oauth_scope_map(token_rows)

    registry = load_registry()
    tools = _apply_allowed_tools(
        _phase1_filter_tools(
            registry.list_available_tools(
                connected_services=connected_services,
                granted_scopes=scope_map,
            )
        ),
        api_key,
    )

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"tools": [tool.to_llm_tool() for tool in tools]},
    }


@router.post("/call_tool")
async def mcp_call_tool(
    request: Request,
    authorization: str | None = Header(default=None),
):
    body = await request.json()
    req_id = body.get("id")
    if body.get("method") != "call_tool":
        return _jsonrpc_error(req_id=req_id, code=4000, message="invalid_method", data={"expected": "call_tool"})

    params = body.get("params")
    if not isinstance(params, dict):
        return _jsonrpc_error(req_id=req_id, code=4004, message="invalid_params")
    tool_name = str(params.get("name") or "").strip()
    arguments = params.get("arguments")
    if not tool_name:
        return _jsonrpc_error(req_id=req_id, code=4005, message="missing_tool_name")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _jsonrpc_error(req_id=req_id, code=4006, message="invalid_arguments")

    api_key = await _authenticate_api_key(authorization)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    if _is_rate_limited(supabase=supabase, api_key_id=api_key["id"]):
        return _jsonrpc_error(req_id=req_id, code=4290, message="rate_limit_exceeded")

    request_id = getattr(request.state, "request_id", "")
    started = time.perf_counter()
    try:
        tool = load_registry().get_tool(tool_name)
        if tool.service not in _PHASE1_SERVICES:
            return _jsonrpc_error(req_id=req_id, code=4042, message="tool_not_available_in_phase1")
        allowed = _api_key_allowed_set(api_key)
        if allowed is not None and tool_name not in allowed:
            return _jsonrpc_error(req_id=req_id, code=4031, message="tool_not_allowed_for_api_key")

        result = await execute_tool(user_id=api_key["user_id"], tool_name=tool_name, payload=arguments)
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            status="success",
            error_code=None,
            latency_ms=latency_ms,
        )
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except HTTPException as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        code, message, data = _map_tool_error(exc)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            status="fail",
            error_code=message,
            latency_ms=latency_ms,
        )
        return _jsonrpc_error(req_id=req_id, code=code, message=message, data=data)
