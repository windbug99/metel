from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class QuotaDecision:
    exceeded: bool
    scope: str | None = None
    limit: int | None = None
    used: int | None = None


def _count_since(*, supabase, field: str, value: Any, since_iso: str) -> int:
    query = (
        supabase.table("tool_calls")
        .select("id", count="exact")
        .eq(field, value)
        .gte("created_at", since_iso)
        .limit(1)
        .execute()
    )
    count = getattr(query, "count", None)
    if isinstance(count, int):
        return count
    rows = query.data or []
    return len(rows)


def evaluate_daily_quota(
    *,
    supabase,
    user_id: str,
    api_key_id: str | int,
    per_key_daily_limit: int,
    per_user_daily_limit: int,
) -> QuotaDecision:
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if per_key_daily_limit > 0:
        key_used = _count_since(supabase=supabase, field="api_key_id", value=api_key_id, since_iso=since)
        if key_used >= per_key_daily_limit:
            return QuotaDecision(exceeded=True, scope="api_key", limit=per_key_daily_limit, used=key_used)

    if per_user_daily_limit > 0:
        user_used = _count_since(supabase=supabase, field="user_id", value=user_id, since_iso=since)
        if user_used >= per_user_daily_limit:
            return QuotaDecision(exceeded=True, scope="user", limit=per_user_daily_limit, used=user_used)

    return QuotaDecision(exceeded=False)
