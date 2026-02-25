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


_DAG_ERROR_CODES = {
    "DSL_VALIDATION_FAILED",
    "DSL_REF_NOT_FOUND",
    "LLM_AUTOFILL_FAILED",
    "TOOL_AUTH_ERROR",
    "TOOL_RATE_LIMITED",
    "TOOL_TIMEOUT",
    "VERIFY_COUNT_MISMATCH",
    "COMPENSATION_FAILED",
    "PIPELINE_TIMEOUT",
}


def _print_data_source_error(settings: object, exc: Exception) -> None:
    supabase_url = str(getattr(settings, "supabase_url", "") or "").strip()
    service_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
    host_hint = "unknown-host"
    try:
        host_hint = supabase_url.split("://", 1)[-1].split("/", 1)[0] or host_hint
    except Exception:
        host_hint = "unknown-host"
    print("[DAG Quality Evaluation]")
    print("- verdict: FAIL")
    print(f"- reasons:\n  - data_source_error:{type(exc).__name__}")
    print("- diagnostics:")
    print(f"  - SUPABASE_URL set: {'yes' if supabase_url else 'no'}")
    print(f"  - SUPABASE_SERVICE_ROLE_KEY set: {'yes' if service_key else 'no'}")
    print(f"  - target host: {host_hint}")
    print("  - action: check .env value, DNS/network/VPN/firewall, then retry")


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


def _as_int(value: str | None) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return 0


def _is_dag_row(row: dict) -> bool:
    detail_map = _parse_detail_pairs(row.get("detail"))
    if detail_map.get("dag_pipeline") == "1":
        return True
    error_code = str(row.get("error_code") or "").strip()
    return error_code in _DAG_ERROR_CODES


def _compute_metrics(rows: list[dict], pipeline_links_rows: list[dict] | None = None) -> dict[str, object]:
    dag_rows = [row for row in rows if _is_dag_row(row)]
    total = len(dag_rows)
    code_counts: dict[str, int] = {}
    reuse_total = 0
    for row in dag_rows:
        code = str(row.get("error_code") or "").strip()
        if code:
            code_counts[code] = code_counts.get(code, 0) + 1
        detail_map = _parse_detail_pairs(row.get("detail"))
        reuse_total += max(0, _as_int(detail_map.get("idempotent_success_reuse_count")))

    dsl_validation_failed = code_counts.get("DSL_VALIDATION_FAILED", 0)
    dsl_ref_not_found = code_counts.get("DSL_REF_NOT_FOUND", 0)
    verify_count_mismatch = code_counts.get("VERIFY_COUNT_MISMATCH", 0)
    compensation_failed = code_counts.get("COMPENSATION_FAILED", 0)
    idempotent_success_reuse_rate = _pct(reuse_total, total)
    link_rows = pipeline_links_rows or []
    manual_required_count = len(
        [row for row in link_rows if str(row.get("status") or "").strip().lower() == "manual_required"]
    )
    pipeline_links_error_code_counts: dict[str, int] = {}
    for row in link_rows:
        error_code = str(row.get("error_code") or "").strip()
        if not error_code:
            continue
        pipeline_links_error_code_counts[error_code] = pipeline_links_error_code_counts.get(error_code, 0) + 1
    pipeline_links_sample_size = len(link_rows)
    manual_required_rate = _pct(manual_required_count, pipeline_links_sample_size)

    return {
        "dag_sample_size": total,
        "pipeline_links_sample_size": pipeline_links_sample_size,
        "manual_required_count": manual_required_count,
        "dsl_validation_failed_count": dsl_validation_failed,
        "dsl_ref_not_found_count": dsl_ref_not_found,
        "verify_count_mismatch_count": verify_count_mismatch,
        "compensation_failed_count": compensation_failed,
        "idempotent_success_reuse_total": reuse_total,
        "manual_required_rate": manual_required_rate,
        "pipeline_links_error_code_counts": pipeline_links_error_code_counts,
        "dsl_validation_failed_rate": _pct(dsl_validation_failed, total),
        "dsl_ref_not_found_rate": _pct(dsl_ref_not_found, total),
        "verify_count_mismatch_rate": _pct(verify_count_mismatch, total),
        "compensation_failed_rate": _pct(compensation_failed, total),
        "idempotent_success_reuse_rate": idempotent_success_reuse_rate,
        "error_code_counts": code_counts,
    }


def _evaluate_gate(
    *,
    dag_sample_size: int,
    min_sample: int,
    fail_on_insufficient_sample: bool,
    dsl_validation_failed_rate: float,
    max_dsl_validation_failed_rate: float,
    dsl_ref_not_found_rate: float,
    max_dsl_ref_not_found_rate: float,
    verify_count_mismatch_rate: float,
    max_verify_count_mismatch_rate: float,
    compensation_failed_rate: float,
    max_compensation_failed_rate: float,
    manual_required_rate: float,
    max_manual_required_rate: float,
    idempotent_success_reuse_rate: float,
    min_idempotent_success_reuse_rate: float,
) -> tuple[str, list[str], bool]:
    reasons: list[str] = []
    if dag_sample_size < min_sample and fail_on_insufficient_sample:
        reasons.append(f"insufficient_sample:{dag_sample_size}<{min_sample}")
    if dsl_validation_failed_rate > max_dsl_validation_failed_rate:
        reasons.append(
            f"dsl_validation_failed_rate_above_target:{dsl_validation_failed_rate:.3f}>{max_dsl_validation_failed_rate:.3f}"
        )
    if dsl_ref_not_found_rate > max_dsl_ref_not_found_rate:
        reasons.append(
            f"dsl_ref_not_found_rate_above_target:{dsl_ref_not_found_rate:.3f}>{max_dsl_ref_not_found_rate:.3f}"
        )
    if verify_count_mismatch_rate > max_verify_count_mismatch_rate:
        reasons.append(
            f"verify_count_mismatch_rate_above_target:{verify_count_mismatch_rate:.3f}>{max_verify_count_mismatch_rate:.3f}"
        )
    if compensation_failed_rate > max_compensation_failed_rate:
        reasons.append(
            f"compensation_failed_rate_above_target:{compensation_failed_rate:.3f}>{max_compensation_failed_rate:.3f}"
        )
    if manual_required_rate > max_manual_required_rate:
        reasons.append(
            f"manual_required_rate_above_target:{manual_required_rate:.3f}>{max_manual_required_rate:.3f}"
        )
    if idempotent_success_reuse_rate < min_idempotent_success_reuse_rate:
        reasons.append(
            f"idempotent_success_reuse_rate_below_target:{idempotent_success_reuse_rate:.3f}<{min_idempotent_success_reuse_rate:.3f}"
        )
    verdict = "PASS" if not reasons else "FAIL"
    return verdict, reasons, verdict == "PASS"


def _build_policy_recommendations(
    *,
    dsl_validation_failed_rate: float,
    dsl_ref_not_found_rate: float,
    verify_count_mismatch_rate: float,
    compensation_failed_rate: float,
    manual_required_rate: float,
    idempotent_success_reuse_rate: float,
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []

    def _add(env_key: str, suggested_value: str, reason: str) -> None:
        if any(item["env_key"] == env_key for item in recommendations):
            return
        recommendations.append(
            {
                "env_key": env_key,
                "suggested_value": suggested_value,
                "reason": reason,
            }
        )

    if dsl_validation_failed_rate > 0.05:
        _add(
            "TOOL_SPECS_VALIDATE_ON_STARTUP",
            "true",
            "DSL 검증 실패 비율이 높아 계약/스키마 선검증을 강화해야 합니다.",
        )
    if dsl_ref_not_found_rate > 0.02:
        _add(
            "LLM_HYBRID_EXECUTOR_FIRST",
            "true",
            "참조 해석 실패 비율이 높아 deterministic-first 실행 비중을 높여야 합니다.",
        )
    if verify_count_mismatch_rate > 0.05:
        _add(
            "LLM_AUTONOMOUS_LIMIT_RETRY_ONCE",
            "true",
            "verify count mismatch 비율이 높아 자동 재시도/보정 정책이 필요합니다.",
        )
    if compensation_failed_rate > 0.0:
        _add(
            "LLM_AUTONOMOUS_STRICT_TOOL_SCOPE",
            "true",
            "보상 실패가 발생해 cross-service 도구 경계를 더 엄격히 유지해야 합니다.",
        )
    if manual_required_rate > 0.0:
        _add(
            "LLM_HYBRID_EXECUTOR_FIRST",
            "true",
            "manual_required 비율이 발생해 안정 구간에서 deterministic-first를 유지해야 합니다.",
        )
    if idempotent_success_reuse_rate <= 0.0:
        _add(
            "LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED",
            "false",
            "idempotent 재사용률이 낮아 mutation fallback 확장을 보수적으로 유지해야 합니다.",
        )
    return recommendations[:5]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate DAG quality metrics from command_logs.")
    parser.add_argument("--limit", type=int, default=200, help="Number of recent agent_plan logs")
    parser.add_argument("--days", type=int, default=0, help="If > 0, evaluate logs in recent N days (UTC)")
    parser.add_argument("--min-sample", type=int, default=20, help="Minimum DAG sample size")
    parser.add_argument("--max-dsl-validation-failed-rate", type=float, default=0.10)
    parser.add_argument("--max-dsl-ref-not-found-rate", type=float, default=0.05)
    parser.add_argument("--max-verify-count-mismatch-rate", type=float, default=0.10)
    parser.add_argument("--max-compensation-failed-rate", type=float, default=0.02)
    parser.add_argument("--max-manual-required-rate", type=float, default=0.05)
    parser.add_argument("--min-idempotent-success-reuse-rate", type=float, default=0.00)
    parser.add_argument("--fail-on-insufficient-sample", action="store_true")
    parser.add_argument("--output-json", type=str, default="", help="Optional JSON output path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    query = (
        supabase.table("command_logs")
        .select("status,error_code,verification_reason,detail,created_at")
        .eq("command", "agent_plan")
        .order("created_at", desc=True)
    )
    window_start_utc: str | None = None
    if int(args.days) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(args.days))
        window_start_utc = cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        query = query.gte("created_at", window_start_utc)

    try:
        rows = (query.limit(max(1, int(args.limit))).execute().data or [])
    except Exception as exc:
        _print_data_source_error(settings, exc)
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "window_days": int(args.days),
                        "window_start_utc": window_start_utc,
                        "dag_sample_size": 0,
                        "verdict": "FAIL",
                        "reasons": [f"data_source_error:{type(exc).__name__}"],
                    },
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        return 1

    pipeline_links_rows: list[dict] = []
    try:
        links_query = (
            supabase.table((get_settings().pipeline_links_table or "pipeline_links").strip() or "pipeline_links")
            .select("status,error_code,updated_at")
            .order("updated_at", desc=True)
        )
        if window_start_utc:
            links_query = links_query.gte("updated_at", window_start_utc)
        pipeline_links_rows = links_query.limit(max(1, int(args.limit))).execute().data or []
    except Exception:
        pipeline_links_rows = []

    metrics = _compute_metrics(rows, pipeline_links_rows)
    policy_recommendations = _build_policy_recommendations(
        dsl_validation_failed_rate=float(metrics["dsl_validation_failed_rate"]),
        dsl_ref_not_found_rate=float(metrics["dsl_ref_not_found_rate"]),
        verify_count_mismatch_rate=float(metrics["verify_count_mismatch_rate"]),
        compensation_failed_rate=float(metrics["compensation_failed_rate"]),
        manual_required_rate=float(metrics["manual_required_rate"]),
        idempotent_success_reuse_rate=float(metrics["idempotent_success_reuse_rate"]),
    )
    verdict, reasons, _passed = _evaluate_gate(
        dag_sample_size=int(metrics["dag_sample_size"]),
        min_sample=int(args.min_sample),
        fail_on_insufficient_sample=bool(args.fail_on_insufficient_sample),
        dsl_validation_failed_rate=float(metrics["dsl_validation_failed_rate"]),
        max_dsl_validation_failed_rate=float(args.max_dsl_validation_failed_rate),
        dsl_ref_not_found_rate=float(metrics["dsl_ref_not_found_rate"]),
        max_dsl_ref_not_found_rate=float(args.max_dsl_ref_not_found_rate),
        verify_count_mismatch_rate=float(metrics["verify_count_mismatch_rate"]),
        max_verify_count_mismatch_rate=float(args.max_verify_count_mismatch_rate),
        compensation_failed_rate=float(metrics["compensation_failed_rate"]),
        max_compensation_failed_rate=float(args.max_compensation_failed_rate),
        manual_required_rate=float(metrics["manual_required_rate"]),
        max_manual_required_rate=float(args.max_manual_required_rate),
        idempotent_success_reuse_rate=float(metrics["idempotent_success_reuse_rate"]),
        min_idempotent_success_reuse_rate=float(args.min_idempotent_success_reuse_rate),
    )

    print("[DAG Quality Evaluation]")
    if window_start_utc:
        print(f"- window: recent {int(args.days)} day(s) since {window_start_utc}")
    else:
        print("- window: latest rows only (no day filter)")
    print(f"- dag sample size: {metrics['dag_sample_size']} (min required: {args.min_sample})")
    print(
        f"- DSL_VALIDATION_FAILED rate: {float(metrics['dsl_validation_failed_rate']) * 100:.1f}% "
        f"({metrics['dsl_validation_failed_count']}/{metrics['dag_sample_size']})"
    )
    print(
        f"- DSL_REF_NOT_FOUND rate: {float(metrics['dsl_ref_not_found_rate']) * 100:.1f}% "
        f"({metrics['dsl_ref_not_found_count']}/{metrics['dag_sample_size']})"
    )
    print(
        f"- VERIFY_COUNT_MISMATCH rate: {float(metrics['verify_count_mismatch_rate']) * 100:.1f}% "
        f"({metrics['verify_count_mismatch_count']}/{metrics['dag_sample_size']})"
    )
    print(
        f"- COMPENSATION_FAILED rate: {float(metrics['compensation_failed_rate']) * 100:.1f}% "
        f"({metrics['compensation_failed_count']}/{metrics['dag_sample_size']})"
    )
    print(
        f"- manual_required_rate: {float(metrics['manual_required_rate']) * 100:.1f}% "
        f"({metrics['manual_required_count']}/{metrics['pipeline_links_sample_size']})"
    )
    print(
        f"- idempotent_success_reuse_rate: {float(metrics['idempotent_success_reuse_rate']) * 100:.1f}% "
        f"(total_reuse={metrics['idempotent_success_reuse_total']})"
    )
    if metrics.get("pipeline_links_error_code_counts"):
        print("- pipeline_links top error codes:")
        for code, count in sorted(
            dict(metrics["pipeline_links_error_code_counts"]).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]:
            print(f"  - {code}: {count}")
    print(f"- verdict: {verdict}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")
    if policy_recommendations:
        print("- policy recommendations:")
        for item in policy_recommendations:
            print(f"  - {item['env_key']}={item['suggested_value']} ({item['reason']})")

    if args.output_json:
        out = {
            "window_days": int(args.days),
            "window_start_utc": window_start_utc,
            **metrics,
            "min_sample": int(args.min_sample),
            "max_dsl_validation_failed_rate": float(args.max_dsl_validation_failed_rate),
            "max_dsl_ref_not_found_rate": float(args.max_dsl_ref_not_found_rate),
            "max_verify_count_mismatch_rate": float(args.max_verify_count_mismatch_rate),
            "max_compensation_failed_rate": float(args.max_compensation_failed_rate),
            "max_manual_required_rate": float(args.max_manual_required_rate),
            "min_idempotent_success_reuse_rate": float(args.min_idempotent_success_reuse_rate),
            "policy_recommendations": policy_recommendations,
            "verdict": verdict,
            "reasons": reasons,
        }
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(out, fp, ensure_ascii=False, indent=2)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
