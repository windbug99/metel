from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


async def send_dead_letter_alert(
    *,
    webhook_url: str,
    user_id: str,
    source: str,
    dead_lettered: int,
    details: dict[str, Any] | None = None,
) -> bool:
    url = str(webhook_url or "").strip()
    if not url:
        return False

    payload = {
        "event": "dead_letter_alert",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "source": source,
        "dead_lettered": max(0, int(dead_lettered)),
        "details": details or {},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
        return 200 <= int(response.status_code) < 300
    except Exception:
        return False
