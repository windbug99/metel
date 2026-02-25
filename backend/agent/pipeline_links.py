from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings

try:
    from supabase import create_client
except Exception:  # pragma: no cover
    create_client = None  # type: ignore[assignment]


logger = logging.getLogger("metel-backend.pipeline_links")


def _pipeline_links_table_name() -> str:
    try:
        value = (get_settings().pipeline_links_table or "pipeline_links").strip()
    except Exception:
        value = "pipeline_links"
    return value or "pipeline_links"


def _extract_notion_page_id(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    candidates = [
        payload.get("id"),
        payload.get("page_id"),
        ((payload.get("result") or {}).get("id") if isinstance(payload.get("result"), dict) else None),
        data.get("id"),
        data.get("page_id"),
        ((data.get("result") or {}).get("id") if isinstance(data.get("result"), dict) else None),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _extract_linear_issue_id(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    issue_create = payload.get("issueCreate") if isinstance(payload.get("issueCreate"), dict) else {}
    issue = issue_create.get("issue") if isinstance(issue_create.get("issue"), dict) else {}
    data_issue_create = data.get("issueCreate") if isinstance(data.get("issueCreate"), dict) else {}
    data_issue = data_issue_create.get("issue") if isinstance(data_issue_create.get("issue"), dict) else {}
    candidates = [
        issue.get("id"),
        ((payload.get("issue") or {}).get("id") if isinstance(payload.get("issue"), dict) else None),
        payload.get("id"),
        data_issue.get("id"),
        ((data.get("issue") or {}).get("id") if isinstance(data.get("issue"), dict) else None),
        data.get("id"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def extract_pipeline_links(
    *,
    user_id: str,
    pipeline_run_id: str,
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    if not isinstance(artifacts, dict):
        return links
    for value in artifacts.values():
        if not isinstance(value, dict):
            continue
        item_results = value.get("item_results")
        if not isinstance(item_results, list):
            continue
        for item_result in item_results:
            if not isinstance(item_result, dict):
                continue
            transform = item_result.get("n2_1") if isinstance(item_result.get("n2_1"), dict) else {}
            notion = item_result.get("n2_2") if isinstance(item_result.get("n2_2"), dict) else {}
            linear = item_result.get("n2_3") if isinstance(item_result.get("n2_3"), dict) else {}
            event_id = str(transform.get("event_id") or transform.get("calendar_event_id") or "").strip()
            notion_page_id = _extract_notion_page_id(notion)
            linear_issue_id = _extract_linear_issue_id(linear)
            if not event_id:
                continue
            links.append(
                {
                    "user_id": user_id,
                    "event_id": event_id,
                    "notion_page_id": notion_page_id or None,
                    "linear_issue_id": linear_issue_id or None,
                    "run_id": pipeline_run_id,
                    "status": "succeeded",
                    "error_code": None,
                    "compensation_status": "not_required",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return links


def persist_pipeline_links(*, links: list[dict[str, Any]]) -> bool:
    if not links:
        return True
    if create_client is None:
        return False
    settings = get_settings()
    table = _pipeline_links_table_name()
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        client.table(table).upsert(links, on_conflict="user_id,event_id").execute()
        return True
    except Exception as exc:
        logger.warning("failed to persist pipeline_links: %s", exc)
        return False


def persist_pipeline_failure_link(
    *,
    user_id: str,
    event_id: str,
    run_id: str,
    status: str,
    error_code: str | None = None,
    compensation_status: str | None = None,
) -> bool:
    event = str(event_id or "").strip()
    if not event:
        return True
    if create_client is None:
        return False
    settings = get_settings()
    table = _pipeline_links_table_name()
    payload = {
        "user_id": user_id,
        "event_id": event,
        "notion_page_id": None,
        "linear_issue_id": None,
        "run_id": str(run_id or "").strip() or "unknown",
        "status": str(status or "").strip() or "failed",
        "error_code": str(error_code or "").strip() or None,
        "compensation_status": str(compensation_status or "").strip() or "not_required",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        client.table(table).upsert(payload, on_conflict="user_id,event_id").execute()
        return True
    except Exception as exc:
        logger.warning("failed to persist pipeline_links failure row: %s", exc)
        return False
