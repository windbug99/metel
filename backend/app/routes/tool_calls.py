from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.authz import Role, get_authz_context, require_min_role
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
    if text.startswith("github_"):
        return "github"
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
    user_ids: list[str],
    from_iso: str,
    to_iso: str | None = None,
    agent_id: int | None = None,
    api_key_ids: list[int] | None = None,
) -> list[dict]:
    scoped_user_ids = [str(item or "").strip() for item in user_ids if str(item or "").strip()]
    if not scoped_user_ids:
        return []
    if api_key_ids is not None and not api_key_ids:
        return []

    query = (
        supabase.table("tool_calls")
        .select("id,api_key_id,agent_id,tool_name,status,error_code,latency_ms,created_at")
        .gte("created_at", from_iso)
    )
    if len(scoped_user_ids) == 1:
        query = query.eq("user_id", scoped_user_ids[0])
    else:
        query = query.in_("user_id", scoped_user_ids)
    if agent_id is not None:
        query = query.eq("agent_id", agent_id)
    if api_key_ids is not None:
        if len(api_key_ids) == 1:
            query = query.eq("api_key_id", api_key_ids[0])
        else:
            query = query.in_("api_key_id", api_key_ids)
    if to_iso:
        query = query.lte("created_at", to_iso)
    return query.execute().data or []


def _normalize_optional_int(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _resolve_scoped_user_ids(
    *,
    supabase,
    authz_ctx,
    request_user_id: str,
    organization_id: int | None,
) -> list[str]:
    if organization_id is None:
        return [request_user_id]
    if authz_ctx.role == Role.MEMBER:
        raise HTTPException(status_code=403, detail={"code": "access_denied", "reason": "member_org_scope_forbidden"})
    if organization_id not in authz_ctx.org_ids:
        raise HTTPException(status_code=403, detail={"code": "access_denied", "reason": "organization_scope_forbidden"})

    member_rows = (
        supabase.table("org_memberships")
        .select("user_id")
        .eq("organization_id", organization_id)
        .execute()
    ).data or []
    scoped_user_ids = [str(row.get("user_id") or "").strip() for row in member_rows if str(row.get("user_id") or "").strip()]
    return scoped_user_ids or [request_user_id]


def _resolve_scoped_api_key_ids(
    *,
    supabase,
    authz_ctx,
    scoped_user_ids: list[str],
    team_id: int | None,
) -> list[int] | None:
    if team_id is None:
        return None

    if authz_ctx.role == Role.MEMBER and team_id not in authz_ctx.team_ids:
        raise HTTPException(status_code=403, detail={"code": "access_denied", "reason": "team_scope_forbidden"})

    if authz_ctx.role in {Role.ADMIN, Role.OWNER}:
        team_rows = (
            supabase.table("teams")
            .select("id,organization_id")
            .eq("id", team_id)
            .limit(1)
            .execute()
        ).data or []
        if not team_rows:
            return []
        org_id_raw = team_rows[0].get("organization_id")
        try:
            org_id = int(org_id_raw) if org_id_raw is not None else None
        except (TypeError, ValueError):
            org_id = None
        has_org_scope = org_id is not None and org_id in authz_ctx.org_ids
        has_team_scope = team_id in authz_ctx.team_ids
        if not has_org_scope and not has_team_scope:
            raise HTTPException(status_code=403, detail={"code": "access_denied", "reason": "team_scope_forbidden"})

    key_query = supabase.table("api_keys").select("id").eq("team_id", team_id)
    normalized_user_ids = [str(item or "").strip() for item in scoped_user_ids if str(item or "").strip()]
    if normalized_user_ids:
        if len(normalized_user_ids) == 1:
            key_query = key_query.eq("user_id", normalized_user_ids[0])
        else:
            key_query = key_query.in_("user_id", normalized_user_ids)
    key_rows = key_query.execute().data or []
    key_ids: list[int] = []
    for row in key_rows:
        raw = row.get("id")
        try:
            if raw is not None:
                key_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return sorted(set(key_ids))


def _resolve_scope_filters(
    *,
    supabase,
    authz_ctx,
    request_user_id: str,
    organization_id: int | None,
    team_id: int | None,
) -> tuple[list[str], list[int] | None]:
    normalized_organization_id = _normalize_optional_int(organization_id)
    normalized_team_id = _normalize_optional_int(team_id)
    scoped_user_ids = _resolve_scoped_user_ids(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=request_user_id,
        organization_id=normalized_organization_id,
    )
    scoped_api_key_ids = _resolve_scoped_api_key_ids(
        supabase=supabase,
        authz_ctx=authz_ctx,
        scoped_user_ids=scoped_user_ids,
        team_id=normalized_team_id,
    )
    return scoped_user_ids, scoped_api_key_ids


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
        if connector in {"notion", "linear", "github"} and current >= 5 and current > previous * 1.5:
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
    agent_id: int | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
    from_: str = Query(default="", alias="from"),
    to: str = Query(default=""),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    normalized_status = status.strip().lower()
    if normalized_status not in {"all", "success", "fail"}:
        normalized_status = "all"
    normalized_tool_name = tool_name.strip()
    from_iso = _normalize_iso_datetime(from_, field_name="from")
    to_iso = _normalize_iso_datetime(to, field_name="to")
    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )

    if scoped_api_key_ids is not None and not scoped_api_key_ids:
        calls = []
    else:
        query = supabase.table("tool_calls").select("id,api_key_id,agent_id,tool_name,status,error_code,latency_ms,created_at")
        if len(scoped_user_ids) == 1:
            query = query.eq("user_id", scoped_user_ids[0])
        else:
            query = query.in_("user_id", scoped_user_ids)
        if scoped_api_key_ids is not None:
            if len(scoped_api_key_ids) == 1:
                query = query.eq("api_key_id", scoped_api_key_ids[0])
            else:
                query = query.in_("api_key_id", scoped_api_key_ids)
        if normalized_status != "all":
            query = query.eq("status", normalized_status)
        if normalized_tool_name:
            query = query.eq("tool_name", normalized_tool_name)
        if api_key_id is not None:
            query = query.eq("api_key_id", api_key_id)
        if agent_id is not None:
            query = query.eq("agent_id", agent_id)
        if from_iso:
            query = query.gte("created_at", from_iso)
        if to_iso:
            query = query.lte("created_at", to_iso)
        calls_result = query.order("created_at", desc=True).limit(limit).execute()
        calls = calls_result.data or []

    if scoped_api_key_ids is not None and not scoped_api_key_ids:
        keys = []
    else:
        key_query = supabase.table("api_keys").select("id,name,key_prefix")
        if len(scoped_user_ids) == 1:
            key_query = key_query.eq("user_id", scoped_user_ids[0])
        else:
            key_query = key_query.in_("user_id", scoped_user_ids)
        if scoped_api_key_ids is not None:
            if len(scoped_api_key_ids) == 1:
                key_query = key_query.eq("id", scoped_api_key_ids[0])
            else:
                key_query = key_query.in_("id", scoped_api_key_ids)
        keys = key_query.execute().data or []
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
                "agent_id": row.get("agent_id"),
            }
        )

    window_start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    if scoped_api_key_ids is not None and not scoped_api_key_ids:
        stats_rows = []
    else:
        stats_query = supabase.table("tool_calls").select("status,error_code").gte("created_at", window_start)
        if len(scoped_user_ids) == 1:
            stats_query = stats_query.eq("user_id", scoped_user_ids[0])
        else:
            stats_query = stats_query.in_("user_id", scoped_user_ids)
        if scoped_api_key_ids is not None:
            if len(scoped_api_key_ids) == 1:
                stats_query = stats_query.eq("api_key_id", scoped_api_key_ids[0])
            else:
                stats_query = stats_query.in_("api_key_id", scoped_api_key_ids)
        if normalized_status != "all":
            stats_query = stats_query.eq("status", normalized_status)
        if normalized_tool_name:
            stats_query = stats_query.eq("tool_name", normalized_tool_name)
        if api_key_id is not None:
            stats_query = stats_query.eq("api_key_id", api_key_id)
        if agent_id is not None:
            stats_query = stats_query.eq("agent_id", agent_id)
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
    agent_id: int | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)
    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )

    now = datetime.now(timezone.utc)
    current_from = (now - timedelta(hours=hours)).isoformat()
    previous_from = (now - timedelta(hours=hours * 2)).isoformat()
    previous_to = current_from

    current_rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=current_from,
        agent_id=agent_id,
        api_key_ids=scoped_api_key_ids,
    )
    previous_rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=previous_from,
        to_iso=previous_to,
        agent_id=agent_id,
        api_key_ids=scoped_api_key_ids,
    )

    key_query = supabase.table("api_keys").select("id,name,key_prefix")
    if len(scoped_user_ids) == 1:
        key_query = key_query.eq("user_id", scoped_user_ids[0])
    else:
        key_query = key_query.in_("user_id", scoped_user_ids)
    if scoped_api_key_ids is not None:
        if len(scoped_api_key_ids) == 1:
            key_query = key_query.eq("id", scoped_api_key_ids[0])
        elif len(scoped_api_key_ids) > 1:
            key_query = key_query.in_("id", scoped_api_key_ids)
    key_rows = key_query.execute().data or []
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
    agent_id: int | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )
    normalized_bucket = bucket.strip().lower()
    if normalized_bucket not in {"hour", "day"}:
        normalized_bucket = "day"
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=since.isoformat(),
        agent_id=agent_id,
        api_key_ids=scoped_api_key_ids,
    )

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
    agent_id: int | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=since,
        agent_id=agent_id,
        api_key_ids=scoped_api_key_ids,
    )
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
    agent_id: int | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=since,
        agent_id=agent_id,
        api_key_ids=scoped_api_key_ids,
    )

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


@router.get("/agents")
async def tool_calls_agents(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    organization_id: int | None = Query(default=None),
    team_id: int | None = Query(default=None),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    scoped_user_ids, scoped_api_key_ids = _resolve_scope_filters(
        supabase=supabase,
        authz_ctx=authz_ctx,
        request_user_id=user_id,
        organization_id=organization_id,
        team_id=team_id,
    )
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _query_tool_call_rows(
        supabase=supabase,
        user_ids=scoped_user_ids,
        from_iso=since,
        api_key_ids=scoped_api_key_ids,
    )
    agent_rows = (
        supabase.table("agents")
        .select("id,name,team_id,organization_id")
        .execute()
    ).data or []
    agent_map = {str(row.get("id")): row for row in agent_rows if row.get("id") is not None}

    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "success": 0, "fail": 0, "blocked": 0})
    for row in rows:
        key = str(row.get("agent_id") or "unassigned")
        bucket = buckets[key]
        bucket["calls"] += 1
        if row.get("status") == "success":
            bucket["success"] += 1
        if row.get("status") == "fail":
            bucket["fail"] += 1
        if row.get("error_code") == "policy_blocked":
            bucket["blocked"] += 1

    items: list[dict] = []
    for key, agg in sorted(buckets.items(), key=lambda item: item[1]["calls"], reverse=True):
        agent_row = agent_map.get(key) if key != "unassigned" else None
        calls = int(agg["calls"])
        items.append(
            {
                "agent_id": None if key == "unassigned" else int(key),
                "agent_name": agent_row.get("name") if agent_row else None,
                "team_id": agent_row.get("team_id") if agent_row else None,
                "organization_id": agent_row.get("organization_id") if agent_row else None,
                "calls": calls,
                "success_rate": _ratio(int(agg["success"]), calls),
                "fail_rate": _ratio(int(agg["fail"]), calls),
                "blocked_rate": _ratio(int(agg["blocked"]), calls),
            }
        )
    return {"days": days, "items": items}
