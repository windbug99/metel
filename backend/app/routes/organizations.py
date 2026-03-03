from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

_ALLOWED_MEMBER_ROLES = {"owner", "admin", "member"}


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class OrganizationMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: str = Field(default="member", min_length=1, max_length=40)


def _is_org_owner(*, supabase, user_id: str, organization_id: str | int) -> bool:
    rows = (
        supabase.table("organizations")
        .select("id")
        .eq("id", organization_id)
        .eq("created_by", user_id)
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def _is_org_member(*, supabase, user_id: str, organization_id: str | int) -> bool:
    rows = (
        supabase.table("org_memberships")
        .select("organization_id")
        .eq("organization_id", organization_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


@router.get("")
async def list_organizations(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    membership_rows = (
        supabase.table("org_memberships")
        .select("organization_id,role")
        .eq("user_id", user_id)
        .execute()
    ).data or []
    role_map = {str(item.get("organization_id")): str(item.get("role") or "member") for item in membership_rows if item.get("organization_id") is not None}
    org_ids = [item.get("organization_id") for item in membership_rows if item.get("organization_id") is not None]
    if not org_ids:
        return {"items": [], "count": 0}

    rows = (
        supabase.table("organizations")
        .select("id,name,created_at,updated_at")
        .in_("id", org_ids)
        .order("created_at", desc=False)
        .execute()
    ).data or []
    items = []
    for row in rows:
        org_id = row.get("id")
        items.append(
            {
                "id": org_id,
                "name": row.get("name"),
                "role": role_map.get(str(org_id), "member"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"items": items, "count": len(items)}


@router.post("")
async def create_organization(request: Request, body: OrganizationCreateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    now = datetime.now(timezone.utc).isoformat()

    created = (
        supabase.table("organizations")
        .insert({"name": body.name.strip(), "created_by": user_id, "created_at": now, "updated_at": now})
        .execute()
    ).data or []
    if not created:
        raise HTTPException(status_code=500, detail="organization_create_failed")
    org = created[0]
    supabase.table("org_memberships").upsert(
        {
            "organization_id": org.get("id"),
            "user_id": user_id,
            "role": "owner",
            "created_at": now,
        },
        on_conflict="organization_id,user_id",
    ).execute()
    return {"item": {"id": org.get("id"), "name": org.get("name"), "role": "owner", "created_at": org.get("created_at"), "updated_at": org.get("updated_at")}}


@router.patch("/{organization_id}")
async def update_organization(request: Request, organization_id: str, body: OrganizationUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    if not _is_org_owner(supabase=supabase, user_id=user_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    supabase.table("organizations").update({"name": body.name.strip(), "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", organization_id).execute()
    return {"ok": True}


@router.get("/{organization_id}/members")
async def list_organization_members(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    if not _is_org_member(supabase=supabase, user_id=user_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    rows = (
        supabase.table("org_memberships")
        .select("id,organization_id,user_id,role,created_at")
        .eq("organization_id", organization_id)
        .order("created_at", desc=False)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/{organization_id}/members")
async def upsert_organization_member(request: Request, organization_id: str, body: OrganizationMemberRequest):
    owner_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    if not _is_org_owner(supabase=supabase, user_id=owner_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")

    role = str(body.role or "").strip().lower()
    if role not in _ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="invalid_member_role")
    target_user_id = body.user_id.strip()
    now = datetime.now(timezone.utc).isoformat()
    row = (
        supabase.table("org_memberships")
        .upsert(
            {
                "organization_id": organization_id,
                "user_id": target_user_id,
                "role": role,
                "created_at": now,
            },
            on_conflict="organization_id,user_id",
        )
        .execute()
    ).data or []
    item: dict[str, Any]
    if row:
        item = row[0]
    else:
        item = {"organization_id": organization_id, "user_id": target_user_id, "role": role}
    return {"item": item}


@router.delete("/{organization_id}/members/{member_user_id}")
async def delete_organization_member(request: Request, organization_id: str, member_user_id: str):
    owner_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    if not _is_org_owner(supabase=supabase, user_id=owner_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    target_user_id = member_user_id.strip()
    if target_user_id == owner_id:
        raise HTTPException(status_code=400, detail="cannot_remove_owner_self")
    row = (
        supabase.table("org_memberships")
        .select("id")
        .eq("organization_id", organization_id)
        .eq("user_id", target_user_id)
        .limit(1)
        .execute()
    ).data or []
    if not row:
        raise HTTPException(status_code=404, detail="organization_member_not_found")
    supabase.table("org_memberships").delete().eq("organization_id", organization_id).eq("user_id", target_user_id).execute()
    return {"ok": True}
