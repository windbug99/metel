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


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Skill V2 rollout/shadow metrics from command_logs.")
    parser.add_argument("--limit", type=int, default=100, help="Number of recent agent_plan logs")
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="If > 0, evaluate logs within recent N days (UTC). 0 means no time filter.",
    )
    parser.add_argument("--min-sample", type=int, default=30, help="Minimum sample size")
    parser.add_argument("--target-v2-success", type=float, default=0.85, help="Target V2 success rate")
    parser.add_argument("--max-v2-error-rate", type=float, default=0.15, help="Maximum V2 error rate")
    parser.add_argument(
        "--max-v2-p95-latency-ms",
        type=int,
        default=12000,
        help="Maximum allowed p95 latency(ms) for selected V2 responses",
    )
    parser.add_argument("--output-json", type=str, default="", help="Optional JSON output path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    query = (
        supabase.table("command_logs")
        .select("status, plan_source, execution_mode, detail, error_code, created_at")
        .eq("command", "agent_plan")
        .order("created_at", desc=True)
    )
    window_start_utc: str | None = None
    if int(args.days) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(args.days))
        window_start_utc = cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        query = query.gte("created_at", window_start_utc)
    try:
        result = query.limit(max(1, args.limit)).execute()
    except Exception as exc:
        print("[Skill V2 Rollout Evaluation]")
        if window_start_utc:
            print(f"- window: recent {int(args.days)} day(s) since {window_start_utc}")
        else:
            print("- window: latest rows only (no day filter)")
        print(f"- verdict: FAIL")
        print(f"- reasons:")
        print(f"  - data_source_error:{type(exc).__name__}")
        if args.output_json:
            payload = {
                "window_days": int(args.days),
                "window_start_utc": window_start_utc,
                "sample_size": 0,
                "min_sample": args.min_sample,
                "v2_selected_count": 0,
                "v2_success_count": 0,
                "v2_success_rate": 0.0,
                "v2_error_rate": 0.0,
                "v2_latency_p50_ms": 0,
                "v2_latency_p95_ms": 0,
                "shadow_count": 0,
                "shadow_ok_count": 0,
                "shadow_ok_rate": 0.0,
                "shadow_latency_p50_ms": 0,
                "shadow_latency_p95_ms": 0,
                "rollout_reasons": {},
                "router_sources": {},
                "verdict": "FAIL",
                "reasons": [f"data_source_error:{type(exc).__name__}"],
            }
            with open(args.output_json, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
        return 1
    rows = result.data or []
    total = len(rows)

    v2_selected = [row for row in rows if (row.get("plan_source") or "").strip() == "router_v2"]
    v2_selected_count = len(v2_selected)
    v2_success_count = len([row for row in v2_selected if (row.get("status") or "").strip() == "success"])
    v2_selected_latency: list[int] = []
    for row in v2_selected:
        detail_map = _parse_detail_pairs(row.get("detail"))
        latency = _as_int(detail_map.get("analysis_latency_ms"))
        if latency is not None and latency >= 0:
            v2_selected_latency.append(latency)

    shadow_rows = []
    for row in rows:
        detail_map = _parse_detail_pairs(row.get("detail"))
        if detail_map.get("skill_v2_shadow_executed") == "1":
            shadow_rows.append((row, detail_map))

    shadow_count = len(shadow_rows)
    shadow_ok_count = len([1 for row, detail in shadow_rows if detail.get("skill_v2_shadow_ok") == "1"])
    shadow_latency: list[int] = []
    for _row, detail in shadow_rows:
        latency = _as_int(detail.get("analysis_latency_ms"))
        if latency is not None and latency >= 0:
            shadow_latency.append(latency)

    rollout_reasons: dict[str, int] = {}
    router_sources: dict[str, int] = {}
    for row in rows:
        detail_map = _parse_detail_pairs(row.get("detail"))
        rollout = detail_map.get("skill_v2_rollout")
        if rollout:
            rollout_reasons[rollout] = rollout_reasons.get(rollout, 0) + 1
        source = detail_map.get("router_source")
        if source:
            router_sources[source] = router_sources.get(source, 0) + 1

    v2_success_rate = _pct(v2_success_count, v2_selected_count)
    v2_error_rate = 1.0 - v2_success_rate if v2_selected_count > 0 else 0.0
    shadow_ok_rate = _pct(shadow_ok_count, shadow_count)
    v2_latency_p50 = _percentile(v2_selected_latency, 0.50)
    v2_latency_p95 = _percentile(v2_selected_latency, 0.95)
    shadow_latency_p50 = _percentile(shadow_latency, 0.50)
    shadow_latency_p95 = _percentile(shadow_latency, 0.95)

    print("[Skill V2 Rollout Evaluation]")
    if window_start_utc:
        print(f"- window: recent {int(args.days)} day(s) since {window_start_utc}")
    else:
        print("- window: latest rows only (no day filter)")
    print(f"- sample size: {total} (min required: {args.min_sample})")
    print(f"- v2 selected count: {v2_selected_count}")
    print(f"- v2 success rate: {v2_success_rate * 100:.1f}% ({v2_success_count}/{v2_selected_count})")
    print(f"- v2 error rate: {v2_error_rate * 100:.1f}%")
    print(f"- v2 latency p50/p95: {v2_latency_p50}ms / {v2_latency_p95}ms")
    print(f"- v2 shadow count: {shadow_count}")
    print(f"- v2 shadow ok rate: {shadow_ok_rate * 100:.1f}% ({shadow_ok_count}/{shadow_count})")
    print(f"- v2 shadow latency p50/p95: {shadow_latency_p50}ms / {shadow_latency_p95}ms")

    if rollout_reasons:
        print("- rollout reasons:")
        for reason, count in sorted(rollout_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")
    if router_sources:
        print("- router sources:")
        for source, count in sorted(router_sources.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {source}: {count}")

    reasons: list[str] = []
    if total < args.min_sample:
        reasons.append(f"insufficient_sample:{total}<{args.min_sample}")
    if v2_selected_count > 0 and v2_success_rate < args.target_v2_success:
        reasons.append(f"v2_success_rate_below_target:{v2_success_rate:.3f}<{args.target_v2_success:.3f}")
    if v2_selected_count > 0 and v2_error_rate > args.max_v2_error_rate:
        reasons.append(f"v2_error_rate_above_target:{v2_error_rate:.3f}>{args.max_v2_error_rate:.3f}")
    if v2_selected_count > 0 and v2_latency_p95 > int(args.max_v2_p95_latency_ms):
        reasons.append(f"v2_p95_latency_above_target:{v2_latency_p95}>{int(args.max_v2_p95_latency_ms)}")

    verdict = "PASS" if not reasons else "FAIL"
    print(f"- verdict: {verdict}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    if args.output_json:
        payload = {
            "window_days": int(args.days),
            "window_start_utc": window_start_utc,
            "sample_size": total,
            "min_sample": args.min_sample,
            "v2_selected_count": v2_selected_count,
            "v2_success_count": v2_success_count,
            "v2_success_rate": v2_success_rate,
            "v2_error_rate": v2_error_rate,
            "v2_latency_p50_ms": v2_latency_p50,
            "v2_latency_p95_ms": v2_latency_p95,
            "shadow_count": shadow_count,
            "shadow_ok_count": shadow_ok_count,
            "shadow_ok_rate": shadow_ok_rate,
            "shadow_latency_p50_ms": shadow_latency_p50,
            "shadow_latency_p95_ms": shadow_latency_p95,
            "rollout_reasons": rollout_reasons,
            "router_sources": router_sources,
            "verdict": verdict,
            "reasons": reasons,
        }
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
