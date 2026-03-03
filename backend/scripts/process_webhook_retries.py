from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from supabase import create_client

# Ensure `app` package is importable when executed as a script.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.dead_letter_alert import send_dead_letter_alert
from app.core.event_hooks import process_pending_webhook_retries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process pending webhook retries for all users.")
    parser.add_argument("--limit", type=int, default=500, help="Max deliveries to scan in one run (1-500).")
    parser.add_argument(
        "--user-id",
        type=str,
        default="",
        help="Optional user_id scope. If omitted, process all users.",
    )
    return parser


async def _run(limit: int, user_id: str) -> int:
    supabase_url = str(os.getenv("SUPABASE_URL", "")).strip()
    supabase_service_role_key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    webhook_retry_max_retries = max(0, int(os.getenv("WEBHOOK_RETRY_MAX_RETRIES", "5")))
    webhook_retry_base_backoff_seconds = max(1, int(os.getenv("WEBHOOK_RETRY_BASE_BACKOFF_SECONDS", "30")))
    webhook_retry_max_backoff_seconds = max(1, int(os.getenv("WEBHOOK_RETRY_MAX_BACKOFF_SECONDS", "900")))
    dead_letter_alert_webhook_url = str(os.getenv("DEAD_LETTER_ALERT_WEBHOOK_URL", "")).strip()
    dead_letter_alert_min_count = max(1, int(os.getenv("DEAD_LETTER_ALERT_MIN_COUNT", "1")))
    alert_ticket_webhook_url = str(os.getenv("ALERT_TICKET_WEBHOOK_URL", "")).strip()

    supabase = create_client(supabase_url, supabase_service_role_key)
    result = await process_pending_webhook_retries(
        supabase=supabase,
        user_id=user_id or None,
        limit=max(1, min(int(limit), 500)),
        max_retries=webhook_retry_max_retries,
        base_backoff_seconds=webhook_retry_base_backoff_seconds,
        max_backoff_seconds=webhook_retry_max_backoff_seconds,
    )
    dead_lettered = max(0, int(result.get("dead_lettered") or 0))
    if dead_letter_alert_webhook_url and dead_lettered >= dead_letter_alert_min_count:
        await send_dead_letter_alert(
            webhook_url=dead_letter_alert_webhook_url,
            user_id=user_id or "all",
            source="scheduler_process_retries",
            dead_lettered=dead_lettered,
            details={"result": result, "limit": limit},
            ticket_webhook_url=alert_ticket_webhook_url or None,
        )
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(limit=args.limit, user_id=str(args.user_id or "").strip()))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
