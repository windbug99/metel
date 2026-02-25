from __future__ import annotations

import argparse
import pathlib
import random
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx
from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


@dataclass(frozen=True)
class PromptItem:
    text: str
    service: str  # google | notion | linear | generic
    mutation: bool


PROMPTS: list[PromptItem] = [
    PromptItem("Linear 최근 이슈 5개를 조회해줘.", "linear", False),
    PromptItem("Linear에서 진행중인 이슈 3개를 보여줘.", "linear", False),
    PromptItem("Linear에서 내게 할당된 이슈를 찾아줘.", "linear", False),
    PromptItem("Linear OPT-46 이슈를 요약해줘.", "linear", False),
    PromptItem("Linear에서 timeout 키워드 이슈를 검색해줘.", "linear", False),
    PromptItem('Notion에서 "스프린트 보고서" 페이지를 찾아줘.', "notion", False),
    PromptItem("Notion 최근 페이지 5개를 보여줘.", "notion", False),
    PromptItem("Notion에서 incident 키워드 검색 결과를 보여줘.", "notion", False),
    PromptItem("Notion 운영 체크리스트 페이지를 찾아줘.", "notion", False),
    PromptItem("Notion 페이지 하나를 찾아 제목과 링크를 알려줘.", "notion", False),
    PromptItem("Google Calendar 오늘 일정 3개를 조회해줘.", "google", False),
    PromptItem("Google Calendar 오늘 첫 일정 제목을 알려줘.", "google", False),
    PromptItem("Google Calendar 오늘 회의 개수를 알려줘.", "google", False),
    PromptItem("Google Calendar 내일 일정 3개를 보여줘.", "google", False),
    PromptItem("Google Calendar 이번주 일정 개요를 알려줘.", "google", False),
    PromptItem("오늘 할 일을 3줄로 정리해줘.", "generic", False),
    PromptItem("업무 우선순위를 간단히 정리해줘.", "generic", False),
    PromptItem("회의 준비 체크리스트를 간단히 만들어줘.", "generic", False),
    PromptItem("이번주 업무 계획을 3가지로 정리해줘.", "generic", False),
    PromptItem("오늘 일정 요약을 한 문단으로 작성해줘.", "generic", False),
    PromptItem("Linear 이슈를 하나 생성해줘. 제목은 autonomous sample.", "linear", True),
    PromptItem("Notion 새 페이지를 만들어줘. 제목은 autonomous sample.", "notion", True),
]


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


def _load_user_id_by_chat_id(chat_id: int) -> str | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("users")
        .select("id")
        .eq("telegram_chat_id", chat_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    value = str(rows[0].get("id") or "").strip()
    return value or None


def _load_connected_services(user_id: str) -> set[str]:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("oauth_tokens")
        .select("provider")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    out: set[str] = set()
    for row in rows:
        provider = str(row.get("provider") or "").strip().lower()
        if provider:
            out.add(provider)
    return out


def _send_webhook_update(*, webhook_url: str, webhook_secret: str | None, chat_id: int, text: str, update_id: int) -> None:
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "autonomous-seed"},
            "text": text,
        },
    }
    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = webhook_secret
    with httpx.Client(timeout=20) as client:
        response = client.post(webhook_url, json=payload, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"webhook_post_failed:{response.status_code}:{response.text[:200]}")


def _build_prompt_pool(*, connected_services: set[str], read_only_only: bool) -> list[str]:
    pool: list[str] = []
    for item in PROMPTS:
        if read_only_only and item.mutation:
            continue
        if item.service == "generic":
            pool.append(item.text)
            continue
        if item.service in connected_services:
            pool.append(item.text)
    return pool


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed autonomous traffic with connected-service prompts.")
    parser.add_argument("--webhook-url", type=str, required=True, help="Target telegram webhook URL")
    parser.add_argument("--chat-id", type=int, default=0, help="Telegram chat_id. Auto-detect if omitted.")
    parser.add_argument("--target-count", type=int, default=30, help="How many prompts to send.")
    parser.add_argument("--sleep-sec", type=float, default=8.0, help="Interval between sends.")
    parser.add_argument("--include-mutation", action="store_true", help="Include mutation prompts.")
    parser.add_argument("--seed", type=int, default=20260225, help="Random seed for stable shuffling.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected prompts without sending.")
    args = parser.parse_args()

    settings = get_settings()
    webhook_secret = str(settings.telegram_webhook_secret or "").strip() or None
    chat_id = int(args.chat_id) if int(args.chat_id or 0) > 0 else int(_find_recent_chat_id() or 0)
    if chat_id <= 0:
        print("[seed-autonomous-traffic]")
        print("- verdict: FAIL")
        print("- reason: missing_chat_id")
        return 1

    user_id = _load_user_id_by_chat_id(chat_id)
    if not user_id:
        print("[seed-autonomous-traffic]")
        print("- verdict: FAIL")
        print("- reason: user_not_found_for_chat")
        print(f"- chat_id: {chat_id}")
        return 1

    connected_services = _load_connected_services(user_id)
    pool = _build_prompt_pool(connected_services=connected_services, read_only_only=not bool(args.include_mutation))
    if not pool:
        print("[seed-autonomous-traffic]")
        print("- verdict: FAIL")
        print("- reason: no_prompt_pool")
        print(f"- connected_services: {sorted(connected_services)}")
        return 1

    rng = random.Random(int(args.seed))
    selected: list[str] = []
    while len(selected) < max(1, int(args.target_count)):
        round_pool = list(pool)
        rng.shuffle(round_pool)
        selected.extend(round_pool)
    selected = selected[: max(1, int(args.target_count))]

    print("[seed-autonomous-traffic]")
    print(f"- chat_id: {chat_id}")
    print(f"- user_id: {user_id}")
    print(f"- connected_services: {sorted(connected_services)}")
    print(f"- prompt_pool_size: {len(pool)}")
    print(f"- target_count: {len(selected)}")
    print(f"- include_mutation: {bool(args.include_mutation)}")
    print(f"- webhook_url: {str(args.webhook_url).strip()}")

    if args.dry_run:
        print("- dry_run: true")
        for idx, text in enumerate(selected, start=1):
            print(f"  {idx:02d}. {text}")
        print("- verdict: PASS")
        return 0

    update_seed = int(time.time() * 1000) % 2_000_000_000
    sent = 0
    for idx, text in enumerate(selected, start=1):
        try:
            _send_webhook_update(
                webhook_url=str(args.webhook_url).strip(),
                webhook_secret=webhook_secret,
                chat_id=chat_id,
                text=text,
                update_id=update_seed + idx,
            )
            sent += 1
            print(f"- sent[{idx:02d}/{len(selected)}]: {text}")
        except Exception as exc:
            print(f"- send_failed[{idx:02d}]: {type(exc).__name__}:{exc}")
        if idx < len(selected):
            time.sleep(max(0.0, float(args.sleep_sec)))

    print(f"- sent_count: {sent}")
    print(f"- failed_count: {len(selected) - sent}")
    print(f"- verdict: {'PASS' if sent == len(selected) else 'FAIL'}")
    return 0 if sent == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
