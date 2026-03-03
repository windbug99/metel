from __future__ import annotations

import math
from collections import defaultdict
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


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _avg_latency_ms(rows: list[dict]) -> float:
    latencies = [int(row.get("latency_ms") or 0) for row in rows]
    if not latencies:
        return 0.0
    return round(sum(latencies) / len(latencies), 2)


def _p95_latency_ms(rows: list[dict]) -> int:
    latencies = sorted(int(row.get("latency_ms") or 0) for row in rows)
    if not latencies:
        return 0
    index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    return latencies[index]


def _connector_from_tool(tool_name: str | None) -> str:
    text = str(tool_name or "").strip().lower()
    if text.startswith("notion_"):
        return "notion"
    if text.startswith("linear_"):
        return "linear"
    return "other"


def _error_category(error_code: str | None) -> str:
    code = str(error_code or "").strip()
    if code in {"missing_required_field", "invalid_field_type"}:
        return "schema_error"
    if code in {"resolve_not_found", "resolve_ambiguous"}:
        return "resolver_failed"
    if code == "policy_blocked":
        return "policy_blocked"
    if code == "upstream_temporary_failure":
        return "upstream_429_or_5xx"
    if code == "timeout":
        return "timeout"
    if code == "quota_exceeded":
        return "quota_exceeded"
    if not code:
        return "unknown"
    return "other"


def _query_tool_call_rows(
    *,
    supabase,
    user_id: str,
    from_iso: str,
    to_iso: str | None = None,
) -> list[dict]:
    query = (
        supabase.table("tool_calls")
        .select("id,api_key_id,tool_name,status,error_code,latency_ms,created_at")
        .eq("user_id", user_id)
        .gte("created_at", from_iso)
    )
    if to_iso:
        query = query.lte("created_at", to_iso)
    return query.execute().data or []


def _kpi_summary(rows: list[dict]) -> dict:
    total_calls = len(rows)
    success_count = len([row for row in rows if row.get("status") == "success"])
    fail_count = len([row for row in rows if row.get("status") == "fail"])
    blocked_count = len([row for row in rows if row.get("error_code") == "policy_blocked"])
    retryable_count = len([row for row in rows if row.get("error_code") == "upstream_temporary_failure"])
    return {
        "total_calls": total_calls,
        "success_rate": _ratio(success_count, total_calls),
        "fail_rate": _ratio(fail_count, total_calls),
        "avg_latency_ms": _avg_latency_ms(rows),
        "p95_latency_ms": _p95_latency_ms(rows),
        "retry_rate": _ratio(retryable_count, total_calls),
        "policy_block_rate": _ratio(blocked_count, total_calls),
        "success_count": success_count,
        "fail_count": fail_count,
        "policy_blocked_count": blocked_count,
    }


def _top_tool_counts(rows: list[dict], *, predicate) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        if not predicate(row):
            continue
        name = str(row.get("tool_name") or "").strip() or "unknown_tool"
        counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return [{"tool_name": name, "count": count} for name, count in ranked]


def _anomaly_rows(
    *,
    current_rows: list[dict],
    previous_rows: list[dict],
    key_map: dict[str, dict],
) -> list[dict]:
    anomalies: list[dict] = []
    current_fail = len([row for row in current_rows if row.get("status") == "fail"])
    previous_fail = len([row for row in previous_rows if row.get("status") == "fail"])
    if current_fail >= 10 and current_fail > previous_fail * 1.5:
        anomalies.append(
            {
                "type": "failure_surge",
                "severity": "high",
                "message": "Failed calls increased sharply vs previous window.",
                "context": {"current_fail": current_fail, "previous_fail": previous_fail},
            }
        )

    current_upstream = len([row for row in current_rows if row.get("error_code") == "upstream_temporary_failure"])
    previous_upstream = len([row for row in previous_rows if row.get("error_code") == "upstream_temporary_failure"])
    if current_upstream >= 5 and current_upstream > previous_upstream * 1.5:
        anomalies.append(
            {
                "type": "upstream_429_5xx_surge",
                "severity": "high",
                "message": "Upstream temporary failures (429/5xx) increased sharply.",
                "context": {"current": current_upstream, "previous": previous_upstream},
            }
        )

    current_key_counts: dict[str, int] = {}
    previous_key_counts: dict[str, int] = {}
    for row in current_rows:
        key = str(row.get("api_key_id") or "")
        if key:
            current_key_counts[key] = current_key_counts.get(key, 0) + 1
    for row in previous_rows:
        key = str(row.get("api_key_id") or "")
        if key:
            previous_key_counts[key] = previous_key_counts.get(key, 0) + 1
    for key_id, current in sorted(current_key_counts.items(), key=lambda item: item[1], reverse=True)[:3]:
        previous = previous_key_counts.get(key_id, 0)
        if current >= 20 and current > max(10, previous * 2):
            key_row = key_map.get(key_id) or {}
            anomalies.append(
                {
                    "type": "api_key_spike",
                    "severity": "medium",
                    "message": "API key call volume increased sharply.",
                    "context": {
                        "api_key_id": key_row.get("id") or key_id,
                        "api_key_name": key_row.get("name"),
                        "current": current,
                        "previous": previous,
                    },
                }
            )

    current_connector_fails: dict[str, int] = {}
    previous_connector_fails: dict[str, int] = {}
    for row in current_rows:
        if row.get("status") != "fail":
            continue
        connector = _connector_from_tool(str(row.get("tool_name") or ""))
        current_connector_fails[connector] = current_connector_fails.get(connector, 0) + 1
    for row in previous_rows:
        if row.get("status") != "fail":
            continue
        connector = _connector_from_tool(str(row.get("tool_name") or ""))
        previous_connector_fails[connector] = previous_connector_fails.get(connector, 0) + 1
    for connector, current in current_connector_fails.items():
        previous = previous_connector_fails.get(connector, 0)
        if connector in {"notion", "linear"} and current >= 5 and current > previous * 1.5:
            anomalies.append(
                {
                    "type": "connector_error_surge",
                    "severity": "medium",
                    "message": f"{connector} connector errors increased sharply.",
                    "context": {"connector": connector, "current": current, "previous": previous},
                }
            )

    return anomalies[:10]


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
    stats_query = supabase.table("tool_calls").select("status,error_code").eq("user_id", user_id).gte("created_at", window_start)
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
    policy_blocked_24h = len([row for row in stats_rows if row.get("error_code") == "policy_blocked"])
    quota_exceeded_24h = len([row for row in stats_rows if row.get("error_code") == "quota_exceeded"])
    policy_override_allowed_24h = len([row for row in stats_rows if row.get("error_code") == "policy_override_allowed"])
    access_denied_24h = len(
        [
            row
            for row in stats_rows
            if str(row.get("error_code") or "") in {"access_denied", "service_not_allowed", "tool_not_allowed_for_api_key"}
        ]
    )
    resolve_fail_24h = len(
        [
            row
            for row in stats_rows
            if str(row.get("error_code") or "") in {"resolve_not_found", "resolve_ambiguous"}
        ]
    )
    upstream_temporary_24h = len([row for row in stats_rows if row.get("error_code") == "upstream_temporary_failure"])

    fail_error_counts: dict[str, int] = {}
    for row in stats_rows:
        if row.get("status") != "fail":
            continue
        code = str(row.get("error_code") or "").strip() or "unknown_fail"
        fail_error_counts[code] = fail_error_counts.get(code, 0) + 1
    top_failure_codes = sorted(fail_error_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    return {
        "items": items,
        "count": len(items),
        "summary": {
            "recent_success": success_count,
            "recent_fail": fail_count,
            "calls_24h": calls_24h,
            "success_24h": success_24h,
            "fail_24h": fail_24h,
            "fail_rate_24h": _ratio(fail_24h, calls_24h),
            "blocked_rate_24h": _ratio(policy_blocked_24h, calls_24h),
            "retryable_fail_rate_24h": _ratio(upstream_temporary_24h, calls_24h),
            "policy_blocked_24h": policy_blocked_24h,
            "quota_exceeded_24h": quota_exceeded_24h,
            "access_denied_24h": access_denied_24h,
            "high_risk_allowed_24h": policy_override_allowed_24h,
            "policy_override_usage_24h": _ratio(policy_override_allowed_24h, calls_24h),
            "resolve_fail_24h": resolve_fail_24h,
            "upstream_temporary_24h": upstream_temporary_24h,
            "top_failure_codes": [{"error_code": code, "count": count} for code, count in top_failure_codes],
        },
    }


@router.get("/overview")
async def tool_calls_overview(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    now = datetime.now(timezone.utc)
    current_from = (now - timedelta(hours=hours)).isoformat()
    previous_from = (now - timedelta(hours=hours * 2)).isoformat()
    previous_to = current_from

    current_rows = _query_tool_call_rows(supabase=supabase, user_id=user_id, from_iso=current_from)
    previous_rows = _query_tool_call_rows(supabase=supabase, user_id=user_id, from_iso=previous_from, to_iso=previous_to)

    key_rows = (
        supabase.table("api_keys")
        .select("id,name,key_prefix")
        .eq("user_id", user_id)
        .execute()
    ).data or []
    key_map = {str(row.get("id")): row for row in key_rows}

    return {
        "window_hours": hours,
        "kpis": _kpi_summary(current_rows),
        "top": {
            "called_tools": _top_tool_counts(current_rows, predicate=lambda _row: True),
            "failed_tools": _top_tool_counts(current_rows, predicate=lambda row: row.get("status") == "fail"),
            "blocked_tools": _top_tool_counts(current_rows, predicate=lambda row: row.get("error_code") == "policy_blocked"),
        },
        "anomalies": _anomaly_rows(current_rows=current_rows, previous_rows=previous_rows, key_map=key_map),
    }


@router.get("/trends")
async def tool_calls_trends(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    bucket: str = Query("day"),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    normalized_bucket = bucket.strip().lower()
    if normalized_bucket not in {"hour", "day"}:
        normalized_bucket = "day"
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    rows = _query_tool_call_rows(supabase=supabase, user_id=user_id, from_iso=since.isoformat())

    if normalized_bucket == "hour":
        start = since.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    else:
        start = since.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)

    bucket_index: dict[str, dict] = {}
    cursor = start
    while cursor <= now:
        key = cursor.isoformat()
        bucket_index[key] = {"calls": 0, "success": 0, "fail": 0, "blocked": 0, "latency_sum": 0}
        cursor += step

    for row in rows:
        created = _parse_iso_datetime(row.get("created_at"))
        if not created:
            continue
        if normalized_bucket == "hour":
            slot = created.replace(minute=0, second=0, microsecond=0)
        else:
            slot = created.replace(hour=0, minute=0, second=0, microsecond=0)
        key = slot.isoformat()
        if key not in bucket_index:
            continue
        slot_item = bucket_index[key]
        slot_item["calls"] += 1
        if row.get("status") == "success":
            slot_item["success"] += 1
        if row.get("status") == "fail":
            slot_item["fail"] += 1
        if row.get("error_code") == "policy_blocked":
            slot_item["blocked"] += 1
        slot_item["latency_sum"] += int(row.get("latency_ms") or 0)

    items: list[dict] = []
    for key, agg in sorted(bucket_index.items(), key=lambda item: item[0]):
        calls = int(agg["calls"])
        avg_latency = round(agg["latency_sum"] / calls, 2) if calls else 0.0
        items.append(
            {
                "bucket_start": key,
                "calls": calls,
                "success_rate": _ratio(int(agg["success"]), calls),
                "fail_rate": _ratio(int(agg["fail"]), calls),
                "blocked_rate": _ratio(int(agg["blocked"]), calls),
                "avg_latency_ms": avg_latency,
            }
        )

    return {"days": days, "bucket": normalized_bucket, "items": items}


@router.get("/failure-breakdown")
async def tool_calls_failure_breakdown(
    request: Request,
    days: int = Query(7, ge=1, le=30),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _query_tool_call_rows(supabase=supabase, user_id=user_id, from_iso=since)
    fail_rows = [row for row in rows if row.get("status") == "fail"]

    category_counts: dict[str, int] = defaultdict(int)
    error_counts: dict[str, int] = defaultdict(int)
    for row in fail_rows:
        code = str(row.get("error_code") or "").strip() or "unknown"
        error_counts[code] += 1
        category_counts[_error_category(code)] += 1

    categories = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
    error_codes = sorted(error_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    total = len(fail_rows)
    return {
        "days": days,
        "total_failures": total,
        "categories": [
            {"category": name, "count": count, "ratio": _ratio(count, total)}
            for name, count in categories
        ],
        "error_codes": [{"error_code": code, "count": count} for code, count in error_codes],
    }


@router.get("/connectors")
async def tool_calls_connectors(
    request: Request,
    days: int = Query(7, ge=1, le=30),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _query_tool_call_rows(supabase=supabase, user_id=user_id, from_iso=since)

    connector_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        connector_rows[_connector_from_tool(str(row.get("tool_name") or ""))].append(row)

    items: list[dict] = []
    for connector, group in sorted(connector_rows.items(), key=lambda item: item[0]):
        if connector == "other":
            continue
        fail_count = len([row for row in group if row.get("status") == "fail"])
        code_counts: dict[str, int] = defaultdict(int)
        for row in group:
            if row.get("status") != "fail":
                continue
            code = str(row.get("error_code") or "").strip() or "unknown"
            code_counts[code] += 1
        top_error_codes = sorted(code_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        items.append(
            {
                "connector": connector,
                "calls": len(group),
                "fail_rate": _ratio(fail_count, len(group)),
                "avg_latency_ms": _avg_latency_ms(group),
                "top_error_codes": [{"error_code": code, "count": count} for code, count in top_error_codes],
            }
        )

    return {"days": days, "items": items}
