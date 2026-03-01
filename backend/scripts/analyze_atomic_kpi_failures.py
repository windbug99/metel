from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter
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


def _is_atomic_plan_source(plan_source: str | None) -> bool:
    value = str(plan_source or "").strip()
    return value == "atomic_overhaul_v1" or value.startswith("atomic_overhaul_v1_")


def _normalize_since_utc(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("since_utc is empty")
    normalized = value.replace(" ", "T")
    if normalized.endswith("Z"):
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    else:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _classify_failure_bucket(status: str | None, error_code: str | None, detail: str | None) -> str:
    s = str(status or "").strip().lower()
    e = str(error_code or "").strip().lower()
    d = str(detail or "").strip().lower()

    if s == "success":
        return "success"
    if e in {"auth_error", "token_missing"}:
        return "oauth_auth"
    if e in {"validation_error", "clarification_needed", "risk_gate_blocked"}:
        return "needs_input_or_policy"
    if e == "tool_failed":
        if any(token in d for token in ("auth", "oauth", "permission", "forbidden", "unauthorized")):
            return "oauth_auth"
        return "tool_execution"
    return "other_error"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze atomic KPI failure composition from command_logs.")
    parser.add_argument("--limit", type=int, default=500, help="Number of recent rows to inspect")
    parser.add_argument("--days", type=int, default=0, help="If > 0, inspect recent N days (UTC)")
    parser.add_argument("--since-utc", type=str, default="", help="Inspect rows since this UTC datetime (ISO8601)")
    parser.add_argument("--output-json", type=str, default="", help="Optional output JSON path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    query = (
        supabase.table("command_logs")
        .select("status, plan_source, error_code, detail, created_at")
        .eq("command", "agent_plan")
        .order("created_at", desc=True)
    )
    window_start_utc: str | None = None
    if str(args.since_utc or "").strip():
        window_start_utc = _normalize_since_utc(args.since_utc)
        query = query.gte("created_at", window_start_utc)
    elif int(args.days) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(args.days))
        window_start_utc = cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        query = query.gte("created_at", window_start_utc)

    rows = query.limit(max(1, int(args.limit))).execute().data or []
    atomic_rows = [row for row in rows if _is_atomic_plan_source(row.get("plan_source"))]

    bucket_counter: Counter[str] = Counter()
    error_code_counter: Counter[str] = Counter()
    service_counter: Counter[str] = Counter()
    plan_source_counter: Counter[str] = Counter()

    for row in atomic_rows:
        status = str(row.get("status") or "").strip()
        error_code = str(row.get("error_code") or "").strip() or "(none)"
        plan_source = str(row.get("plan_source") or "").strip() or "(none)"
        detail_map = _parse_detail_pairs(row.get("detail"))
        services = str(detail_map.get("services") or "").strip() or "(none)"

        bucket = _classify_failure_bucket(status, error_code, row.get("detail"))
        bucket_counter[bucket] += 1
        error_code_counter[error_code] += 1
        plan_source_counter[plan_source] += 1
        for service in [s.strip() for s in services.split(",") if s.strip()]:
            service_counter[service] += 1

    payload = {
        "window_start_utc": window_start_utc,
        "inspected_rows": len(rows),
        "atomic_rows": len(atomic_rows),
        "bucket_counts": dict(bucket_counter),
        "error_code_counts": dict(error_code_counter),
        "service_counts": dict(service_counter),
        "plan_source_counts": dict(plan_source_counter),
    }

    print("[Atomic KPI Failure Analysis]")
    if window_start_utc:
        print(f"- window_start_utc: {window_start_utc}")
    print(f"- inspected_rows: {len(rows)}")
    print(f"- atomic_rows: {len(atomic_rows)}")
    print(f"- bucket_counts: {dict(bucket_counter)}")
    print(f"- error_code_counts: {dict(error_code_counter)}")
    print(f"- service_counts: {dict(service_counter)}")
    print(f"- plan_source_counts: {dict(plan_source_counter)}")

    if args.output_json:
        out_path = pathlib.Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
