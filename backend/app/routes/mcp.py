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
from app.core.error_codes import (
    CODE_ACCESS_DENIED,
    CODE_POLICY_BLOCKED,
    CODE_QUOTA_EXCEEDED,
    CODE_RESOLVE_AMBIGUOUS,
    CODE_RESOLVE_NOT_FOUND,
    CODE_SERVICE_NOT_ALLOWED,
    CODE_TOOL_NOT_ALLOWED,
    CODE_UPSTREAM_TEMPORARY_FAILURE,
    ERR_ACCESS_DENIED,
    ERR_POLICY_BLOCKED,
    ERR_POLICY_OVERRIDE_ALLOWED,
    ERR_QUOTA_EXCEEDED,
    ERR_RESOLVE_NOT_FOUND,
    ERR_SERVICE_NOT_ALLOWED,
    ERR_UPSTREAM_TEMPORARY_FAILURE,
)
from app.core.event_hooks import emit_webhook_event
from app.core.quota import evaluate_daily_quota
from app.core.resolver import ResolverException, resolve_tool_payload
from app.core.retry_policy import run_with_retry
from app.core.risk_gate import evaluate_risk_with_policy

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
        .select("id,user_id,is_active,team_id,allowed_tools,policy_json")
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
    status = _extract_upstream_status(detail)
    if ":RATE_LIMITED" in detail or status in {429, 500, 502, 503, 504}:
        return (
            CODE_UPSTREAM_TEMPORARY_FAILURE,
            ERR_UPSTREAM_TEMPORARY_FAILURE,
            {"status": status, "retryable": True},
        )
    return 5001, "tool_execution_failed", {"detail": detail}


def _extract_upstream_status(detail: str) -> int | None:
    marker = "|status="
    if marker not in detail:
        return None
    tail = detail.split(marker, 1)[1]
    code_text = tail.split("|", 1)[0].strip()
    try:
        return int(code_text)
    except ValueError:
        return None


def _connector_from_tool_name(tool_name: str) -> str:
    value = str(tool_name or "").strip().lower()
    if value.startswith("notion_"):
        return "notion"
    if value.startswith("linear_"):
        return "linear"
    return "other"


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
    trace_id: str | None = None,
    connector: str | None = None,
    request_payload: dict[str, Any] | None = None,
    resolved_payload: dict[str, Any] | None = None,
    risk_result: dict[str, Any] | None = None,
    upstream_status: int | None = None,
    retry_count: int | None = None,
    backoff_ms: int | None = None,
    masked_fields: list[str] | None = None,
) -> None:
    query = supabase.table("tool_calls")
    if not hasattr(query, "insert"):
        return
    query.insert(
        {
            "request_id": request_id,
            "trace_id": trace_id or request_id,
            "user_id": user_id,
            "api_key_id": api_key_id,
            "tool_name": tool_name,
            "connector": connector,
            "status": status,
            "error_code": error_code,
            "latency_ms": latency_ms,
            "request_payload": request_payload,
            "resolved_payload": resolved_payload,
            "risk_result": risk_result,
            "upstream_status": upstream_status,
            "retry_count": retry_count if retry_count is not None else 0,
            "backoff_ms": backoff_ms if backoff_ms is not None else 0,
            "masked_fields": masked_fields or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def _masked_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    masked = dict(payload)
    masked_fields: list[str] = []
    for key in list(masked.keys()):
        lowered = str(key).strip().lower()
        if lowered in {"token", "access_token", "authorization", "password", "secret"}:
            masked[key] = "***"
            masked_fields.append(str(key))
    return masked, masked_fields


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


def _api_key_policy(api_key: dict[str, Any]) -> dict[str, Any] | None:
    effective = api_key.get("effective_policy_json")
    if isinstance(effective, dict):
        return effective
    raw = api_key.get("policy_json")
    return raw if isinstance(raw, dict) else None


def _normalized_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    out: dict[str, Any] = {}
    if "allow_high_risk" in policy:
        out["allow_high_risk"] = bool(policy.get("allow_high_risk"))
    for key in ("allowed_services", "deny_tools", "allowed_linear_team_ids"):
        raw = policy.get(key)
        if not isinstance(raw, list):
            continue
        values = [str(item).strip() for item in raw if str(item).strip()]
        if key == "allowed_services":
            values = [item.lower() for item in values]
        out[key] = values
    return out


def _merge_team_and_key_policy(team_policy: dict[str, Any] | None, key_policy: dict[str, Any] | None) -> dict[str, Any]:
    team = _normalized_policy(team_policy)
    key = _normalized_policy(key_policy)
    if not team and not key:
        return {}

    merged: dict[str, Any] = {}
    if "allow_high_risk" in key:
        merged["allow_high_risk"] = bool(key["allow_high_risk"])
    elif "allow_high_risk" in team:
        merged["allow_high_risk"] = bool(team["allow_high_risk"])

    def _merge_allowlist(field: str) -> list[str] | None:
        team_values = set(team.get(field) or []) if isinstance(team.get(field), list) else None
        key_values = set(key.get(field) or []) if isinstance(key.get(field), list) else None
        if team_values is not None and key_values is not None:
            return sorted(team_values.intersection(key_values))
        if key_values is not None:
            return sorted(key_values)
        if team_values is not None:
            return sorted(team_values)
        return None

    allowed_services = _merge_allowlist("allowed_services")
    if allowed_services is not None:
        merged["allowed_services"] = allowed_services

    allowed_linear_team_ids = _merge_allowlist("allowed_linear_team_ids")
    if allowed_linear_team_ids is not None:
        merged["allowed_linear_team_ids"] = allowed_linear_team_ids

    team_deny = set(team.get("deny_tools") or []) if isinstance(team.get("deny_tools"), list) else set()
    key_deny = set(key.get("deny_tools") or []) if isinstance(key.get("deny_tools"), list) else set()
    deny_tools = sorted(team_deny.union(key_deny))
    if deny_tools:
        merged["deny_tools"] = deny_tools
    return merged


def _load_team_policy(supabase, *, team_id: int | str | None) -> dict[str, Any] | None:
    if not team_id:
        return None
    rows = (
        supabase.table("team_policies")
        .select("policy_json")
        .eq("team_id", team_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    raw = rows[0].get("policy_json")
    return raw if isinstance(raw, dict) else None


def _with_effective_policy(supabase, *, api_key: dict[str, Any]) -> dict[str, Any]:
    next_api_key = dict(api_key)
    next_api_key["effective_policy_json"] = _merge_team_and_key_policy(
        _load_team_policy(supabase, team_id=api_key.get("team_id")),
        api_key.get("policy_json") if isinstance(api_key.get("policy_json"), dict) else None,
    )
    return next_api_key


def _policy_allowed_services(api_key: dict[str, Any]) -> set[str] | None:
    policy = _api_key_policy(api_key)
    if not policy:
        return None
    items = policy.get("allowed_services")
    if not isinstance(items, list):
        return None
    services = {str(item).strip().lower() for item in items if str(item).strip()}
    return services or None


def _policy_deny_tools(api_key: dict[str, Any]) -> set[str]:
    policy = _api_key_policy(api_key)
    if not policy:
        return set()
    items = policy.get("deny_tools")
    if not isinstance(items, list):
        return set()
    return {str(item).strip() for item in items if str(item).strip()}


def _policy_allowed_linear_team_ids(api_key: dict[str, Any]) -> set[str] | None:
    policy = _api_key_policy(api_key)
    if not policy:
        return None
    items = policy.get("allowed_linear_team_ids")
    if not isinstance(items, list):
        return None
    team_ids = {str(item).strip() for item in items if str(item).strip()}
    return team_ids or None


def _apply_policy_filters(tools: list[ToolDefinition], api_key: dict[str, Any]) -> list[ToolDefinition]:
    allowed_services = _policy_allowed_services(api_key)
    deny_tools = _policy_deny_tools(api_key)
    filtered = tools
    if allowed_services:
        filtered = [tool for tool in filtered if tool.service in allowed_services]
    if deny_tools:
        filtered = [tool for tool in filtered if str(getattr(tool, "tool_name", getattr(tool, "_name", ""))) not in deny_tools]
    return filtered


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
    api_key = _with_effective_policy(supabase, api_key=api_key)

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
        _apply_policy_filters(
            _phase1_filter_tools(
                registry.list_available_tools(
                    connected_services=connected_services,
                    granted_scopes=scope_map,
                )
            ),
            api_key,
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
    api_key = _with_effective_policy(supabase, api_key=api_key)
    request_id = getattr(request.state, "request_id", "")
    started = time.perf_counter()
    masked_request_payload, masked_fields = _masked_payload(arguments)

    if _is_rate_limited(supabase=supabase, api_key_id=api_key["id"]):
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            connector=_connector_from_tool_name(tool_name),
            status="fail",
            error_code="rate_limit_exceeded",
            latency_ms=latency_ms,
            request_payload=masked_request_payload,
            resolved_payload=None,
            risk_result=None,
            retry_count=0,
            backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
            masked_fields=masked_fields,
        )
        await emit_webhook_event(
            supabase=supabase,
            user_id=api_key["user_id"],
            event_type="rate_limit_exceeded",
            payload={"request_id": request_id, "api_key_id": api_key["id"], "tool_name": tool_name},
        )
        return _jsonrpc_error(req_id=req_id, code=4290, message="rate_limit_exceeded")
    await emit_webhook_event(
        supabase=supabase,
        user_id=api_key["user_id"],
        event_type="tool_called",
        payload={
            "request_id": request_id,
            "api_key_id": api_key["id"],
            "tool_name": tool_name,
            "connector": _connector_from_tool_name(tool_name),
        },
    )
    resolved_arguments: dict[str, Any] | None = None
    risk_result: dict[str, Any] | None = None
    quota = evaluate_daily_quota(
        supabase=supabase,
        user_id=api_key["user_id"],
        api_key_id=api_key["id"],
        per_key_daily_limit=max(0, int(getattr(settings, "mcp_quota_per_key_daily", 0))),
        per_user_daily_limit=max(0, int(getattr(settings, "mcp_quota_per_user_daily", 0))),
    )
    if quota.exceeded:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            connector="other",
            status="fail",
            error_code=ERR_QUOTA_EXCEEDED,
            latency_ms=latency_ms,
            request_payload=masked_request_payload,
            resolved_payload=None,
            risk_result=None,
            retry_count=0,
            backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
            masked_fields=masked_fields,
        )
        await emit_webhook_event(
            supabase=supabase,
            user_id=api_key["user_id"],
            event_type="quota_exceeded",
            payload={"request_id": request_id, "api_key_id": api_key["id"], "tool_name": tool_name},
        )
        return _jsonrpc_error(
            req_id=req_id,
            code=CODE_QUOTA_EXCEEDED,
            message=ERR_QUOTA_EXCEEDED,
            data={"scope": quota.scope, "limit": quota.limit, "used": quota.used},
        )

    try:
        tool = load_registry().get_tool(tool_name)
        if tool.service not in _PHASE1_SERVICES:
            return _jsonrpc_error(req_id=req_id, code=4042, message="tool_not_available_in_phase1")
        allowed = _api_key_allowed_set(api_key)
        if allowed is not None and tool_name not in allowed:
            return _jsonrpc_error(req_id=req_id, code=CODE_TOOL_NOT_ALLOWED, message="tool_not_allowed_for_api_key")
        deny_tools = _policy_deny_tools(api_key)
        if tool_name in deny_tools:
            return _jsonrpc_error(req_id=req_id, code=CODE_ACCESS_DENIED, message=ERR_ACCESS_DENIED)
        allowed_services = _policy_allowed_services(api_key)
        if allowed_services is not None and tool.service not in allowed_services:
            return _jsonrpc_error(
                req_id=req_id,
                code=CODE_SERVICE_NOT_ALLOWED,
                message=ERR_SERVICE_NOT_ALLOWED,
                data={"service": tool.service},
            )
        risk = evaluate_risk_with_policy(
            tool_name=tool_name,
            payload=arguments,
            policy=_api_key_policy(api_key),
        )
        risk_result = {"allowed": risk.allowed, "reason": risk.reason, "risk_type": risk.risk_type}
        if not risk.allowed:
            latency_ms = int((time.perf_counter() - started) * 1000)
            _log_tool_call(
                supabase=supabase,
                request_id=request_id,
                user_id=api_key["user_id"],
                api_key_id=api_key["id"],
                tool_name=tool_name,
                connector=tool.service,
                status="fail",
                error_code=ERR_POLICY_BLOCKED,
                latency_ms=latency_ms,
                request_payload=masked_request_payload,
                resolved_payload=None,
                risk_result=risk_result,
                retry_count=0,
                backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
                masked_fields=masked_fields,
            )
            await emit_webhook_event(
                supabase=supabase,
                user_id=api_key["user_id"],
                event_type="policy_blocked",
                payload={
                    "request_id": request_id,
                    "api_key_id": api_key["id"],
                    "tool_name": tool_name,
                    "reason": risk.reason,
                    "risk_type": risk.risk_type,
                },
            )
            return _jsonrpc_error(
                req_id=req_id,
                code=CODE_POLICY_BLOCKED,
                message=ERR_POLICY_BLOCKED,
                data={"reason": risk.reason, "risk_type": risk.risk_type},
            )
        resolved_arguments = await resolve_tool_payload(
            user_id=api_key["user_id"],
            tool_name=tool_name,
            payload=arguments,
            execute_tool=execute_tool,
        )
        masked_resolved_payload, _ = _masked_payload(resolved_arguments)
        allowed_linear_team_ids = _policy_allowed_linear_team_ids(api_key)
        if tool.service == "linear" and allowed_linear_team_ids is not None:
            team_id = str(resolved_arguments.get("team_id") or "").strip()
            if team_id and team_id not in allowed_linear_team_ids:
                latency_ms = int((time.perf_counter() - started) * 1000)
                _log_tool_call(
                    supabase=supabase,
                    request_id=request_id,
                    user_id=api_key["user_id"],
                    api_key_id=api_key["id"],
                    tool_name=tool_name,
                    connector=tool.service,
                    status="fail",
                    error_code=ERR_ACCESS_DENIED,
                    latency_ms=latency_ms,
                    request_payload=masked_request_payload,
                    resolved_payload=masked_resolved_payload,
                    risk_result=risk_result,
                    retry_count=0,
                    backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
                    masked_fields=masked_fields,
                )
                return _jsonrpc_error(
                    req_id=req_id,
                    code=CODE_ACCESS_DENIED,
                    message=ERR_ACCESS_DENIED,
                    data={"reason": "team_not_allowed", "team_id": team_id},
                )
        max_retries = max(0, int(getattr(settings, "mcp_retry_max_retries", 1)))
        backoff_ms = max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250)))
        retried = await run_with_retry(
            operation=lambda: execute_tool(user_id=api_key["user_id"], tool_name=tool_name, payload=resolved_arguments),
            max_retries=max_retries,
            backoff_ms=backoff_ms,
        )
        result = retried.data
        success_error_code: str | None = None
        if risk.reason == "policy_override_high_risk":
            success_error_code = ERR_POLICY_OVERRIDE_ALLOWED
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            connector=tool.service,
            status="success",
            error_code=success_error_code,
            latency_ms=latency_ms,
            request_payload=masked_request_payload,
            resolved_payload=masked_resolved_payload,
            risk_result=risk_result,
            retry_count=int(retried.retry_count),
            backoff_ms=backoff_ms,
            masked_fields=masked_fields,
        )
        await emit_webhook_event(
            supabase=supabase,
            user_id=api_key["user_id"],
            event_type="tool_succeeded",
            payload={
                "request_id": request_id,
                "api_key_id": api_key["id"],
                "tool_name": tool_name,
                "connector": tool.service,
                "retry_count": int(retried.retry_count),
            },
        )
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except ResolverException as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            connector=_connector_from_tool_name(tool_name),
            status="fail",
            error_code=exc.error_code,
            latency_ms=latency_ms,
            request_payload=masked_request_payload,
            resolved_payload=None,
            risk_result=risk_result,
            retry_count=0,
            backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
            masked_fields=masked_fields,
        )
        await emit_webhook_event(
            supabase=supabase,
            user_id=api_key["user_id"],
            event_type="tool_failed",
            payload={
                "request_id": request_id,
                "api_key_id": api_key["id"],
                "tool_name": tool_name,
                "error_code": exc.error_code,
            },
        )
        return _jsonrpc_error(
            req_id=req_id,
            code=CODE_RESOLVE_NOT_FOUND if exc.error_code == ERR_RESOLVE_NOT_FOUND else CODE_RESOLVE_AMBIGUOUS,
            message=exc.message,
            data=exc.data,
        )
    except HTTPException as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        code, message, data = _map_tool_error(exc)
        upstream_status = _extract_upstream_status(str(exc.detail or ""))
        masked_resolved_payload: dict[str, Any] | None = None
        if isinstance(resolved_arguments, dict):
            masked_resolved_payload, _ = _masked_payload(resolved_arguments)
        _log_tool_call(
            supabase=supabase,
            request_id=request_id,
            user_id=api_key["user_id"],
            api_key_id=api_key["id"],
            tool_name=tool_name,
            connector=_connector_from_tool_name(tool_name),
            status="fail",
            error_code=message,
            latency_ms=latency_ms,
            request_payload=masked_request_payload,
            resolved_payload=masked_resolved_payload,
            risk_result=risk_result,
            upstream_status=upstream_status,
            retry_count=0,
            backoff_ms=max(0, int(getattr(settings, "mcp_retry_backoff_ms", 250))),
            masked_fields=masked_fields,
        )
        await emit_webhook_event(
            supabase=supabase,
            user_id=api_key["user_id"],
            event_type="tool_failed",
            payload={
                "request_id": request_id,
                "api_key_id": api_key["id"],
                "tool_name": tool_name,
                "error_code": message,
                "upstream_status": upstream_status,
            },
        )
        return _jsonrpc_error(req_id=req_id, code=code, message=message, data=data)
