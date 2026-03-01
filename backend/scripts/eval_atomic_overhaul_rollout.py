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


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(1.0, p)) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(len(ordered) - 1, lo + 1)
    if lo == hi:
        return ordered[lo]
    frac = rank - lo
    return int(round(ordered[lo] * (1 - frac) + ordered[hi] * frac))


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _ratio(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return n / d


def _is_atomic_plan_source(plan_source: str | None) -> bool:
    value = str(plan_source or "").strip()
    return value == "atomic_overhaul_v1" or value.startswith("atomic_overhaul_v1_")


def _is_needs_input_outcome(error_code: str | None, detail_map: dict[str, str]) -> bool:
    code = str(error_code or "").strip().lower()
    if code in {"clarification_needed", "risk_gate_blocked"}:
        return True
    if code == "validation_error":
        if str(detail_map.get("missing_slot") or "").strip():
            return True
        if str(detail_map.get("slot_action") or "").strip():
            return True
    return False


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Atomic Overhaul rollout metrics from command_logs.")
    parser.add_argument("--limit", type=int, default=200, help="Number of recent agent_plan logs to inspect")
    parser.add_argument("--days", type=int, default=0, help="If > 0, inspect recent N days (UTC)")
    parser.add_argument("--since-utc", type=str, default="", help="Inspect rows since this UTC datetime (ISO8601)")
    parser.add_argument("--min-sample", type=int, default=30, help="Minimum sample size")
    parser.add_argument("--target-success-rate", type=float, default=0.85, help="Atomic success rate target")
    parser.add_argument("--max-validation-error-rate", type=float, default=0.10, help="Validation error rate ceiling")
    parser.add_argument("--max-user-visible-error-rate", type=float, default=0.15, help="Overall error rate ceiling")
    parser.add_argument("--max-p95-latency-ms", type=int, default=12000, help="Latency p95 ceiling")
    parser.add_argument(
        "--require-zero-legacy",
        action="store_true",
        help="Fail gate when legacy plan_source rows are present in the same window",
    )
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

    result = query.limit(max(1, int(args.limit))).execute()
    rows = result.data or []

    atomic_rows = [row for row in rows if _is_atomic_plan_source(row.get("plan_source"))]
    legacy_rows = [row for row in rows if not _is_atomic_plan_source(row.get("plan_source"))]
    sample_size = len(atomic_rows)
    success_count = sum(1 for row in atomic_rows if str(row.get("status") or "").strip() == "success")
    needs_input_count = 0
    hard_error_count = 0
    validation_error_count = 0

    latency_values: list[int] = []
    for row in atomic_rows:
        detail_map = _parse_detail_pairs(row.get("detail"))
        code = str(row.get("error_code") or "").strip()
        status = str(row.get("status") or "").strip()
        needs_input = _is_needs_input_outcome(code, detail_map)
        if needs_input:
            needs_input_count += 1
        elif status == "error":
            hard_error_count += 1
            if code == "validation_error":
                validation_error_count += 1
        latency = _as_int(detail_map.get("analysis_latency_ms"))
        if latency is not None and latency >= 0:
            latency_values.append(latency)

    accepted_outcome_count = success_count + needs_input_count
    accepted_outcome_rate = _ratio(accepted_outcome_count, sample_size)
    success_rate = _ratio(success_count, sample_size)
    validation_error_rate = _ratio(validation_error_count, sample_size)
    user_visible_error_rate = _ratio(hard_error_count, sample_size)
    p50_latency = _percentile(latency_values, 0.50)
    p95_latency = _percentile(latency_values, 0.95)

    reasons: list[str] = []
    if sample_size < int(args.min_sample):
        reasons.append(f"insufficient_sample:{sample_size}<{int(args.min_sample)}")
    if sample_size > 0 and accepted_outcome_rate < float(args.target_success_rate):
        reasons.append(f"accepted_outcome_rate_below_target:{accepted_outcome_rate:.3f}<{float(args.target_success_rate):.3f}")
    if sample_size > 0 and validation_error_rate > float(args.max_validation_error_rate):
        reasons.append(
            f"validation_error_rate_above_target:{validation_error_rate:.3f}>{float(args.max_validation_error_rate):.3f}"
        )
    if sample_size > 0 and user_visible_error_rate > float(args.max_user_visible_error_rate):
        reasons.append(
            f"user_visible_error_rate_above_target:{user_visible_error_rate:.3f}>{float(args.max_user_visible_error_rate):.3f}"
        )
    if sample_size > 0 and p95_latency > int(args.max_p95_latency_ms):
        reasons.append(f"p95_latency_above_target:{p95_latency}>{int(args.max_p95_latency_ms)}")
    if args.require_zero_legacy and legacy_rows:
        reasons.append(f"legacy_rows_detected:{len(legacy_rows)}")

    verdict = "PASS" if not reasons else "FAIL"

    print("[Atomic Overhaul Rollout Evaluation]")
    if window_start_utc:
        if str(args.since_utc or "").strip():
            print(f"- window: since {window_start_utc}")
        else:
            print(f"- window: recent {int(args.days)} day(s) since {window_start_utc}")
    else:
        print("- window: latest rows only (no day filter)")
    print(f"- atomic sample size: {sample_size} (min required: {int(args.min_sample)})")
    print(f"- legacy row count: {len(legacy_rows)}")
    print(f"- accepted outcome rate: {accepted_outcome_rate * 100:.1f}% ({accepted_outcome_count}/{sample_size})")
    print(f"- success rate: {success_rate * 100:.1f}% ({success_count}/{sample_size})")
    print(f"- needs_input count: {needs_input_count}")
    print(f"- validation error rate: {validation_error_rate * 100:.1f}% ({validation_error_count}/{sample_size})")
    print(f"- user-visible error rate: {user_visible_error_rate * 100:.1f}% ({hard_error_count}/{sample_size})")
    print(f"- latency p50/p95: {p50_latency}ms / {p95_latency}ms")
    print(f"- verdict: {verdict}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    payload = {
        "window_days": int(args.days),
        "window_start_utc": window_start_utc,
        "sample_size": sample_size,
        "legacy_row_count": len(legacy_rows),
        "min_sample": int(args.min_sample),
        "accepted_outcome_count": accepted_outcome_count,
        "accepted_outcome_rate": accepted_outcome_rate,
        "success_count": success_count,
        "success_rate": success_rate,
        "needs_input_count": needs_input_count,
        "validation_error_count": validation_error_count,
        "validation_error_rate": validation_error_rate,
        "user_visible_error_count": hard_error_count,
        "user_visible_error_rate": user_visible_error_rate,
        "latency_p50_ms": p50_latency,
        "latency_p95_ms": p95_latency,
        "verdict": verdict,
        "reasons": reasons,
    }
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
