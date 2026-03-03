from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/teams", tags=["teams"])


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    policy_json: dict[str, Any] | None = None


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    policy_json: dict[str, Any] | None = None


class TeamMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: str = Field(default="member", min_length=1, max_length=40)


def _normalize_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="invalid_policy_json")
    out: dict[str, Any] = {}
    allow_high_risk = raw.get("allow_high_risk")
    if allow_high_risk is not None:
        out["allow_high_risk"] = bool(allow_high_risk)
    allowed_services = raw.get("allowed_services")
    if isinstance(allowed_services, list):
        out["allowed_services"] = [str(item).strip().lower() for item in allowed_services if str(item).strip()]
    deny_tools = raw.get("deny_tools")
    if isinstance(deny_tools, list):
        out["deny_tools"] = [str(item).strip() for item in deny_tools if str(item).strip()]
    allowed_linear_team_ids = raw.get("allowed_linear_team_ids")
    if isinstance(allowed_linear_team_ids, list):
        out["allowed_linear_team_ids"] = [str(item).strip() for item in allowed_linear_team_ids if str(item).strip()]
    return out


def _insert_policy_revision(*, supabase, team_id: int | str, user_id: str, source: str, policy_json: dict[str, Any]) -> None:
    supabase.table("policy_revisions").insert(
        {
            "team_id": team_id,
            "source": source,
            "policy_json": policy_json,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


@router.get("")
async def list_teams(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    teams = (
        supabase.table("teams")
        .select("id,name,description,is_active,created_at,updated_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    team_ids = [item.get("id") for item in teams if item.get("id") is not None]
    policies = (
        supabase.table("team_policies")
        .select("team_id,policy_json,updated_at")
        .in_("team_id", team_ids)
        .execute()
    ).data or [] if team_ids else []
    policy_map = {str(item.get("team_id")): item for item in policies}
    items = []
    for team in teams:
        policy_row = policy_map.get(str(team.get("id"))) or {}
        items.append(
            {
                **team,
                "policy_json": policy_row.get("policy_json") or {},
                "policy_updated_at": policy_row.get("updated_at"),
            }
        )
    return {"items": items, "count": len(items)}


@router.post("")
async def create_team(request: Request, body: TeamCreateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    now = datetime.now(timezone.utc).isoformat()
    policy_json = _normalize_policy(body.policy_json)

    created = (
        supabase.table("teams")
        .insert(
            {
                "user_id": user_id,
                "name": body.name.strip(),
                "description": (body.description or "").strip() or None,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        .execute()
    ).data or []
    if not created:
        raise HTTPException(status_code=500, detail="team_create_failed")
    team = created[0]
    supabase.table("team_policies").insert({"team_id": team.get("id"), "policy_json": policy_json, "created_at": now, "updated_at": now}).execute()
    _insert_policy_revision(supabase=supabase, team_id=team.get("id"), user_id=user_id, source="team_created", policy_json=policy_json)
    return {"id": team.get("id"), "name": team.get("name"), "policy_json": policy_json}


@router.patch("/{team_id}")
async def update_team(request: Request, team_id: str, body: TeamUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    team_rows = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not team_rows:
        raise HTTPException(status_code=404, detail="team_not_found")

    payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    fields = body.model_fields_set
    if "name" in fields:
        payload["name"] = (body.name or "").strip()
    if "description" in fields:
        payload["description"] = (body.description or "").strip() or None
    if "is_active" in fields and body.is_active is not None:
        payload["is_active"] = bool(body.is_active)
    if len(payload) > 1:
        supabase.table("teams").update(payload).eq("id", team_id).eq("user_id", user_id).execute()

    if "policy_json" in fields:
        policy_json = _normalize_policy(body.policy_json)
        now = datetime.now(timezone.utc).isoformat()
        existing = (
            supabase.table("team_policies")
            .select("id")
            .eq("team_id", team_id)
            .limit(1)
            .execute()
        ).data or []
        if existing:
            supabase.table("team_policies").update({"policy_json": policy_json, "updated_at": now}).eq("team_id", team_id).execute()
        else:
            supabase.table("team_policies").insert({"team_id": team_id, "policy_json": policy_json, "created_at": now, "updated_at": now}).execute()
        _insert_policy_revision(supabase=supabase, team_id=team_id, user_id=user_id, source="team_policy_update", policy_json=policy_json)

    return {"ok": True}


@router.get("/{team_id}/members")
async def list_team_members(request: Request, team_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    team = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")

    rows = (
        supabase.table("team_memberships")
        .select("id,user_id,role,created_at")
        .eq("team_id", team_id)
        .order("created_at", desc=False)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/{team_id}/members")
async def add_team_member(request: Request, team_id: str, body: TeamMemberRequest):
    owner_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    team = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", owner_id)
        .limit(1)
        .execute()
    ).data or []
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")
    now = datetime.now(timezone.utc).isoformat()
    row = (
        supabase.table("team_memberships")
        .upsert(
            {"team_id": team_id, "user_id": body.user_id.strip(), "role": body.role.strip(), "created_at": now},
            on_conflict="team_id,user_id",
        )
        .execute()
    ).data or []
    return {"item": row[0] if row else {"team_id": team_id, "user_id": body.user_id.strip(), "role": body.role.strip()}}


@router.delete("/{team_id}/members/{membership_id}")
async def delete_team_member(request: Request, team_id: str, membership_id: str):
    owner_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    team = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", owner_id)
        .limit(1)
        .execute()
    ).data or []
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")

    member = (
        supabase.table("team_memberships")
        .select("id")
        .eq("id", membership_id)
        .eq("team_id", team_id)
        .limit(1)
        .execute()
    ).data or []
    if not member:
        raise HTTPException(status_code=404, detail="team_member_not_found")

    supabase.table("team_memberships").delete().eq("id", membership_id).eq("team_id", team_id).execute()
    return {"ok": True}


@router.get("/{team_id}/policy-revisions")
async def list_policy_revisions(request: Request, team_id: str, limit: int = 20):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    team = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")
    rows = (
        supabase.table("policy_revisions")
        .select("id,team_id,source,policy_json,created_by,created_at")
        .eq("team_id", team_id)
        .order("created_at", desc=True)
        .limit(min(max(limit, 1), 100))
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/{team_id}/policy-revisions/{revision_id}/rollback")
async def rollback_policy_revision(request: Request, team_id: str, revision_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    team = (
        supabase.table("teams")
        .select("id")
        .eq("id", team_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")
    revision = (
        supabase.table("policy_revisions")
        .select("id,policy_json")
        .eq("id", revision_id)
        .eq("team_id", team_id)
        .limit(1)
        .execute()
    ).data or []
    if not revision:
        raise HTTPException(status_code=404, detail="policy_revision_not_found")
    policy_json = revision[0].get("policy_json") if isinstance(revision[0].get("policy_json"), dict) else {}
    now = datetime.now(timezone.utc).isoformat()
    existing = (
        supabase.table("team_policies")
        .select("id")
        .eq("team_id", team_id)
        .limit(1)
        .execute()
    ).data or []
    if existing:
        supabase.table("team_policies").update({"policy_json": policy_json, "updated_at": now}).eq("team_id", team_id).execute()
    else:
        supabase.table("team_policies").insert({"team_id": team_id, "policy_json": policy_json, "created_at": now, "updated_at": now}).execute()
    _insert_policy_revision(supabase=supabase, team_id=team_id, user_id=user_id, source="team_policy_rollback", policy_json=policy_json)
    return {"ok": True, "policy_json": policy_json}
