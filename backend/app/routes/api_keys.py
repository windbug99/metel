from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from supabase import create_client

from agent.registry import load_registry
from app.core.api_keys import generate_api_key, hash_api_key
from app.core.auth import get_authenticated_user_id
from app.core.authz import AuthzContext, Role, get_authz_context, require_min_role
from app.core.config import get_settings
from app.core.error_codes import ERR_POLICY_CONFLICT

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])
_PHASE1_SERVICES = {"notion", "linear"}
_MEMBER_ALLOWED_POLICY_KEYS = {"allowed_services", "deny_tools"}


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=100)
    allowed_tools: list[str] | None = None
    policy_json: dict[str, Any] | None = None
    memo: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    team_id: int | None = None


class UpdateApiKeyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_tools: list[str] | None = None
    policy_json: dict[str, Any] | None = None
    memo: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    team_id: int | None = None
    is_active: bool | None = None


def _phase1_tool_names() -> set[str]:
    registry = load_registry()
    return {tool.tool_name for tool in registry.list_tools() if tool.service in _PHASE1_SERVICES}


def _phase1_tool_service_map() -> dict[str, str]:
    registry = load_registry()
    return {
        str(tool.tool_name): str(tool.service)
        for tool in registry.list_tools()
        if str(tool.service) in _PHASE1_SERVICES and str(tool.tool_name).strip()
    }


def _phase1_tool_options() -> list[dict[str, str]]:
    registry = load_registry()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for tool in registry.list_tools():
        service = str(tool.service)
        name = str(tool.tool_name).strip()
        if service not in _PHASE1_SERVICES or not name or name in seen:
            continue
        seen.add(name)
        rows.append({"tool_name": name, "service": service})
    rows.sort(key=lambda item: item["tool_name"])
    return rows


def _normalize_allowed_tools(raw_tools: list[str] | None) -> list[str] | None:
    if raw_tools is None:
        return None
    phase1_tools = _phase1_tool_names()
    seen: set[str] = set()
    normalized: list[str] = []
    for tool_name in raw_tools:
        name = str(tool_name or "").strip()
        if not name or name in seen:
            continue
        if name not in phase1_tools:
            raise HTTPException(status_code=400, detail=f"invalid_allowed_tool:{name}")
        seen.add(name)
        normalized.append(name)
    return normalized


def _normalize_tags(raw_tags: list[str] | None) -> list[str] | None:
    if raw_tags is None:
        return None
    if not isinstance(raw_tags, list):
        raise HTTPException(status_code=400, detail="invalid_tags")
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in raw_tags:
        value = str(tag or "").strip()
        if not value or value in seen:
            continue
        if len(value) > 40:
            raise HTTPException(status_code=400, detail="invalid_tag_too_long")
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_memo(raw_memo: str | None) -> str | None:
    if raw_memo is None:
        return None
    memo = str(raw_memo).strip()
    return memo or None


def _validate_team_id(*, supabase, authz_ctx: AuthzContext, user_id: str, team_id: int | None) -> int | None:
    if team_id is None:
        return None
    rows = (
        supabase.table("teams")
        .select("id,organization_id")
        .eq("id", team_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=400, detail="invalid_team_id")
    organization_id = rows[0].get("organization_id")
    try:
        organization_id_int = int(organization_id) if organization_id is not None else None
    except (TypeError, ValueError):
        organization_id_int = None
    has_org_scope = organization_id_int is not None and organization_id_int in authz_ctx.org_ids
    has_admin_scope = has_org_scope and authz_ctx.role in {Role.ADMIN, Role.OWNER}
    is_team_member = (
        supabase.table("team_memberships")
        .select("id")
        .eq("team_id", team_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not has_admin_scope and not is_team_member:
        raise HTTPException(status_code=400, detail="invalid_team_id")
    return team_id


def _normalize_api_key_policy(raw_policy: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw_policy is None:
        return None
    if not isinstance(raw_policy, dict):
        raise HTTPException(status_code=400, detail="invalid_policy_json")

    normalized: dict[str, Any] = {}
    allow_high_risk = raw_policy.get("allow_high_risk")
    if allow_high_risk is not None:
        normalized["allow_high_risk"] = bool(allow_high_risk)

    allowed_services = raw_policy.get("allowed_services")
    if allowed_services is not None:
        if not isinstance(allowed_services, list):
            raise HTTPException(status_code=400, detail="invalid_policy_json:allowed_services")
        services: list[str] = []
        seen_services: set[str] = set()
        for item in allowed_services:
            name = str(item or "").strip().lower()
            if not name or name in seen_services:
                continue
            if name not in _PHASE1_SERVICES:
                raise HTTPException(status_code=400, detail=f"invalid_allowed_service:{name}")
            seen_services.add(name)
            services.append(name)
        normalized["allowed_services"] = services

    deny_tools = raw_policy.get("deny_tools")
    if deny_tools is not None:
        if not isinstance(deny_tools, list):
            raise HTTPException(status_code=400, detail="invalid_policy_json:deny_tools")
        phase1_tools = _phase1_tool_names()
        tools: list[str] = []
        seen_tools: set[str] = set()
        for item in deny_tools:
            name = str(item or "").strip()
            if not name or name in seen_tools:
                continue
            if name not in phase1_tools:
                raise HTTPException(status_code=400, detail=f"invalid_deny_tool:{name}")
            seen_tools.add(name)
            tools.append(name)
        normalized["deny_tools"] = tools

    allowed_linear_team_ids = raw_policy.get("allowed_linear_team_ids")
    if allowed_linear_team_ids is not None:
        if not isinstance(allowed_linear_team_ids, list):
            raise HTTPException(status_code=400, detail="invalid_policy_json:allowed_linear_team_ids")
        team_ids: list[str] = []
        seen_team_ids: set[str] = set()
        for item in allowed_linear_team_ids:
            value = str(item or "").strip()
            if not value or value in seen_team_ids:
                continue
            seen_team_ids.add(value)
            team_ids.append(value)
        normalized["allowed_linear_team_ids"] = team_ids

    return normalized


def _validate_policy_conflict(
    *,
    allowed_tools: list[str] | None,
    policy_json: dict[str, Any] | None,
) -> None:
    if not policy_json:
        return

    allowed_services_raw = policy_json.get("allowed_services")
    if isinstance(allowed_services_raw, list) and allowed_services_raw:
        allowed_services = {str(item).strip().lower() for item in allowed_services_raw if str(item).strip()}
        if "allowed_linear_team_ids" in policy_json and "linear" not in allowed_services:
            raise HTTPException(
                status_code=409,
                detail=f"{ERR_POLICY_CONFLICT}:linear_team_policy_without_linear_service",
            )

    if not allowed_tools:
        return

    deny_tools_raw = policy_json.get("deny_tools")
    deny_tools = set(deny_tools_raw) if isinstance(deny_tools_raw, list) else set()
    overlap = sorted(set(allowed_tools).intersection(deny_tools))
    if overlap:
        raise HTTPException(
            status_code=409,
            detail=f"{ERR_POLICY_CONFLICT}:allowed_tool_in_deny_tools:{overlap[0]}",
        )

    if isinstance(allowed_services_raw, list) and allowed_services_raw:
        tool_service_map = _phase1_tool_service_map()
        for tool_name in allowed_tools:
            service = str(tool_service_map.get(tool_name, "")).strip().lower()
            if service and service not in allowed_services:
                raise HTTPException(
                    status_code=409,
                    detail=f"{ERR_POLICY_CONFLICT}:tool_outside_allowed_services:{tool_name}",
                )


def _enforce_member_api_key_write_policy(
    *,
    authz_ctx: AuthzContext,
    policy_json: dict[str, Any] | None,
) -> None:
    if authz_ctx.role != Role.MEMBER:
        return
    if policy_json is None:
        return
    extra_keys = sorted(set(policy_json.keys()) - _MEMBER_ALLOWED_POLICY_KEYS)
    if extra_keys:
        raise HTTPException(
            status_code=403,
            detail={"code": "access_denied", "reason": f"member_policy_key_forbidden:{extra_keys[0]}"},
        )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _p95_latency_ms(rows: list[dict[str, Any]]) -> int:
    latencies = sorted(int(item.get("latency_ms") or 0) for item in rows)
    if not latencies:
        return 0
    index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    return latencies[index]


def _iso_bucket_day(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d")


@router.get("")
async def list_api_keys(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    result = (
        supabase.table("api_keys")
        .select("id,name,key_prefix,team_id,allowed_tools,policy_json,memo,tags,issued_by,rotated_from,is_active,last_used_at,created_at,revoked_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    rows = result.data or []
    return {"items": rows, "count": len(rows)}


@router.get("/tool-options")
async def list_api_key_tool_options(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    return {"items": _phase1_tool_options()}


@router.get("/{key_id}/drilldown")
async def api_key_drilldown(
    request: Request,
    key_id: int,
    days: int = Query(7, ge=1, le=30),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    key_rows = (
        supabase.table("api_keys")
        .select("id,name,key_prefix")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not key_rows:
        raise HTTPException(status_code=404, detail="api_key_not_found")
    key = key_rows[0]

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("tool_calls")
        .select("tool_name,status,error_code,latency_ms,created_at")
        .eq("user_id", user_id)
        .eq("api_key_id", key_id)
        .gte("created_at", since)
        .execute()
    ).data or []

    total_calls = len(rows)
    success_count = len([item for item in rows if item.get("status") == "success"])
    fail_count = len([item for item in rows if item.get("status") == "fail"])
    avg_latency_ms = round(sum(int(item.get("latency_ms") or 0) for item in rows) / total_calls, 2) if total_calls else 0.0

    error_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    day_counts: dict[str, dict[str, int]] = {}
    for item in rows:
        error_code = str(item.get("error_code") or "").strip() or "none"
        error_counts[error_code] = error_counts.get(error_code, 0) + 1
        tool_name = str(item.get("tool_name") or "").strip() or "unknown_tool"
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        day = _iso_bucket_day(item.get("created_at"))
        bucket = day_counts.get(day) or {"calls": 0, "success": 0, "fail": 0}
        bucket["calls"] += 1
        if item.get("status") == "success":
            bucket["success"] += 1
        elif item.get("status") == "fail":
            bucket["fail"] += 1
        day_counts[day] = bucket

    trend = []
    for day in sorted(day_counts.keys()):
        bucket = day_counts[day]
        calls = int(bucket.get("calls") or 0)
        success = int(bucket.get("success") or 0)
        fail = int(bucket.get("fail") or 0)
        trend.append(
            {
                "day": day,
                "calls": calls,
                "success": success,
                "fail": fail,
                "success_rate": _ratio(success, calls),
                "fail_rate": _ratio(fail, calls),
            }
        )

    top_error_codes = [{"error_code": code, "count": count} for code, count in sorted(error_counts.items(), key=lambda item: item[1], reverse=True)[:8]]
    top_tools = [{"tool_name": name, "count": count} for name, count in sorted(tool_counts.items(), key=lambda item: item[1], reverse=True)[:8]]

    return {
        "api_key": {"id": key.get("id"), "name": key.get("name"), "key_prefix": key.get("key_prefix")},
        "window_days": days,
        "summary": {
            "total_calls": total_calls,
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": _ratio(success_count, total_calls),
            "fail_rate": _ratio(fail_count, total_calls),
            "avg_latency_ms": avg_latency_ms,
            "p95_latency_ms": _p95_latency_ms(rows),
        },
        "top_error_codes": top_error_codes,
        "top_tools": top_tools,
        "trend": trend,
    }


@router.post("")
async def create_api_key(request: Request, body: CreateApiKeyRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]
    now = datetime.now(timezone.utc).isoformat()
    allowed_tools = _normalize_allowed_tools(body.allowed_tools)
    policy_json = _normalize_api_key_policy(body.policy_json)
    memo = _normalize_memo(body.memo)
    tags = _normalize_tags(body.tags)
    _enforce_member_api_key_write_policy(authz_ctx=authz_ctx, policy_json=policy_json)
    team_id = _validate_team_id(supabase=supabase, authz_ctx=authz_ctx, user_id=user_id, team_id=body.team_id)
    _validate_policy_conflict(allowed_tools=allowed_tools, policy_json=policy_json)

    created = (
        supabase.table("api_keys")
        .insert(
            {
                "user_id": user_id,
                "name": body.name.strip(),
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "team_id": team_id,
                "allowed_tools": allowed_tools,
                "policy_json": policy_json,
                "memo": memo,
                "tags": tags,
                "issued_by": user_id,
                "rotated_from": None,
                "is_active": True,
                "created_at": now,
            }
        )
        .execute()
    )
    row = (created.data or [{}])[0]
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "key_prefix": key_prefix,
        "team_id": row.get("team_id"),
        "allowed_tools": allowed_tools,
        "policy_json": policy_json,
        "memo": memo,
        "tags": tags,
        "issued_by": user_id,
        "rotated_from": row.get("rotated_from"),
        "api_key": raw_key,
    }


@router.delete("/{key_id}")
async def revoke_api_key(request: Request, key_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    now = datetime.now(timezone.utc).isoformat()

    found = (
        supabase.table("api_keys")
        .select("id")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not (found.data or []):
        raise HTTPException(status_code=404, detail="api_key_not_found")

    (
        supabase.table("api_keys")
        .update({"is_active": False, "revoked_at": now})
        .eq("id", key_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"ok": True}


@router.patch("/{key_id}")
async def update_api_key(request: Request, key_id: str, body: UpdateApiKeyRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    found = (
        supabase.table("api_keys")
        .select("id,team_id,allowed_tools,policy_json")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = found.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="api_key_not_found")
    current = rows[0]

    fields_set = body.model_fields_set
    payload: dict[str, object] = {}
    next_allowed_tools = current.get("allowed_tools")
    next_policy_json = current.get("policy_json")
    if "name" in fields_set:
        payload["name"] = (body.name or "").strip()
    if "allowed_tools" in fields_set:
        next_allowed_tools = _normalize_allowed_tools(body.allowed_tools)
        payload["allowed_tools"] = next_allowed_tools
    if "policy_json" in fields_set:
        next_policy_json = _normalize_api_key_policy(body.policy_json)
        payload["policy_json"] = next_policy_json
    if "memo" in fields_set:
        payload["memo"] = _normalize_memo(body.memo)
    if "tags" in fields_set:
        payload["tags"] = _normalize_tags(body.tags)
    if "team_id" in fields_set:
        payload["team_id"] = _validate_team_id(supabase=supabase, authz_ctx=authz_ctx, user_id=user_id, team_id=body.team_id)
    _enforce_member_api_key_write_policy(
        authz_ctx=authz_ctx,
        policy_json=next_policy_json if isinstance(next_policy_json, dict) else None,
    )
    _validate_policy_conflict(
        allowed_tools=next_allowed_tools if isinstance(next_allowed_tools, list) else None,
        policy_json=next_policy_json if isinstance(next_policy_json, dict) else None,
    )
    if "is_active" in fields_set and body.is_active is not None:
        payload["is_active"] = bool(body.is_active)
        if not body.is_active:
            payload["revoked_at"] = datetime.now(timezone.utc).isoformat()
        else:
            payload["revoked_at"] = None

    if not payload:
        return {"ok": True, "updated": False}

    (
        supabase.table("api_keys")
        .update(payload)
        .eq("id", key_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"ok": True, "updated": True}


@router.post("/{key_id}/rotate")
async def rotate_api_key(request: Request, key_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    found = (
        supabase.table("api_keys")
        .select("id,name,team_id,allowed_tools,policy_json,memo,tags,is_active")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = found.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="api_key_not_found")
    current = rows[0]
    if not bool(current.get("is_active")):
        raise HTTPException(status_code=409, detail="api_key_not_active")

    now = datetime.now(timezone.utc).isoformat()
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]

    created = (
        supabase.table("api_keys")
        .insert(
            {
                "user_id": user_id,
                "name": current.get("name") or "default",
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "team_id": current.get("team_id"),
                "allowed_tools": current.get("allowed_tools"),
                "policy_json": current.get("policy_json"),
                "memo": current.get("memo"),
                "tags": current.get("tags"),
                "issued_by": user_id,
                "rotated_from": current.get("id"),
                "is_active": True,
                "created_at": now,
            }
        )
        .execute()
    )
    created_row = (created.data or [{}])[0]

    (
        supabase.table("api_keys")
        .update({"is_active": False, "revoked_at": now})
        .eq("id", key_id)
        .eq("user_id", user_id)
        .execute()
    )

    return {
        "id": created_row.get("id"),
        "name": created_row.get("name"),
        "key_prefix": key_prefix,
        "team_id": created_row.get("team_id"),
        "allowed_tools": created_row.get("allowed_tools"),
        "policy_json": created_row.get("policy_json"),
        "memo": created_row.get("memo"),
        "tags": created_row.get("tags"),
        "issued_by": created_row.get("issued_by"),
        "rotated_from": created_row.get("rotated_from"),
        "api_key": raw_key,
    }
