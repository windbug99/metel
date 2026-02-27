from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _parse_detail_pairs(detail: str | None) -> dict[str, str]:
    raw = str(detail or "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for token in raw.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _cutoff_iso(days: int) -> str:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, int(days)))
    return since.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _top(items: dict[str, int], limit: int) -> list[tuple[str, int]]:
    return sorted(items.items(), key=lambda x: x[1], reverse=True)[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize skill_llm_transform compile miss reasons from command_logs.")
    parser.add_argument("--days", type=int, default=1, help="Lookback days (UTC).")
    parser.add_argument("--limit", type=int, default=500, help="Max rows to scan.")
    parser.add_argument("--top", type=int, default=10, help="Top-N miss reasons.")
    parser.add_argument("--since", type=str, default="", help="Optional UTC ISO cutoff (overrides --days).")
    parser.add_argument(
        "--output-json",
        type=str,
        default="../docs/reports/skill_llm_transform_compile_miss_latest.json",
        help="Optional JSON output path.",
    )
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    since_iso = str(args.since or "").strip() or _cutoff_iso(int(args.days))

    query = (
        supabase.table("command_logs")
        .select("created_at,detail")
        .eq("command", "agent_plan")
        .gte("created_at", since_iso)
        .order("created_at", desc=True)
        .limit(max(1, int(args.limit)))
    )
    try:
        rows = (query.execute().data or [])
    except Exception as exc:
        payload = {
            "since_utc": since_iso,
            "scanned_rows": 0,
            "rollout_miss_rows": 0,
            "top_miss_reasons": [],
            "top_services": [],
            "verdict": "FAIL",
            "reasons": [f"data_source_error:{type(exc).__name__}"],
        }
        print("[Skill+LLM Transform Compile Miss Evaluation]")
        print(f"- since_utc: {since_iso}")
        print("- verdict: FAIL")
        print("- reasons:")
        print(f"  - data_source_error:{type(exc).__name__}")
        out = str(args.output_json or "").strip()
        if out:
            out_path = pathlib.Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"- report: {out_path}")
        return 1

    scanned = len(rows)
    rollout_miss = 0
    miss_reason_hist: dict[str, int] = {}
    service_hist: dict[str, int] = {}

    for row in rows:
        detail = _parse_detail_pairs(row.get("detail"))
        rollout = str(detail.get("skill_llm_transform_rollout") or "").strip()
        if not rollout.endswith("_miss"):
            continue
        rollout_miss += 1
        reason = str(detail.get("skill_llm_transform_compile_miss_reason") or "").strip() or "unknown"
        miss_reason_hist[reason] = miss_reason_hist.get(reason, 0) + 1
        services = str(detail.get("services") or "").strip() or "unknown"
        service_hist[services] = service_hist.get(services, 0) + 1

    top_reasons = _top(miss_reason_hist, max(1, int(args.top)))
    top_services = _top(service_hist, max(1, int(args.top)))

    print("[Skill+LLM Transform Compile Miss Evaluation]")
    print(f"- since_utc: {since_iso}")
    print(f"- scanned_rows: {scanned}")
    print(f"- rollout_miss_rows: {rollout_miss}")
    if top_reasons:
        print("- top_miss_reasons:")
        for reason, count in top_reasons:
            print(f"  - {reason}: {count}")
    if top_services:
        print("- top_services:")
        for services, count in top_services:
            print(f"  - {services}: {count}")

    payload = {
        "since_utc": since_iso,
        "scanned_rows": scanned,
        "rollout_miss_rows": rollout_miss,
        "top_miss_reasons": [{"reason": k, "count": v} for k, v in top_reasons],
        "top_services": [{"services": k, "count": v} for k, v in top_services],
        "verdict": "PASS",
        "reasons": [],
    }

    out = str(args.output_json or "").strip()
    if out:
        out_path = pathlib.Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"- report: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
