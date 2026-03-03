from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditSettingsUpdateRequest(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    export_enabled: bool | None = None
    masking_policy: dict[str, Any] | None = None


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


def _decision(status: str, error_code: str | None) -> str:
    code = str(error_code or "")
    if status == "success":
        if code == "policy_override_allowed":
            return "policy_override_allowed"
        return "allowed"
    if code == "policy_blocked":
        return "policy_blocked"
    if code in {"access_denied", "service_not_allowed", "tool_not_allowed_for_api_key"}:
        return "access_denied"
    return "failed"


def _query_audit_rows(
    *,
    supabase,
    user_id: str,
    limit: int,
    status: str,
    tool_name: str,
    api_key_id: int | None,
    error_code: str,
    connector: str,
    from_iso: str | None,
    to_iso: str | None,
) -> list[dict]:
    query = (
        supabase.table("tool_calls")
        .select(
            "id,request_id,trace_id,api_key_id,tool_name,connector,status,error_code,latency_ms,"
            "request_payload,resolved_payload,risk_result,upstream_status,retry_count,backoff_ms,masked_fields,created_at"
        )
        .eq("user_id", user_id)
    )
    if status != "all":
        query = query.eq("status", status)
    if tool_name:
        query = query.eq("tool_name", tool_name)
    if api_key_id is not None:
        query = query.eq("api_key_id", api_key_id)
    if error_code:
        query = query.eq("error_code", error_code)
    if connector:
        query = query.eq("connector", connector)
    if from_iso:
        query = query.gte("created_at", from_iso)
    if to_iso:
        query = query.lte("created_at", to_iso)
    return query.order("created_at", desc=True).limit(limit).execute().data or []


def _query_api_key_map(*, supabase, user_id: str) -> dict[str, dict]:
    key_rows = (
        supabase.table("api_keys")
        .select("id,name,key_prefix")
        .eq("user_id", user_id)
        .execute()
    ).data or []
    return {str(item.get("id")): item for item in key_rows}


def _default_audit_settings(*, user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "retention_days": 90,
        "export_enabled": True,
        "masking_policy": {"mask_keys": ["token", "access_token", "authorization", "password", "secret"]},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_audit_settings(*, supabase, user_id: str) -> dict[str, Any]:
    rows = (
        supabase.table("audit_settings")
        .select("user_id,retention_days,export_enabled,masking_policy,updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    ).data or []
    if rows:
        row = rows[0]
        if not isinstance(row.get("masking_policy"), dict):
            row["masking_policy"] = {}
        return row
    return _default_audit_settings(user_id=user_id)


@router.get("/events")
async def list_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    status: str = Query("all"),
    tool_name: str = Query(""),
    api_key_id: int | None = Query(default=None),
    error_code: str = Query(""),
    connector: str = Query(""),
    decision: str = Query("all"),
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
    normalized_error_code = error_code.strip()
    normalized_connector = str(connector or "").strip().lower()
    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in {"all", "allowed", "policy_blocked", "access_denied", "failed", "policy_override_allowed"}:
        normalized_decision = "all"
    from_iso = _normalize_iso_datetime(from_, field_name="from")
    to_iso = _normalize_iso_datetime(to, field_name="to")

    rows = _query_audit_rows(
        supabase=supabase,
        user_id=user_id,
        limit=limit,
        status=normalized_status,
        tool_name=normalized_tool_name,
        api_key_id=api_key_id,
        error_code=normalized_error_code,
        connector=normalized_connector,
        from_iso=from_iso,
        to_iso=to_iso,
    )
    key_map = _query_api_key_map(supabase=supabase, user_id=user_id)

    items: list[dict] = []
    decision_counts: dict[str, int] = {
        "allowed": 0,
        "policy_override_allowed": 0,
        "policy_blocked": 0,
        "access_denied": 0,
        "failed": 0,
    }
    for row in rows:
        status_value = str(row.get("status") or "")
        err = row.get("error_code")
        decision = _decision(status_value, err)
        if normalized_decision != "all" and decision != normalized_decision:
            continue
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

        api_key_row = key_map.get(str(row.get("api_key_id")))
        items.append(
            {
                "id": row.get("id"),
                "request_id": row.get("request_id"),
                "trace_id": row.get("trace_id"),
                "timestamp": row.get("created_at"),
                "action": {"tool_name": row.get("tool_name")},
                "actor": {
                    "user_id": user_id,
                    "api_key": {
                        "id": api_key_row.get("id") if api_key_row else row.get("api_key_id"),
                        "name": api_key_row.get("name") if api_key_row else None,
                        "key_prefix": api_key_row.get("key_prefix") if api_key_row else None,
                    },
                },
                "outcome": {
                    "decision": decision,
                    "status": status_value,
                    "error_code": err,
                    "upstream_status": row.get("upstream_status"),
                    "latency_ms": row.get("latency_ms"),
                },
            }
        )

    return {
        "items": items,
        "count": len(items),
        "summary": {
            "allowed_count": decision_counts.get("allowed", 0),
            "high_risk_allowed_count": decision_counts.get("policy_override_allowed", 0),
            "policy_override_usage": (
                round(decision_counts.get("policy_override_allowed", 0) / len(items), 4) if items else 0.0
            ),
            "policy_blocked_count": decision_counts.get("policy_blocked", 0),
            "access_denied_count": decision_counts.get("access_denied", 0),
            "failed_count": decision_counts.get("failed", 0),
        },
    }


@router.get("/export")
async def export_audit_events(
    request: Request,
    format: str = Query("jsonl"),
    limit: int = Query(200, ge=1, le=2000),
    status: str = Query("all"),
    tool_name: str = Query(""),
    api_key_id: int | None = Query(default=None),
    error_code: str = Query(""),
    connector: str = Query(""),
    decision: str = Query("all"),
    from_: str = Query(default="", alias="from"),
    to: str = Query(default=""),
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    audit_settings = _load_audit_settings(supabase=supabase, user_id=user_id)
    if not bool(audit_settings.get("export_enabled", True)):
        raise HTTPException(status_code=403, detail="audit_export_disabled")

    export_format = format.strip().lower()
    if export_format not in {"jsonl", "csv"}:
        raise HTTPException(status_code=400, detail="invalid_export_format")

    normalized_status = status.strip().lower()
    if normalized_status not in {"all", "success", "fail"}:
        normalized_status = "all"
    normalized_tool_name = tool_name.strip()
    normalized_error_code = error_code.strip()
    normalized_connector = str(connector or "").strip().lower()
    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in {"all", "allowed", "policy_blocked", "access_denied", "failed", "policy_override_allowed"}:
        normalized_decision = "all"
    from_iso = _normalize_iso_datetime(from_, field_name="from")
    to_iso = _normalize_iso_datetime(to, field_name="to")

    rows = _query_audit_rows(
        supabase=supabase,
        user_id=user_id,
        limit=limit,
        status=normalized_status,
        tool_name=normalized_tool_name,
        api_key_id=api_key_id,
        error_code=normalized_error_code,
        connector=normalized_connector,
        from_iso=from_iso,
        to_iso=to_iso,
    )
    key_map = _query_api_key_map(supabase=supabase, user_id=user_id)

    normalized_rows: list[dict] = []
    for row in rows:
        row_decision = _decision(str(row.get("status") or ""), row.get("error_code"))
        if normalized_decision != "all" and row_decision != normalized_decision:
            continue
        api_key_row = key_map.get(str(row.get("api_key_id")))
        normalized_rows.append(
            {
                "id": row.get("id"),
                "request_id": row.get("request_id"),
                "trace_id": row.get("trace_id"),
                "timestamp": row.get("created_at"),
                "tool_name": row.get("tool_name"),
                "connector": row.get("connector"),
                "status": row.get("status"),
                "decision": row_decision,
                "error_code": row.get("error_code"),
                "latency_ms": row.get("latency_ms"),
                "upstream_status": row.get("upstream_status"),
                "retry_count": row.get("retry_count"),
                "backoff_ms": row.get("backoff_ms"),
                "api_key_id": row.get("api_key_id"),
                "api_key_name": api_key_row.get("name") if api_key_row else None,
                "api_key_prefix": api_key_row.get("key_prefix") if api_key_row else None,
            }
        )

    if export_format == "jsonl":
        body = "\n".join(json.dumps(item, ensure_ascii=False) for item in normalized_rows)
        return Response(
            content=body,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": 'attachment; filename="audit-events.jsonl"'},
        )

    output = StringIO()
    headers = [
        "id",
        "request_id",
        "trace_id",
        "timestamp",
        "tool_name",
        "connector",
        "status",
        "decision",
        "error_code",
        "latency_ms",
        "upstream_status",
        "retry_count",
        "backoff_ms",
        "api_key_id",
        "api_key_name",
        "api_key_prefix",
    ]
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for item in normalized_rows:
        writer.writerow({field: item.get(field, "") or "" for field in headers})
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
    )


@router.get("/settings")
async def get_audit_settings(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    row = _load_audit_settings(supabase=supabase, user_id=user_id)
    return {
        "retention_days": int(row.get("retention_days") or 90),
        "export_enabled": bool(row.get("export_enabled", True)),
        "masking_policy": row.get("masking_policy") if isinstance(row.get("masking_policy"), dict) else {},
        "updated_at": row.get("updated_at"),
    }


@router.patch("/settings")
async def update_audit_settings(request: Request, body: AuditSettingsUpdateRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    current = _load_audit_settings(supabase=supabase, user_id=user_id)
    payload = {
        "user_id": user_id,
        "retention_days": int(body.retention_days) if body.retention_days is not None else int(current.get("retention_days") or 90),
        "export_enabled": bool(body.export_enabled) if body.export_enabled is not None else bool(current.get("export_enabled", True)),
        "masking_policy": body.masking_policy if isinstance(body.masking_policy, dict) else current.get("masking_policy") or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (
        supabase.table("audit_settings")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )
    return {
        "retention_days": payload["retention_days"],
        "export_enabled": payload["export_enabled"],
        "masking_policy": payload["masking_policy"],
        "updated_at": payload["updated_at"],
    }


@router.get("/events/{event_id}")
async def get_audit_event_detail(
    request: Request,
    event_id: int,
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    row = (
        supabase.table("tool_calls")
        .select(
            "id,request_id,trace_id,api_key_id,tool_name,connector,status,error_code,latency_ms,"
            "request_payload,resolved_payload,risk_result,upstream_status,retry_count,backoff_ms,masked_fields,created_at"
        )
        .eq("user_id", user_id)
        .eq("id", event_id)
        .limit(1)
        .execute()
    ).data or []
    if not row:
        raise HTTPException(status_code=404, detail="audit_event_not_found")
    item = row[0]

    api_key_row = (
        supabase.table("api_keys")
        .select("id,name,key_prefix")
        .eq("user_id", user_id)
        .eq("id", item.get("api_key_id"))
        .limit(1)
        .execute()
    ).data or []
    key = api_key_row[0] if api_key_row else None
    decision = _decision(str(item.get("status") or ""), item.get("error_code"))
    return {
        "id": item.get("id"),
        "request_id": item.get("request_id"),
        "trace_id": item.get("trace_id"),
        "timestamp": item.get("created_at"),
        "action": {
            "tool_name": item.get("tool_name"),
            "connector": item.get("connector"),
        },
        "actor": {
            "user_id": user_id,
            "api_key": {
                "id": key.get("id") if key else item.get("api_key_id"),
                "name": key.get("name") if key else None,
                "key_prefix": key.get("key_prefix") if key else None,
            },
        },
        "outcome": {
            "decision": decision,
            "status": item.get("status"),
            "error_code": item.get("error_code"),
            "upstream_status": item.get("upstream_status"),
            "latency_ms": item.get("latency_ms"),
            "retry_count": item.get("retry_count"),
            "backoff_ms": item.get("backoff_ms"),
        },
        "execution": {
            "request_payload": item.get("request_payload"),
            "resolved_payload": item.get("resolved_payload"),
            "risk_result": item.get("risk_result"),
            "masked_fields": item.get("masked_fields") or [],
        },
    }
