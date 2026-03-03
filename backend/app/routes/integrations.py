from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.core.dead_letter_alert import send_dead_letter_alert
from app.core.event_hooks import emit_webhook_event, process_pending_webhook_retries, retry_webhook_delivery

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    endpoint_url: str = Field(min_length=1, max_length=500)
    secret: str | None = Field(default=None, max_length=200)
    event_types: list[str] = Field(default_factory=list)


class WebhookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    endpoint_url: str | None = Field(default=None, min_length=1, max_length=500)
    secret: str | None = Field(default=None, max_length=200)
    event_types: list[str] | None = None
    is_active: bool | None = None


def _normalize_event_types(raw: list[str] | None) -> list[str]:
    if raw is None:
        return []
    allowed = {
        "tool_called",
        "tool_succeeded",
        "tool_failed",
        "policy_blocked",
        "quota_exceeded",
        "rate_limit_exceeded",
        "*",
    }
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        if value not in allowed:
            raise HTTPException(status_code=400, detail=f"invalid_event_type:{value}")
        seen.add(value)
        out.append(value)
    return out


@router.get("/webhooks")
async def list_webhooks(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("webhook_subscriptions")
        .select("id,name,endpoint_url,event_types,is_active,last_delivery_at,created_at,updated_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    return {"items": rows, "count": len(rows)}


@router.post("/webhooks")
async def create_webhook(request: Request, body: WebhookCreateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    now = datetime.now(timezone.utc).isoformat()
    event_types = _normalize_event_types(body.event_types)
    row = (
        supabase.table("webhook_subscriptions")
        .insert(
            {
                "user_id": user_id,
                "name": body.name.strip(),
                "endpoint_url": body.endpoint_url.strip(),
                "secret": (body.secret or "").strip() or None,
                "event_types": event_types,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        .execute()
    ).data or []
    return {"item": row[0] if row else None}


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(request: Request, webhook_id: str, body: WebhookUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    exists = (
        supabase.table("webhook_subscriptions")
        .select("id")
        .eq("id", webhook_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not exists:
        raise HTTPException(status_code=404, detail="webhook_not_found")
    payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    fields = body.model_fields_set
    if "name" in fields:
        payload["name"] = (body.name or "").strip()
    if "endpoint_url" in fields:
        payload["endpoint_url"] = (body.endpoint_url or "").strip()
    if "secret" in fields:
        payload["secret"] = (body.secret or "").strip() or None
    if "event_types" in fields:
        payload["event_types"] = _normalize_event_types(body.event_types)
    if "is_active" in fields and body.is_active is not None:
        payload["is_active"] = bool(body.is_active)
    supabase.table("webhook_subscriptions").update(payload).eq("id", webhook_id).eq("user_id", user_id).execute()
    return {"ok": True}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(request: Request, webhook_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("webhook_subscriptions").update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", webhook_id).eq("user_id", user_id).execute()
    return {"ok": True}


@router.post("/webhooks/{webhook_id}/test")
async def send_test_event(request: Request, webhook_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    exists = (
        supabase.table("webhook_subscriptions")
        .select("id")
        .eq("id", webhook_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not exists:
        raise HTTPException(status_code=404, detail="webhook_not_found")
    await emit_webhook_event(
        supabase=supabase,
        user_id=user_id,
        event_type="tool_called",
        payload={"test": True, "webhook_id": webhook_id},
        max_retries=max(0, int(getattr(settings, "webhook_retry_max_retries", 5))),
        base_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_base_backoff_seconds", 30))),
        max_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_max_backoff_seconds", 900))),
    )
    return {"ok": True}


@router.get("/deliveries")
async def list_deliveries(
    request: Request,
    status: str = Query("all"),
    event_type: str = Query(""),
    webhook_id: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=300),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    normalized_status = status.strip().lower()
    query = (
        supabase.table("webhook_deliveries")
        .select("id,subscription_id,event_type,status,http_status,error_message,retry_count,next_retry_at,delivered_at,created_at")
        .eq("user_id", user_id)
    )
    if normalized_status and normalized_status != "all":
        query = query.eq("status", normalized_status)
    if event_type.strip():
        query = query.eq("event_type", event_type.strip())
    if webhook_id is not None:
        query = query.eq("subscription_id", webhook_id)
    rows = query.order("created_at", desc=True).limit(limit).execute().data or []
    return {"items": rows, "count": len(rows)}


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(request: Request, delivery_id: str):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = await retry_webhook_delivery(
        supabase=supabase,
        user_id=user_id,
        delivery_id=delivery_id,
        max_retries=max(0, int(getattr(settings, "webhook_retry_max_retries", 5))),
        base_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_base_backoff_seconds", 30))),
        max_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_max_backoff_seconds", 900))),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    dead_letter_status = str(result.get("status") or "").strip().lower()
    dead_letter_alert_url = str(getattr(settings, "dead_letter_alert_webhook_url", "") or "").strip()
    if dead_letter_status == "dead_letter" and dead_letter_alert_url:
        await send_dead_letter_alert(
            webhook_url=dead_letter_alert_url,
            user_id=user_id,
            source="manual_retry",
            dead_lettered=1,
            details={
                "delivery_id": delivery_id,
                "status": dead_letter_status,
                "error_message": result.get("error_message"),
            },
        )
    return {"ok": True, "result": result}


@router.post("/deliveries/process-retries")
async def process_deliveries(request: Request, limit: int = Query(100, ge=1, le=500)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = await process_pending_webhook_retries(
        supabase=supabase,
        user_id=user_id,
        limit=limit,
        max_retries=max(0, int(getattr(settings, "webhook_retry_max_retries", 5))),
        base_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_base_backoff_seconds", 30))),
        max_backoff_seconds=max(1, int(getattr(settings, "webhook_retry_max_backoff_seconds", 900))),
    )
    dead_lettered = max(0, int(result.get("dead_lettered") or 0))
    dead_letter_alert_url = str(getattr(settings, "dead_letter_alert_webhook_url", "") or "").strip()
    dead_letter_min_count = max(1, int(getattr(settings, "dead_letter_alert_min_count", 1)))
    if dead_letter_alert_url and dead_lettered >= dead_letter_min_count:
        await send_dead_letter_alert(
            webhook_url=dead_letter_alert_url,
            user_id=user_id,
            source="process_retries",
            dead_lettered=dead_lettered,
            details={"result": result, "limit": limit},
        )
    return {"ok": True, **result}
