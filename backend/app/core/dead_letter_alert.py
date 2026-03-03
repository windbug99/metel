from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


def _build_standard_payload(*, user_id: str, source: str, dead_lettered: int, details: dict[str, Any] | None) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    dedupe_key = f"dead_letter:{user_id}:{source}:{(details or {}).get('delivery_id', 'bulk')}"
    return {
        "schema_version": "1.0",
        "event": "dead_letter_alert",
        "severity": "critical",
        "timestamp": timestamp,
        "user_id": user_id,
        "source": source,
        "dead_lettered": max(0, int(dead_lettered)),
        "dedupe_key": dedupe_key,
        "details": details or {},
    }


def _format_text(*, user_id: str, source: str, dead_lettered: int, details: dict[str, Any] | None) -> str:
    return (
        ":rotating_light: dead-letter alert\n"
        f"- user_id: {user_id}\n"
        f"- source: {source}\n"
        f"- dead_lettered: {max(0, int(dead_lettered))}\n"
        f"- details: {details or {}}"
    )


async def send_dead_letter_alert(
    *,
    webhook_url: str,
    user_id: str,
    source: str,
    dead_lettered: int,
    details: dict[str, Any] | None = None,
    ticket_webhook_url: str | None = None,
) -> bool:
    url = str(webhook_url or "").strip()
    if not url:
        return False

    standard_payload = _build_standard_payload(
        user_id=user_id,
        source=source,
        dead_lettered=dead_lettered,
        details=details,
    )
    payload: dict[str, Any] = dict(standard_payload)
    if "hooks.slack.com/services/" in url:
        # Slack Incoming Webhook expects message payload with `text`.
        payload = {
            "text": _format_text(
                user_id=user_id,
                source=source,
                dead_lettered=dead_lettered,
                details=details,
            )
        }
    sent = False
    ticket_url = str(ticket_webhook_url or "").strip()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            sent = 200 <= int(response.status_code) < 300
            if ticket_url:
                await client.post(ticket_url, json=standard_payload)
        return sent
    except Exception:
        return False
