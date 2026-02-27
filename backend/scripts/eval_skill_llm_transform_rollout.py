from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


_ROLLOUT_SERVE_PATTERN = re.compile(r"^rollout_\d+$")


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


def _pct(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return n / d


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


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


def _is_compiled_target(detail: dict[str, str]) -> bool:
    return bool(detail.get("skill_llm_transform_rollout"))


def _is_served_by_compiled(detail: dict[str, str]) -> bool:
    rollout = str(detail.get("skill_llm_transform_rollout") or "").strip()
    # Served traffic includes rollout-bucket served traffic and explicit allowlist forced serve.
    if rollout == "allowlist":
        return True
    return bool(_ROLLOUT_SERVE_PATTERN.match(rollout))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Skill+LLM transform rollout/shadow metrics from command_logs.")
    parser.add_argument("--limit", type=int, default=200, help="Number of recent agent_plan logs")
    parser.add_argument("--days", type=int, default=0, help="If > 0, evaluate logs within recent N days (UTC).")
    parser.add_argument("--since", type=str, default="", help="Optional UTC ISO cutoff (overrides --days).")
    parser.add_argument("--min-sample", type=int, default=30, help="Minimum sample size")
    parser.add_argument("--target-success", type=float, default=0.95, help="Target served success rate")
    parser.add_argument("--max-error-rate", type=float, default=0.05, help="Maximum served error rate")
    parser.add_argument("--max-p95-latency-ms", type=int, default=12000, help="Maximum allowed p95 latency(ms)")
    parser.add_argument("--output-json", type=str, default="", help="Optional JSON output path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    query = (
        supabase.table("command_logs")
        .select("status, plan_source, detail, error_code, created_at")
        .eq("command", "agent_plan")
        .order("created_at", desc=True)
    )
    window_start_utc: str | None = str(args.since or "").strip() or None
    if (not window_start_utc) and int(args.days) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(args.days))
        window_start_utc = cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if window_start_utc:
        query = query.gte("created_at", window_start_utc)
    try:
        result = query.limit(max(1, args.limit)).execute()
    except Exception as exc:
        reasons = [f"data_source_error:{type(exc).__name__}"]
        payload = {
            "window_days": int(args.days),
            "window_start_utc": window_start_utc,
            "sample_size": 0,
            "min_sample": int(args.min_sample),
            "target_count": 0,
            "served_count": 0,
            "served_success_count": 0,
            "served_success_rate": 0.0,
            "served_error_rate": 0.0,
            "served_latency_p50_ms": 0,
            "served_latency_p95_ms": 0,
            "shadow_count": 0,
            "shadow_ok_count": 0,
            "shadow_ok_rate": 0.0,
            "shadow_latency_p50_ms": 0,
            "shadow_latency_p95_ms": 0,
            "rollout_reasons": {},
            "verdict": "FAIL",
            "reasons": reasons,
        }
        print("[Skill+LLM Transform Rollout Evaluation]")
        print("- verdict: FAIL")
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
        return 1

    rows = result.data or []
    total = len(rows)

    target_rows: list[tuple[dict, dict[str, str]]] = []
    for row in rows:
        detail = _parse_detail_pairs(row.get("detail"))
        if _is_compiled_target(detail):
            target_rows.append((row, detail))

    served_rows = [(row, detail) for row, detail in target_rows if _is_served_by_compiled(detail)]
    served_count = len(served_rows)
    served_success_count = len([1 for row, _detail in served_rows if str(row.get("status") or "").strip() == "success"])
    served_latency: list[int] = []
    for _row, detail in served_rows:
        latency = _as_int(detail.get("analysis_latency_ms"))
        if latency is not None and latency >= 0:
            served_latency.append(latency)

    shadow_rows = [(row, detail) for row, detail in target_rows if detail.get("skill_llm_transform_shadow_executed") == "1"]
    shadow_count = len(shadow_rows)
    shadow_ok_count = len([1 for _row, detail in shadow_rows if detail.get("skill_llm_transform_shadow_ok") == "1"])
    shadow_latency: list[int] = []
    for _row, detail in shadow_rows:
        latency = _as_int(detail.get("analysis_latency_ms"))
        if latency is not None and latency >= 0:
            shadow_latency.append(latency)

    rollout_reasons: dict[str, int] = {}
    for _row, detail in target_rows:
        reason = str(detail.get("skill_llm_transform_rollout") or "").strip()
        if reason:
            rollout_reasons[reason] = rollout_reasons.get(reason, 0) + 1

    served_success_rate = _pct(served_success_count, served_count)
    served_error_rate = 1.0 - served_success_rate if served_count > 0 else 0.0
    shadow_ok_rate = _pct(shadow_ok_count, shadow_count)
    served_latency_p50 = _percentile(served_latency, 0.50)
    served_latency_p95 = _percentile(served_latency, 0.95)
    shadow_latency_p50 = _percentile(shadow_latency, 0.50)
    shadow_latency_p95 = _percentile(shadow_latency, 0.95)

    reasons: list[str] = []
    if total < int(args.min_sample):
        reasons.append(f"insufficient_sample:{total}<{int(args.min_sample)}")
    if served_count > 0 and served_success_rate < float(args.target_success):
        reasons.append(f"served_success_rate_below_target:{served_success_rate:.3f}<{float(args.target_success):.3f}")
    if served_count > 0 and served_error_rate > float(args.max_error_rate):
        reasons.append(f"served_error_rate_above_target:{served_error_rate:.3f}>{float(args.max_error_rate):.3f}")
    if served_count > 0 and served_latency_p95 > int(args.max_p95_latency_ms):
        reasons.append(f"served_p95_latency_above_target:{served_latency_p95}>{int(args.max_p95_latency_ms)}")

    verdict = "PASS" if not reasons else "FAIL"

    print("[Skill+LLM Transform Rollout Evaluation]")
    if window_start_utc:
        print(f"- window: recent {int(args.days)} day(s) since {window_start_utc}")
    else:
        print("- window: latest rows only (no day filter)")
    print(f"- sample size: {total} (min required: {int(args.min_sample)})")
    print(f"- target count: {len(target_rows)}")
    print(f"- served count: {served_count}")
    print(f"- served success rate: {served_success_rate * 100:.1f}% ({served_success_count}/{served_count})")
    print(f"- served error rate: {served_error_rate * 100:.1f}%")
    print(f"- served latency p50/p95: {served_latency_p50}ms / {served_latency_p95}ms")
    print(f"- shadow count: {shadow_count}")
    print(f"- shadow ok rate: {shadow_ok_rate * 100:.1f}% ({shadow_ok_count}/{shadow_count})")
    print(f"- shadow latency p50/p95: {shadow_latency_p50}ms / {shadow_latency_p95}ms")
    if rollout_reasons:
        print("- rollout reasons:")
        for reason, count in sorted(rollout_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")
    print(f"- verdict: {verdict}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    payload = {
        "window_days": int(args.days),
        "window_start_utc": window_start_utc,
        "sample_size": total,
        "min_sample": int(args.min_sample),
        "target_count": len(target_rows),
        "served_count": served_count,
        "served_success_count": served_success_count,
        "served_success_rate": served_success_rate,
        "served_error_rate": served_error_rate,
        "served_latency_p50_ms": served_latency_p50,
        "served_latency_p95_ms": served_latency_p95,
        "shadow_count": shadow_count,
        "shadow_ok_count": shadow_ok_count,
        "shadow_ok_rate": shadow_ok_rate,
        "shadow_latency_p50_ms": shadow_latency_p50,
        "shadow_latency_p95_ms": shadow_latency_p95,
        "rollout_reasons": rollout_reasons,
        "verdict": verdict,
        "reasons": reasons,
    }
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
