from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.authz import Role, get_authz_context, require_min_role
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


class OrganizationInviteCreateRequest(BaseModel):
    role: str = Field(default="member", min_length=1, max_length=40)
    invited_email: str | None = Field(default=None, max_length=255)
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class OrganizationInviteAcceptRequest(BaseModel):
    token: str = Field(min_length=8, max_length=200)


class OrganizationRoleRequestCreateRequest(BaseModel):
    target_user_id: str = Field(min_length=1)
    requested_role: str = Field(min_length=1, max_length=40)
    reason: str | None = Field(default=None, max_length=400)


class OrganizationRoleRequestReviewRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=400)


class OrganizationPolicyUpdateRequest(BaseModel):
    policy_json: dict[str, Any] = Field(default_factory=dict)


class OrganizationOAuthPolicyUpdateRequest(BaseModel):
    allowed_providers: list[str] = Field(default_factory=list)
    required_providers: list[str] = Field(default_factory=list)
    blocked_providers: list[str] = Field(default_factory=list)
    approval_workflow: dict[str, Any] | None = None


def _is_org_owner(*, supabase, user_id: str, organization_id: str | int) -> bool:
    membership_rows = (
        supabase.table("org_memberships")
        .select("organization_id")
        .eq("organization_id", organization_id)
        .eq("user_id", user_id)
        .eq("role", "owner")
        .limit(1)
        .execute()
    ).data or []
    return bool(membership_rows)


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


def _org_member_role(*, supabase, user_id: str, organization_id: str | int) -> str | None:
    rows = (
        supabase.table("org_memberships")
        .select("role")
        .eq("organization_id", organization_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    return str(rows[0].get("role") or "").strip().lower() or None


def _is_org_admin_or_owner(*, supabase, user_id: str, organization_id: str | int) -> bool:
    role = _org_member_role(supabase=supabase, user_id=user_id, organization_id=organization_id)
    return role in {"owner", "admin"}


def _normalize_provider_list(items: list[str] | None) -> list[str]:
    if not isinstance(items, list):
        return []
    deduped = {str(item or "").strip().lower() for item in items if str(item or "").strip()}
    return sorted(deduped)


def _normalize_org_oauth_policy(body: OrganizationOAuthPolicyUpdateRequest) -> dict[str, Any]:
    allowed = _normalize_provider_list(body.allowed_providers)
    required = _normalize_provider_list(body.required_providers)
    blocked = _normalize_provider_list(body.blocked_providers)

    required_set = set(required)
    allowed_set = set(allowed)
    if allowed_set and not required_set.issubset(allowed_set):
        raise HTTPException(status_code=400, detail="invalid_oauth_policy:required_not_subset_of_allowed")
    if set(blocked).intersection(required_set):
        raise HTTPException(status_code=400, detail="invalid_oauth_policy:blocked_conflicts_required")

    payload: dict[str, Any] = {
        "allowed_providers": allowed,
        "required_providers": required,
        "blocked_providers": blocked,
    }
    if isinstance(body.approval_workflow, dict):
        payload["approval_workflow"] = body.approval_workflow
    return payload


def _sanitize_oauth_policy_for_member(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw or {})
    for key in ("approval_workflow", "provider_credentials", "secrets", "token_templates"):
        payload.pop(key, None)
    return payload


def _require_org_admin_or_owner(*, supabase, user_id: str, organization_id: str | int) -> str:
    role = _org_member_role(supabase=supabase, user_id=user_id, organization_id=organization_id)
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=404, detail="organization_not_found")
    return role


def _user_email(*, supabase, user_id: str) -> str | None:
    rows = (
        supabase.table("users")
        .select("email")
        .eq("id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    value = str(rows[0].get("email") or "").strip().lower()
    return value or None


@router.get("/{organization_id}/policy")
async def get_organization_policy(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    role = _org_member_role(supabase=supabase, user_id=user_id, organization_id=organization_id)
    if role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=404, detail="organization_not_found")
    rows = (
        supabase.table("org_policies")
        .select("organization_id,policy_json,updated_at")
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    row = rows[0] if rows else {}
    return {
        "item": {
            "organization_id": row.get("organization_id", organization_id),
            "policy_json": row.get("policy_json") if isinstance(row.get("policy_json"), dict) else {},
            "updated_at": row.get("updated_at"),
        }
    }


@router.patch("/{organization_id}/policy")
async def update_organization_policy(request: Request, organization_id: str, body: OrganizationPolicyUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    _require_org_admin_or_owner(supabase=supabase, user_id=user_id, organization_id=organization_id)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "organization_id": organization_id,
        "policy_json": body.policy_json if isinstance(body.policy_json, dict) else {},
        "updated_by": user_id,
        "updated_at": now,
        "created_at": now,
    }
    rows = supabase.table("org_policies").upsert(payload, on_conflict="organization_id").execute().data or []
    item = rows[0] if rows else payload
    return {"item": item}


@router.get("/{organization_id}/oauth-policy")
async def get_organization_oauth_policy(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    role = _org_member_role(supabase=supabase, user_id=user_id, organization_id=organization_id)
    if role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=404, detail="organization_not_found")

    rows = (
        supabase.table("org_oauth_policies")
        .select("organization_id,policy_json,version,updated_at")
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    row = rows[0] if rows else {}
    raw_policy = row.get("policy_json") if isinstance(row.get("policy_json"), dict) else {}
    policy_json = _sanitize_oauth_policy_for_member(raw_policy) if role == "member" else raw_policy
    return {
        "item": {
            "organization_id": row.get("organization_id", organization_id),
            "policy_json": policy_json,
            "version": int(row.get("version") or 1),
            "updated_at": row.get("updated_at"),
        }
    }


@router.patch("/{organization_id}/oauth-policy")
async def update_organization_oauth_policy(request: Request, organization_id: str, body: OrganizationOAuthPolicyUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    _require_org_admin_or_owner(supabase=supabase, user_id=user_id, organization_id=organization_id)

    normalized = _normalize_org_oauth_policy(body)
    existing_rows = (
        supabase.table("org_oauth_policies")
        .select("version")
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    next_version = int(existing_rows[0].get("version") or 1) + 1 if existing_rows else 1
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "organization_id": organization_id,
        "policy_json": normalized,
        "version": next_version,
        "updated_by": user_id,
        "updated_at": now,
        "created_at": now,
    }
    rows = supabase.table("org_oauth_policies").upsert(payload, on_conflict="organization_id").execute().data or []
    item = rows[0] if rows else payload
    return {"item": item}


@router.get("")
async def list_organizations(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

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
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
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
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    if not _is_org_owner(supabase=supabase, user_id=user_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    supabase.table("organizations").update({"name": body.name.strip(), "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", organization_id).execute()
    return {"ok": True}


@router.delete("/{organization_id}")
async def delete_organization(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.OWNER, method=request.method)
    if not _is_org_owner(supabase=supabase, user_id=user_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    supabase.table("organizations").delete().eq("id", organization_id).execute()
    return {"ok": True}


@router.get("/{organization_id}/members")
async def list_organization_members(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
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
    actor_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=actor_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    actor_role = _require_org_admin_or_owner(supabase=supabase, user_id=actor_id, organization_id=organization_id)

    role = str(body.role or "").strip().lower()
    if role not in _ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="invalid_member_role")
    target_user_id = body.user_id.strip()
    if target_user_id == actor_id and role != actor_role:
        raise HTTPException(status_code=403, detail="self_role_change_forbidden")

    existing_rows = (
        supabase.table("org_memberships")
        .select("role")
        .eq("organization_id", organization_id)
        .eq("user_id", target_user_id)
        .limit(1)
        .execute()
    ).data or []
    existing_role = str(existing_rows[0].get("role") or "").strip().lower() if existing_rows else None

    if actor_role == "admin":
        if role != "member":
            raise HTTPException(status_code=403, detail="admin_can_assign_member_only")
        if existing_role in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="admin_cannot_modify_privileged_member")

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
    actor_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=actor_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    actor_role = _require_org_admin_or_owner(supabase=supabase, user_id=actor_id, organization_id=organization_id)
    target_user_id = member_user_id.strip()
    if target_user_id == actor_id:
        raise HTTPException(status_code=400, detail="cannot_remove_owner_self")
    row = (
        supabase.table("org_memberships")
        .select("id,role")
        .eq("organization_id", organization_id)
        .eq("user_id", target_user_id)
        .limit(1)
        .execute()
    ).data or []
    if not row:
        raise HTTPException(status_code=404, detail="organization_member_not_found")
    target_role = str(row[0].get("role") or "").strip().lower()
    if actor_role == "admin" and target_role in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="admin_cannot_remove_privileged_member")
    supabase.table("org_memberships").delete().eq("organization_id", organization_id).eq("user_id", target_user_id).execute()
    return {"ok": True}


@router.get("/{organization_id}/invites")
async def list_organization_invites(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    if not _is_org_member(supabase=supabase, user_id=user_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    rows = (
        supabase.table("org_invites")
        .select("id,organization_id,token,invited_email,role,invited_by,expires_at,accepted_by,accepted_at,revoked_at,created_at")
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/{organization_id}/invites")
async def create_organization_invite(request: Request, organization_id: str, body: OrganizationInviteCreateRequest):
    invited_by = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=invited_by, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    actor_role = _require_org_admin_or_owner(supabase=supabase, user_id=invited_by, organization_id=organization_id)
    role = str(body.role or "").strip().lower()
    if role not in _ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="invalid_member_role")
    if actor_role == "admin" and role != "member":
        raise HTTPException(status_code=403, detail="admin_can_invite_member_only")
    token = uuid4().hex
    now = datetime.now(timezone.utc)
    payload = {
        "organization_id": organization_id,
        "token": token,
        "invited_email": (body.invited_email or "").strip().lower() or None,
        "role": role,
        "invited_by": invited_by,
        "expires_at": (now + timedelta(hours=int(body.expires_in_hours))).isoformat(),
        "created_at": now.isoformat(),
    }
    row = supabase.table("org_invites").insert(payload).execute().data or []
    return {"item": row[0] if row else payload}


@router.post("/{organization_id}/invites/{invite_id}/revoke")
async def revoke_organization_invite(request: Request, organization_id: str, invite_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    _require_org_admin_or_owner(supabase=supabase, user_id=user_id, organization_id=organization_id)
    rows = (
        supabase.table("org_invites")
        .select("id,organization_id,accepted_at,revoked_at")
        .eq("id", invite_id)
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="invite_not_found")
    invite = rows[0]
    if invite.get("accepted_at") is not None:
        raise HTTPException(status_code=409, detail="invite_already_accepted")
    if invite.get("revoked_at") is not None:
        return {"ok": True, "status": "already_revoked"}
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("org_invites").update({"revoked_at": now}).eq("id", invite_id).eq("organization_id", organization_id).execute()
    return {"ok": True, "status": "revoked"}


@router.post("/{organization_id}/invites/{invite_id}/reissue")
async def reissue_organization_invite(request: Request, organization_id: str, invite_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.ADMIN, method=request.method)
    _require_org_admin_or_owner(supabase=supabase, user_id=user_id, organization_id=organization_id)
    rows = (
        supabase.table("org_invites")
        .select("id,organization_id,invited_email,role,accepted_at,revoked_at")
        .eq("id", invite_id)
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="invite_not_found")
    invite = rows[0]
    if invite.get("accepted_at") is not None:
        raise HTTPException(status_code=409, detail="invite_already_accepted")
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    supabase.table("org_invites").update({"revoked_at": now.isoformat()}).eq("id", invite_id).eq("organization_id", organization_id).execute()
    payload = {
        "organization_id": organization_id,
        "token": token,
        "invited_email": invite.get("invited_email"),
        "role": invite.get("role"),
        "invited_by": user_id,
        "expires_at": (now + timedelta(hours=72)).isoformat(),
        "created_at": now.isoformat(),
    }
    created = supabase.table("org_invites").insert(payload).execute().data or []
    return {"item": created[0] if created else payload}


@router.post("/invites/accept")
async def accept_organization_invite(request: Request, body: OrganizationInviteAcceptRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    token = body.token.strip()
    rows = (
        supabase.table("org_invites")
        .select("id,organization_id,invited_email,role,expires_at,accepted_at,revoked_at")
        .eq("token", token)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="invite_not_found")
    invite = rows[0]
    if invite.get("accepted_at") is not None:
        raise HTTPException(status_code=409, detail="invite_already_accepted")
    if invite.get("revoked_at") is not None:
        raise HTTPException(status_code=409, detail="invite_revoked")

    expires_at_raw = str(invite.get("expires_at") or "").strip()
    try:
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invite_invalid_expiry") from exc
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="invite_expired")

    invited_email = str(invite.get("invited_email") or "").strip().lower()
    if invited_email:
        my_email = _user_email(supabase=supabase, user_id=user_id)
        if not my_email or my_email != invited_email:
            raise HTTPException(status_code=403, detail="invite_email_mismatch")

    now = datetime.now(timezone.utc).isoformat()
    role = str(invite.get("role") or "member").strip().lower()
    if role not in _ALLOWED_MEMBER_ROLES:
        role = "member"
    organization_id = invite.get("organization_id")
    supabase.table("org_memberships").upsert(
        {
            "organization_id": organization_id,
            "user_id": user_id,
            "role": role,
            "created_at": now,
        },
        on_conflict="organization_id,user_id",
    ).execute()
    supabase.table("org_invites").update({"accepted_by": user_id, "accepted_at": now}).eq("id", invite.get("id")).execute()
    return {"ok": True, "organization_id": organization_id, "role": role}


@router.get("/{organization_id}/role-requests")
async def list_organization_role_requests(request: Request, organization_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    role = _org_member_role(supabase=supabase, user_id=user_id, organization_id=organization_id)
    if role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=404, detail="organization_not_found")

    query = (
        supabase.table("org_role_change_requests")
        .select(
            "id,organization_id,target_user_id,requested_role,reason,request_type,status,requested_by,"
            "reviewed_by,reviewed_at,review_reason,cancelled_by,cancelled_at,created_at,updated_at"
        )
        .eq("organization_id", organization_id)
    )
    if role == "member":
        query = query.eq("requested_by", user_id)
    rows = query.order("created_at", desc=True).execute().data or []
    return {"items": rows, "count": len(rows)}


@router.post("/{organization_id}/role-requests")
async def create_organization_role_request(request: Request, organization_id: str, body: OrganizationRoleRequestCreateRequest):
    requested_by = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=requested_by, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    requester_role = _org_member_role(supabase=supabase, user_id=requested_by, organization_id=organization_id)
    if requester_role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=404, detail="organization_not_found")
    requested_role = str(body.requested_role or "").strip().lower()
    if requested_role not in _ALLOWED_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="invalid_member_role")
    if requested_role == "owner" and requester_role != "owner":
        raise HTTPException(status_code=403, detail="owner_role_request_forbidden")
    target_user_id = body.target_user_id.strip()
    if requester_role == "member" and target_user_id != requested_by:
        raise HTTPException(status_code=403, detail="member_can_request_self_only")
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "organization_id": organization_id,
        "target_user_id": target_user_id,
        "requested_role": requested_role,
        "reason": (body.reason or "").strip() or None,
        "request_type": "change_request",
        "status": "pending",
        "requested_by": requested_by,
        "created_at": now,
        "updated_at": now,
    }
    row = supabase.table("org_role_change_requests").insert(payload).execute().data or []
    return {"item": row[0] if row else payload}


@router.post("/{organization_id}/role-requests/{request_id}/review")
async def review_organization_role_request(
    request: Request, organization_id: str, request_id: str, body: OrganizationRoleRequestReviewRequest
):
    reviewer_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=reviewer_id, supabase=supabase)
    require_min_role(authz_ctx, Role.OWNER, method=request.method)
    if not _is_org_owner(supabase=supabase, user_id=reviewer_id, organization_id=organization_id):
        raise HTTPException(status_code=404, detail="organization_not_found")
    decision = str(body.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="invalid_decision")
    rows = (
        supabase.table("org_role_change_requests")
        .select("id,organization_id,target_user_id,requested_role,status,requested_by")
        .eq("id", request_id)
        .eq("organization_id", organization_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="role_request_not_found")
    row = rows[0]
    if str(row.get("requested_by") or "").strip() == reviewer_id:
        raise HTTPException(status_code=403, detail="self_review_not_allowed")
    if str(row.get("status") or "").strip().lower() != "pending":
        raise HTTPException(status_code=409, detail="role_request_already_reviewed")
    now = datetime.now(timezone.utc).isoformat()
    status = "approved" if decision == "approve" else "rejected"
    review_reason = (body.reason or "").strip() or None
    supabase.table("org_role_change_requests").update(
        {
            "status": status,
            "reviewed_by": reviewer_id,
            "reviewed_at": now,
            "review_reason": review_reason,
            "updated_at": now,
        }
    ).eq("id", request_id).eq("organization_id", organization_id).execute()
    if status == "approved":
        supabase.table("org_memberships").upsert(
            {
                "organization_id": organization_id,
                "user_id": row.get("target_user_id"),
                "role": row.get("requested_role"),
                "created_at": now,
            },
            on_conflict="organization_id,user_id",
        ).execute()
    return {"ok": True, "status": status}
