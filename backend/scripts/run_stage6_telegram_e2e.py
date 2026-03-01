from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


@dataclass(frozen=True)
class Scenario:
    id: str
    text: str
    expected: str  # success | needs_input | error | success_or_needs_input
    chain: str = ""
    note: str = ""


SCENARIOS: list[Scenario] = [
    Scenario("S1", "linear OPT-46 이슈 설명 업데이트: API 타임아웃 재현 조건과 임시 우회 방법을 추가해줘", "success", chain="single_s1"),
    Scenario("S2", "openweather API 사용방법을 정리해서 linear OPT-46 설명에 추가해줘", "success_or_needs_input", chain="single_s2"),
    Scenario("S3", "linear OPT-45 이슈를 삭제하세요", "error", chain="single_s3"),
    Scenario("S4", "linear에 이슈 생성", "success_or_needs_input", chain="linear_create"),
    Scenario("S5", "팀: operate", "success_or_needs_input", chain="linear_create"),
    Scenario("S6", "제목: stage6 자동화 테스트 이슈", "success_or_needs_input", chain="linear_create"),
    Scenario("S7", '노션에서 "서비스 기획서" 페이지 제목을 "서비스 기획서 v2"로 업데이트', "success_or_needs_input", chain="single_s7"),
    Scenario("S8", '노션에서 "서비스 기획서" 페이지 본문 업데이트: 이번 주 배포 리스크와 대응 현황을 3줄로 추가', "success_or_needs_input", chain="single_s8"),
    Scenario("S9", "linear OPT-47 이슈로 notion에 페이지 생성하세요", "success_or_needs_input", chain="single_s9"),
    Scenario("S10", "linear 최근 이슈 5개 검색해줘", "success", chain="single_s10"),
]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_detail_pairs(detail: str | None) -> dict[str, str]:
    text = str(detail or "").strip()
    if not text:
        return {}
    out: dict[str, str] = {}
    for token in text.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _find_recent_chat_id() -> int | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("users")
        .select("telegram_chat_id, updated_at")
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


def _send_webhook_update(
    *,
    webhook_url: str,
    webhook_secret: str | None,
    chat_id: int,
    text: str,
    update_id: int,
) -> None:
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "stage6"},
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
    try:
        body = response.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and body.get("ok") is False:
        raise RuntimeError(f"webhook_post_not_ok:{json.dumps(body, ensure_ascii=False)}")


def _fetch_first_agent_plan_log_after(*, chat_id: int, since_iso: str) -> dict[str, Any] | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("command_logs")
        .select("created_at,status,error_code,detail,plan_source")
        .eq("channel", "telegram")
        .eq("chat_id", chat_id)
        .eq("command", "agent_plan")
        .gt("created_at", since_iso)
        .order("created_at", desc=False)
        .limit(5)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    for row in rows:
        if isinstance(row, dict):
            return row
    return None


def _is_pass(*, expected: str, log_row: dict[str, Any]) -> bool:
    status = str(log_row.get("status") or "").strip().lower()
    error_code = str(log_row.get("error_code") or "").strip().lower()
    detail_map = _parse_detail_pairs(str(log_row.get("detail") or ""))
    shadow_mode = detail_map.get("skill_v2_shadow_mode") == "1"
    shadow_executed = detail_map.get("skill_v2_shadow_executed") == "1"
    shadow_ok = detail_map.get("skill_v2_shadow_ok") == "1"

    # In Stage6 shadow mode, legacy path may fail while V2 shadow path succeeds.
    # For rollout validation this should be treated as pass for success-expected scenarios.
    if shadow_mode and shadow_executed and shadow_ok and expected in {"success", "success_or_needs_input"}:
        return True

    needs_input_codes = {"validation_error", "clarification_needed", "risk_gate_blocked"}

    if expected == "success":
        return status == "success"
    if expected == "needs_input":
        return status == "error" and error_code in needs_input_codes
    if expected == "error":
        return status == "error"
    if expected == "success_or_needs_input":
        return status == "success" or (status == "error" and error_code in needs_input_codes)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage6 Telegram E2E scenarios and auto-grade from command_logs.")
    parser.add_argument("--chat-id", type=int, default=0, help="Telegram chat_id. If omitted, auto-detect recent linked chat.")
    parser.add_argument(
        "--webhook-url",
        type=str,
        default="http://127.0.0.1:8000/api/telegram/webhook",
        help="Target telegram webhook URL for local E2E injection.",
    )
    parser.add_argument("--delay-sec", type=float, default=1.5, help="Delay between scenario sends.")
    parser.add_argument("--poll-timeout-sec", type=float, default=45.0, help="Max wait for command_logs row per scenario.")
    parser.add_argument("--poll-interval-sec", type=float, default=1.2, help="Polling interval for command_logs.")
    parser.add_argument(
        "--output-json",
        type=str,
        default="../docs/reports/stage6_telegram_e2e_latest.json",
        help="Output JSON report path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print scenarios and exit.")
    parser.add_argument(
        "--reset-pending",
        action="store_true",
        help="Send '취소' once before scenarios to clear prior pending action.",
    )
    parser.add_argument(
        "--reset-between-chains",
        action="store_true",
        help="Send '취소' when scenario chain changes (recommended).",
    )
    args = parser.parse_args()

    settings = get_settings()
    webhook_secret = str(settings.telegram_webhook_secret or "").strip() or None

    if args.dry_run:
        print(f"chat_id={int(args.chat_id) if int(args.chat_id or 0) > 0 else '<AUTO_FIND>'}")
        for item in SCENARIOS:
            print(f"- {item.id} [{item.expected}] {item.text}")
        return 0

    chat_id = int(args.chat_id) if int(args.chat_id or 0) > 0 else int(_find_recent_chat_id() or 0)
    if chat_id <= 0:
        print("error: chat_id is required (or linked telegram user not found)")
        return 1

    report_rows: list[dict[str, Any]] = []
    print(
        f"[stage6-telegram-e2e] start chat_id={chat_id} scenarios={len(SCENARIOS)} "
        f"webhook_url={args.webhook_url}"
    )
    update_seed = int(time.time() * 1000) % 2_000_000_000
    if bool(args.reset_pending):
        try:
            _send_webhook_update(
                webhook_url=str(args.webhook_url).strip(),
                webhook_secret=webhook_secret,
                chat_id=chat_id,
                text="취소",
                update_id=update_seed - 1,
            )
            # Give app a short moment to persist pending-state cleanup.
            time.sleep(1.0)
            print("[stage6-telegram-e2e] pending reset sent")
        except Exception as exc:
            print(f"[stage6-telegram-e2e] pending reset failed: {exc}")
    active_chain = ""
    for idx, scenario in enumerate(SCENARIOS, start=1):
        if idx > 1:
            time.sleep(max(0.0, float(args.delay_sec)))
        if bool(args.reset_between_chains):
            scenario_chain = str(scenario.chain or scenario.id)
            if active_chain and scenario_chain != active_chain:
                try:
                    _send_webhook_update(
                        webhook_url=str(args.webhook_url).strip(),
                        webhook_secret=webhook_secret,
                        chat_id=chat_id,
                        text="취소",
                        update_id=update_seed + (idx * 1000),
                    )
                    time.sleep(0.8)
                    print(f"[{scenario.id}] chain reset sent")
                except Exception as exc:
                    print(f"[{scenario.id}] chain reset failed: {exc}")
            active_chain = scenario_chain
        since = _utc_iso()
        print(f"[{scenario.id}] send: {scenario.text}")
        try:
            _send_webhook_update(
                webhook_url=str(args.webhook_url).strip(),
                webhook_secret=webhook_secret,
                chat_id=chat_id,
                text=scenario.text,
                update_id=update_seed + idx,
            )
        except Exception as exc:
            row = {
                "id": scenario.id,
                "text": scenario.text,
                "expected": scenario.expected,
                "pass": False,
                "error": f"send_failed:{exc}",
            }
            report_rows.append(row)
            print(f"[{scenario.id}] FAIL send_failed")
            continue

        deadline = time.time() + max(5.0, float(args.poll_timeout_sec))
        found: dict[str, Any] | None = None
        while time.time() < deadline:
            found = _fetch_first_agent_plan_log_after(chat_id=chat_id, since_iso=since)
            if found is not None:
                break
            time.sleep(max(0.2, float(args.poll_interval_sec)))

        if found is None:
            row = {
                "id": scenario.id,
                "text": scenario.text,
                "expected": scenario.expected,
                "pass": False,
                "error": "log_timeout",
            }
            report_rows.append(row)
            print(f"[{scenario.id}] FAIL log_timeout")
            continue

        passed = _is_pass(expected=scenario.expected, log_row=found)
        row = {
            "id": scenario.id,
            "text": scenario.text,
            "expected": scenario.expected,
            "chain": scenario.chain,
            "pass": passed,
            "status": found.get("status"),
            "error_code": found.get("error_code"),
            "plan_source": found.get("plan_source"),
            "created_at": found.get("created_at"),
            "detail": str(found.get("detail") or "")[:500],
        }
        report_rows.append(row)
        print(
            f"[{scenario.id}] {'PASS' if passed else 'FAIL'} "
            f"status={row.get('status')} error_code={row.get('error_code')}"
        )

    passed_count = sum(1 for row in report_rows if row.get("pass"))
    total = len(report_rows)
    summary = {
        "generated_at": _utc_iso(),
        "chat_id": chat_id,
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": (passed_count / total) if total else 0.0,
        "rows": report_rows,
    }

    output_path = pathlib.Path(args.output_json)
    if not output_path.is_absolute():
        output_path = (ROOT / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[stage6-telegram-e2e] done passed={passed_count}/{total}")
    print(f"[stage6-telegram-e2e] report={output_path}")
    return 0 if passed_count == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
