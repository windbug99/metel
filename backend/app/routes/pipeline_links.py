from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/pipeline-links", tags=["pipeline-links"])


@router.get("/recent")
async def list_recent_pipeline_links(
    request: Request,
    limit: int = 20,
    cursor_updated_at: str | None = None,
):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    table = (settings.pipeline_links_table or "pipeline_links").strip() or "pipeline_links"
    safe_limit = max(1, min(100, int(limit)))
    cursor_value = str(cursor_updated_at or "").strip()
    if cursor_value:
        try:
            datetime.fromisoformat(cursor_value.replace("Z", "+00:00"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid_cursor_updated_at") from exc
    try:
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        query = (
            supabase.table(table)
            .select(
                "event_id,notion_page_id,linear_issue_id,run_id,status,error_code,compensation_status,updated_at"
            )
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
        )
        if cursor_value:
            query = query.lt("updated_at", cursor_value)
        rows = query.limit(safe_limit).execute().data or []
        next_cursor_updated_at = ""
        if len(rows) == safe_limit:
            next_cursor_updated_at = str((rows[-1] or {}).get("updated_at") or "").strip()
        return {
            "items": rows,
            "count": len(rows),
            "next_cursor_updated_at": next_cursor_updated_at or None,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pipeline_links_query_failed:{type(exc).__name__}") from exc
