from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from agent.registry import load_registry
from app.core.api_keys import generate_api_key, hash_api_key
from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.core.error_codes import ERR_POLICY_CONFLICT

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])
_PHASE1_SERVICES = {"notion", "linear"}


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=100)
    allowed_tools: list[str] | None = None
    policy_json: dict[str, Any] | None = None


class UpdateApiKeyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_tools: list[str] | None = None
    policy_json: dict[str, Any] | None = None
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


@router.get("")
async def list_api_keys(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    result = (
        supabase.table("api_keys")
        .select("id,name,key_prefix,allowed_tools,policy_json,is_active,last_used_at,created_at,revoked_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    rows = result.data or []
    return {"items": rows, "count": len(rows)}


@router.post("")
async def create_api_key(request: Request, body: CreateApiKeyRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]
    now = datetime.now(timezone.utc).isoformat()
    allowed_tools = _normalize_allowed_tools(body.allowed_tools)
    policy_json = _normalize_api_key_policy(body.policy_json)
    _validate_policy_conflict(allowed_tools=allowed_tools, policy_json=policy_json)

    created = (
        supabase.table("api_keys")
        .insert(
            {
                "user_id": user_id,
                "name": body.name.strip(),
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "allowed_tools": allowed_tools,
                "policy_json": policy_json,
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
        "allowed_tools": allowed_tools,
        "policy_json": policy_json,
        "api_key": raw_key,
    }


@router.delete("/{key_id}")
async def revoke_api_key(request: Request, key_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
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

    found = (
        supabase.table("api_keys")
        .select("id,allowed_tools,policy_json")
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
