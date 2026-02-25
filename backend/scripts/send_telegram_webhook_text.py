from __future__ import annotations

import argparse
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _find_recent_chat_id() -> int | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("users")
        .select("telegram_chat_id,updated_at")
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    for row in rows:
        chat_id = row.get("telegram_chat_id")
        if isinstance(chat_id, int):
            return chat_id
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one synthetic Telegram webhook message to metel backend.")
    parser.add_argument(
        "--webhook-url",
        type=str,
        default="http://127.0.0.1:8000/api/telegram/webhook",
        help="Target backend webhook URL.",
    )
    parser.add_argument("--chat-id", type=int, default=0, help="Telegram chat_id. Auto-detect if omitted.")
    parser.add_argument("--text", type=str, required=True, help="Message text.")
    parser.add_argument(
        "--update-id",
        type=int,
        default=0,
        help="Telegram update_id override. Auto-generated if omitted.",
    )
    args = parser.parse_args()

    settings = get_settings()
    webhook_secret = str(settings.telegram_webhook_secret or "").strip() or None
    chat_id = int(args.chat_id) if int(args.chat_id or 0) > 0 else int(_find_recent_chat_id() or 0)
    if chat_id <= 0:
        print("[telegram-webhook-send]")
        print("- verdict: FAIL")
        print("- reason: missing_chat_id")
        return 1

    update_id = int(args.update_id) if int(args.update_id or 0) > 0 else int(time.time() * 1000) % 2_000_000_000
    payload: dict[str, Any] = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "smoke"},
            "text": str(args.text),
        },
    }
    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = webhook_secret

    with httpx.Client(timeout=20) as client:
        response = client.post(str(args.webhook_url).strip(), json=payload, headers=headers)

    print("[telegram-webhook-send]")
    print(f"- webhook_url: {str(args.webhook_url).strip()}")
    print(f"- chat_id: {chat_id}")
    print(f"- update_id: {update_id}")
    print(f"- sent_at: {_now_iso()}")
    print(f"- status_code: {response.status_code}")
    if response.status_code >= 400:
        print("- verdict: FAIL")
        print(f"- reason: webhook_post_failed:{response.status_code}")
        return 1

    print("- verdict: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
