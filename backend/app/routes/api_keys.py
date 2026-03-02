from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from agent.registry import load_registry
from app.core.api_keys import generate_api_key, hash_api_key
from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])
_PHASE1_SERVICES = {"notion", "linear"}


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=100)
    allowed_tools: list[str] | None = None


class UpdateApiKeyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_tools: list[str] | None = None
    is_active: bool | None = None


def _normalize_allowed_tools(raw_tools: list[str] | None) -> list[str] | None:
    if raw_tools is None:
        return None
    registry = load_registry()
    phase1_tools = {tool.tool_name for tool in registry.list_tools() if tool.service in _PHASE1_SERVICES}
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


@router.get("")
async def list_api_keys(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    result = (
        supabase.table("api_keys")
        .select("id,name,key_prefix,allowed_tools,is_active,last_used_at,created_at,revoked_at")
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

    created = (
        supabase.table("api_keys")
        .insert(
            {
                "user_id": user_id,
                "name": body.name.strip(),
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "allowed_tools": allowed_tools,
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
        .select("id")
        .eq("id", key_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not (found.data or []):
        raise HTTPException(status_code=404, detail="api_key_not_found")

    fields_set = body.model_fields_set
    payload: dict[str, object] = {}
    if "name" in fields_set:
        payload["name"] = (body.name or "").strip()
    if "allowed_tools" in fields_set:
        payload["allowed_tools"] = _normalize_allowed_tools(body.allowed_tools)
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
