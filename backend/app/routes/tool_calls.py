from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/tool-calls", tags=["tool-calls"])


def _normalize_iso_datetime(value: str | None, *, field_name: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_datetime:{field_name}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


@router.get("")
async def list_tool_calls(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    status: str = Query("all"),
    tool_name: str = Query(""),
    api_key_id: int | None = Query(default=None),
    from_: str = Query(default="", alias="from"),
    to: str = Query(default=""),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    normalized_status = status.strip().lower()
    if normalized_status not in {"all", "success", "fail"}:
        normalized_status = "all"
    normalized_tool_name = tool_name.strip()
    from_iso = _normalize_iso_datetime(from_, field_name="from")
    to_iso = _normalize_iso_datetime(to, field_name="to")

    query = (
        supabase.table("tool_calls")
        .select("id,api_key_id,tool_name,status,error_code,latency_ms,created_at")
        .eq("user_id", user_id)
    )
    if normalized_status != "all":
        query = query.eq("status", normalized_status)
    if normalized_tool_name:
        query = query.eq("tool_name", normalized_tool_name)
    if api_key_id is not None:
        query = query.eq("api_key_id", api_key_id)
    if from_iso:
        query = query.gte("created_at", from_iso)
    if to_iso:
        query = query.lte("created_at", to_iso)
    calls_result = query.order("created_at", desc=True).limit(limit).execute()
    calls = calls_result.data or []

    key_result = (
        supabase.table("api_keys")
        .select("id,name,key_prefix")
        .eq("user_id", user_id)
        .execute()
    )
    keys = key_result.data or []
    key_map = {str(row.get("id")): row for row in keys}

    items = []
    success_count = 0
    fail_count = 0
    for row in calls:
        status = str(row.get("status") or "")
        if status == "success":
            success_count += 1
        elif status == "fail":
            fail_count += 1
        api_key_row = key_map.get(str(row.get("api_key_id")))
        items.append(
            {
                "id": row.get("id"),
                "tool_name": row.get("tool_name"),
                "status": row.get("status"),
                "error_code": row.get("error_code"),
                "latency_ms": row.get("latency_ms"),
                "created_at": row.get("created_at"),
                "api_key": {
                    "id": api_key_row.get("id") if api_key_row else row.get("api_key_id"),
                    "name": api_key_row.get("name") if api_key_row else None,
                    "key_prefix": api_key_row.get("key_prefix") if api_key_row else None,
                },
            }
        )

    window_start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    stats_query = (
        supabase.table("tool_calls")
        .select("status")
        .eq("user_id", user_id)
        .gte("created_at", window_start)
    )
    if normalized_status != "all":
        stats_query = stats_query.eq("status", normalized_status)
    if normalized_tool_name:
        stats_query = stats_query.eq("tool_name", normalized_tool_name)
    if api_key_id is not None:
        stats_query = stats_query.eq("api_key_id", api_key_id)
    if from_iso:
        stats_query = stats_query.gte("created_at", from_iso)
    if to_iso:
        stats_query = stats_query.lte("created_at", to_iso)
    stats_result = stats_query.execute()
    stats_rows = stats_result.data or []
    calls_24h = len(stats_rows)
    success_24h = len([row for row in stats_rows if row.get("status") == "success"])
    fail_24h = len([row for row in stats_rows if row.get("status") == "fail"])

    return {
        "items": items,
        "count": len(items),
        "summary": {
            "recent_success": success_count,
            "recent_fail": fail_count,
            "calls_24h": calls_24h,
            "success_24h": success_24h,
            "fail_24h": fail_24h,
        },
    }
