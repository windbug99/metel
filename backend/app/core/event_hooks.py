from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def _signature(secret: str, body: str) -> str:
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _next_retry_at(*, retry_count: int, base_seconds: int, max_seconds: int) -> str:
    seconds = min(max_seconds, base_seconds * (2 ** max(0, retry_count - 1)))
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds))).isoformat()


async def _deliver_http(*, endpoint_url: str, secret: str | None, event_type: str, payload: dict[str, Any]) -> tuple[str, int | None, str | None]:
    status = "failed"
    http_status: int | None = None
    error_message: str | None = None
    body = json.dumps(payload, ensure_ascii=False)
    headers = {"Content-Type": "application/json", "X-Event-Type": event_type}
    normalized_secret = str(secret or "").strip()
    if normalized_secret:
        headers["X-Webhook-Signature"] = _signature(normalized_secret, body)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(endpoint_url, content=body.encode("utf-8"), headers=headers)
        http_status = int(response.status_code)
        if 200 <= response.status_code < 300:
            status = "success"
        else:
            error_message = f"http_{response.status_code}"
    except Exception as exc:
        error_message = str(exc)
    return status, http_status, error_message


async def _attempt_delivery(
    *,
    supabase,
    delivery_id: int | str,
    subscription: dict[str, Any],
    event_type: str,
    delivery_payload: dict[str, Any],
    retry_count: int,
    max_retries: int,
    base_backoff_seconds: int,
    max_backoff_seconds: int,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    endpoint_url = str(subscription.get("endpoint_url") or "").strip()
    if not endpoint_url:
        update_payload = {
            "status": "failed",
            "error_message": "invalid_endpoint_url",
            "retry_count": retry_count,
            "next_retry_at": None,
            "delivered_at": None,
        }
        supabase.table("webhook_deliveries").update(update_payload).eq("id", delivery_id).execute()
        return update_payload

    status, http_status, error_message = await _deliver_http(
        endpoint_url=endpoint_url,
        secret=subscription.get("secret"),
        event_type=event_type,
        payload=delivery_payload,
    )
    if status == "success":
        update_payload = {
            "status": "success",
            "http_status": http_status,
            "error_message": None,
            "delivered_at": now_iso,
            "next_retry_at": None,
            "retry_count": retry_count,
        }
        supabase.table("webhook_deliveries").update(update_payload).eq("id", delivery_id).execute()
        supabase.table("webhook_subscriptions").update({"last_delivery_at": now_iso, "updated_at": now_iso}).eq("id", subscription.get("id")).execute()
        return update_payload

    next_retry_count = retry_count + 1
    if next_retry_count <= max_retries:
        update_payload = {
            "status": "retrying",
            "http_status": http_status,
            "error_message": error_message,
            "retry_count": next_retry_count,
            "next_retry_at": _next_retry_at(
                retry_count=next_retry_count,
                base_seconds=base_backoff_seconds,
                max_seconds=max_backoff_seconds,
            ),
            "delivered_at": None,
        }
    else:
        update_payload = {
            "status": "failed",
            "http_status": http_status,
            "error_message": error_message,
            "retry_count": next_retry_count,
            "next_retry_at": None,
            "delivered_at": None,
        }
    supabase.table("webhook_deliveries").update(update_payload).eq("id", delivery_id).execute()
    return update_payload


async def emit_webhook_event(
    *,
    supabase,
    user_id: str,
    event_type: str,
    payload: dict[str, Any],
    max_retries: int = 5,
    base_backoff_seconds: int = 30,
    max_backoff_seconds: int = 900,
) -> None:
    try:
        subscriptions = (
            supabase.table("webhook_subscriptions")
            .select("id,endpoint_url,secret,event_types,is_active")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        ).data or []
    except Exception:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    for sub in subscriptions:
        event_types = sub.get("event_types")
        allowed = event_types if isinstance(event_types, list) else []
        normalized_allowed = {str(item).strip() for item in allowed if str(item).strip()}
        if normalized_allowed and event_type not in normalized_allowed and "*" not in normalized_allowed:
            continue

        delivery_payload = {
            "event_type": event_type,
            "timestamp": now_iso,
            "user_id": user_id,
            "payload": payload,
        }
        delivery = (
            supabase.table("webhook_deliveries")
            .insert(
                {
                    "subscription_id": sub.get("id"),
                    "user_id": user_id,
                    "event_type": event_type,
                    "payload": delivery_payload,
                    "status": "pending",
                    "retry_count": 0,
                    "next_retry_at": None,
                    "created_at": now_iso,
                }
            )
            .execute()
        ).data or []
        delivery_id = delivery[0].get("id") if delivery else None
        if delivery_id is None:
            continue
        await _attempt_delivery(
            supabase=supabase,
            delivery_id=delivery_id,
            subscription=sub,
            event_type=event_type,
            delivery_payload=delivery_payload,
            retry_count=0,
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )


async def retry_webhook_delivery(
    *,
    supabase,
    user_id: str,
    delivery_id: int | str,
    max_retries: int = 5,
    base_backoff_seconds: int = 30,
    max_backoff_seconds: int = 900,
) -> dict[str, Any] | None:
    rows = (
        supabase.table("webhook_deliveries")
        .select("id,subscription_id,event_type,payload,retry_count")
        .eq("id", delivery_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    subscription_rows = (
        supabase.table("webhook_subscriptions")
        .select("id,endpoint_url,secret,is_active")
        .eq("id", row.get("subscription_id"))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if not subscription_rows:
        return None
    subscription = subscription_rows[0]
    if not bool(subscription.get("is_active")):
        update_payload = {"status": "failed", "error_message": "subscription_inactive", "next_retry_at": None}
        supabase.table("webhook_deliveries").update(update_payload).eq("id", delivery_id).eq("user_id", user_id).execute()
        return update_payload
    payload = row.get("payload")
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    return await _attempt_delivery(
        supabase=supabase,
        delivery_id=row.get("id"),
        subscription=subscription,
        event_type=str(row.get("event_type") or "tool_called"),
        delivery_payload=payload,
        retry_count=int(row.get("retry_count") or 0),
        max_retries=max_retries,
        base_backoff_seconds=base_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
    )


async def process_pending_webhook_retries(
    *,
    supabase,
    user_id: str | None = None,
    limit: int = 100,
    max_retries: int = 5,
    base_backoff_seconds: int = 30,
    max_backoff_seconds: int = 900,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    query = (
        supabase.table("webhook_deliveries")
        .select("id,user_id,subscription_id,event_type,payload,retry_count,next_retry_at,status")
        .in_("status", ["retrying", "pending"])
        .order("created_at", desc=False)
        .limit(max(1, min(limit, 500)))
    )
    if user_id:
        query = query.eq("user_id", user_id)
    rows = query.execute().data or []

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    for row in rows:
        next_retry_at = _parse_iso(row.get("next_retry_at"))
        if next_retry_at and next_retry_at > now:
            skipped += 1
            continue
        target_user_id = str(row.get("user_id") or "").strip()
        if not target_user_id:
            skipped += 1
            continue
        result = await retry_webhook_delivery(
            supabase=supabase,
            user_id=target_user_id,
            delivery_id=row.get("id"),
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )
        if result is None:
            skipped += 1
            continue
        processed += 1
        if result.get("status") == "success":
            succeeded += 1
        elif result.get("status") == "failed":
            failed += 1
    return {"processed": processed, "succeeded": succeeded, "failed": failed, "skipped": skipped}
