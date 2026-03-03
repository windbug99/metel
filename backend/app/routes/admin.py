from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


class IncidentBannerUpdateRequest(BaseModel):
    enabled: bool | None = None
    message: str | None = Field(default=None, max_length=400)
    severity: str | None = Field(default=None, max_length=20)
    starts_at: str | None = None
    ends_at: str | None = None


class IncidentBannerRevisionCreateRequest(BaseModel):
    enabled: bool | None = None
    message: str | None = Field(default=None, max_length=400)
    severity: str | None = Field(default=None, max_length=20)
    starts_at: str | None = None
    ends_at: str | None = None


class IncidentBannerRevisionReviewRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=20)


def _connector_name(row: dict[str, Any]) -> str:
    connector = str(row.get("connector") or "").strip().lower()
    if connector:
        return connector
    tool_name = str(row.get("tool_name") or "").strip().lower()
    if tool_name.startswith("notion_"):
        return "notion"
    if tool_name.startswith("linear_"):
        return "linear"
    return "other"


def _parse_iso(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_datetime") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


@router.get("/connectors/diagnostics")
async def connector_diagnostics(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("oauth_tokens")
        .select("provider,workspace_id,workspace_name,granted_scopes,updated_at")
        .eq("user_id", user_id)
        .execute()
    ).data or []
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        updated_at = row.get("updated_at")
        dt = None
        if isinstance(updated_at, str):
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                dt = None
        stale = bool(dt and (now - dt) > timedelta(days=30))
        items.append(
            {
                "provider": row.get("provider"),
                "workspace_id": row.get("workspace_id"),
                "workspace_name": row.get("workspace_name"),
                "granted_scopes": row.get("granted_scopes") or [],
                "updated_at": updated_at,
                "status": "stale" if stale else "ok",
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/rate-limit-events")
async def rate_limit_events(request: Request, days: int = Query(7, ge=1, le=30), limit: int = Query(100, ge=1, le=500)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("tool_calls")
        .select("id,request_id,api_key_id,tool_name,error_code,created_at")
        .eq("user_id", user_id)
        .in_("error_code", ["rate_limit_exceeded", "quota_exceeded"])
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.get("/system-health")
async def system_health(request: Request):
    _ = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    db_ok = True
    error_message = None
    try:
        supabase.table("users").select("id").limit(1).execute()
    except Exception as exc:
        db_ok = False
        error_message = str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "services": {"database": {"ok": db_ok, "error": error_message}},
    }


@router.get("/external-health")
async def external_health(request: Request, days: int = Query(1, ge=1, le=14)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("tool_calls")
        .select("connector,tool_name,status,error_code,latency_ms,created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .execute()
    ).data or []

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        connector = _connector_name(row)
        bucket = buckets.get(connector) or {
            "connector": connector,
            "calls": 0,
            "failures": 0,
            "upstream_temporary": 0,
            "avg_latency_ms": 0.0,
            "last_error_at": None,
            "status": "ok",
            "top_errors": {},
        }
        bucket["calls"] += 1
        if str(row.get("status") or "") == "fail":
            bucket["failures"] += 1
            bucket["last_error_at"] = row.get("created_at")
        if str(row.get("error_code") or "") == "upstream_temporary_failure":
            bucket["upstream_temporary"] += 1
        error_code = str(row.get("error_code") or "").strip()
        if error_code:
            top_errors = bucket.get("top_errors") or {}
            top_errors[error_code] = int(top_errors.get(error_code, 0)) + 1
            bucket["top_errors"] = top_errors
        bucket["avg_latency_ms"] += float(row.get("latency_ms") or 0.0)
        buckets[connector] = bucket

    items: list[dict[str, Any]] = []
    for connector, bucket in buckets.items():
        calls = int(bucket.get("calls") or 0)
        failures = int(bucket.get("failures") or 0)
        upstream_temporary = int(bucket.get("upstream_temporary") or 0)
        avg_latency_ms = round(float(bucket.get("avg_latency_ms") or 0.0) / calls, 2) if calls else 0.0
        fail_rate = round((failures / calls), 4) if calls else 0.0
        status = "ok"
        if calls >= 5 and (fail_rate >= 0.3 or upstream_temporary >= 3):
            status = "degraded"
        top_errors_dict = bucket.get("top_errors") or {}
        top_errors = [
            {"error_code": code, "count": count}
            for code, count in sorted(top_errors_dict.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        items.append(
            {
                "connector": connector,
                "calls": calls,
                "failures": failures,
                "fail_rate": fail_rate,
                "upstream_temporary": upstream_temporary,
                "avg_latency_ms": avg_latency_ms,
                "last_error_at": bucket.get("last_error_at"),
                "status": status,
                "top_errors": top_errors,
            }
        )

    return {"window_days": days, "items": sorted(items, key=lambda item: item["connector"])}


@router.get("/incident-banner")
async def get_incident_banner(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("incident_banners")
        .select("user_id,enabled,message,severity,starts_at,ends_at,updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {
            "enabled": False,
            "message": None,
            "severity": "info",
            "starts_at": None,
            "ends_at": None,
            "updated_at": None,
        }
    return rows[0]


@router.patch("/incident-banner")
async def update_incident_banner(request: Request, body: IncidentBannerUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    severity = str(body.severity or "info").strip().lower()
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="invalid_severity")
    starts_at = _parse_iso(body.starts_at)
    ends_at = _parse_iso(body.ends_at)
    payload = {
        "user_id": user_id,
        "enabled": bool(body.enabled) if body.enabled is not None else False,
        "message": (body.message or "").strip() or None,
        "severity": severity,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("incident_banners").upsert(payload, on_conflict="user_id").execute()
    return payload


@router.get("/incident-banner/revisions")
async def list_incident_banner_revisions(request: Request, limit: int = Query(50, ge=1, le=200)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("incident_banner_revisions")
        .select("id,user_id,enabled,message,severity,starts_at,ends_at,status,requested_by,approved_by,approved_at,created_at,updated_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/incident-banner/revisions")
async def create_incident_banner_revision(request: Request, body: IncidentBannerRevisionCreateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    severity = str(body.severity or "info").strip().lower()
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="invalid_severity")
    starts_at = _parse_iso(body.starts_at)
    ends_at = _parse_iso(body.ends_at)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user_id,
        "enabled": bool(body.enabled) if body.enabled is not None else False,
        "message": (body.message or "").strip() or None,
        "severity": severity,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "status": "pending",
        "requested_by": user_id,
        "created_at": now,
        "updated_at": now,
    }
    row = supabase.table("incident_banner_revisions").insert(payload).execute().data or []
    return {"item": row[0] if row else payload}


@router.post("/incident-banner/revisions/{revision_id}/review")
async def review_incident_banner_revision(request: Request, revision_id: str, body: IncidentBannerRevisionReviewRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    decision = str(body.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="invalid_decision")
    rows = (
        supabase.table("incident_banner_revisions")
        .select("id,user_id,enabled,message,severity,starts_at,ends_at,status")
        .eq("id", revision_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="revision_not_found")
    revision = rows[0]
    current_status = str(revision.get("status") or "").strip().lower()
    if current_status != "pending":
        raise HTTPException(status_code=409, detail="revision_already_reviewed")
    now = datetime.now(timezone.utc).isoformat()
    status = "approved" if decision == "approve" else "rejected"
    supabase.table("incident_banner_revisions").update(
        {"status": status, "approved_by": user_id, "approved_at": now, "updated_at": now}
    ).eq("id", revision_id).eq("user_id", user_id).execute()
    if status == "approved":
        supabase.table("incident_banners").upsert(
            {
                "user_id": user_id,
                "enabled": bool(revision.get("enabled")),
                "message": revision.get("message"),
                "severity": revision.get("severity"),
                "starts_at": revision.get("starts_at"),
                "ends_at": revision.get("ends_at"),
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()
    return {"ok": True, "status": status}
