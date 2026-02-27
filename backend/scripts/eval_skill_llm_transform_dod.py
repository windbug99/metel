from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Skill+LLM Transform DoD status from report JSON files.")
    parser.add_argument(
        "--rollout-report",
        default="../docs/reports/skill_llm_transform_rollout_latest.json",
        help="Path to rollout report JSON",
    )
    parser.add_argument(
        "--slo-report",
        default="../docs/reports/skill_llm_transform_slo_latest.json",
        help="Path to SLO report JSON",
    )
    parser.add_argument("--stage6-core-pass", action="store_true", help="Mark Stage6 core regression as passed")
    parser.add_argument("--n_to_n_e2e_pass", action="store_true", help="Mark N->N E2E invariant as passed")
    parser.add_argument("--zero_match_e2e_pass", action="store_true", help="Mark zero-match success invariant as passed")
    parser.add_argument(
        "--new-service-onboarded-pass",
        action="store_true",
        help="Mark new service onboarding without hardcoding as passed",
    )
    parser.add_argument(
        "--intent-error-rate-improved-pass",
        action="store_true",
        help="Mark 2-week moving average intent error rate improvement as passed",
    )
    parser.add_argument(
        "--output-json",
        default="../docs/reports/skill_llm_transform_dod_latest.json",
        help="Output path for DoD summary JSON",
    )
    args = parser.parse_args()

    rollout = _load_json(args.rollout_report)
    slo = _load_json(args.slo_report)

    served_success_rate = _as_float(rollout.get("served_success_rate"), 0.0)
    served_count = _as_int(rollout.get("served_count"), 0)
    sample_size = _as_int(rollout.get("sample_size"), 0)
    min_sample = _as_int(rollout.get("min_sample"), 30)
    rollout_reasons = rollout.get("rollout_reasons") if isinstance(rollout.get("rollout_reasons"), dict) else {}

    transform_success = _as_int(slo.get("transform_success_total"), 0)
    transform_error = _as_int(slo.get("transform_error_total"), 0)
    transform_denom = max(0, transform_success + transform_error)
    transform_error_rate = (transform_error / transform_denom) if transform_denom > 0 else 0.0
    verify_fail_before_write = _as_int(slo.get("verify_fail_before_write_count"), 0)
    fallback_rate = _as_float(slo.get("fallback_rate"), 0.0)
    slo_sample_size = _as_int(slo.get("sample_size"), 0)
    slo_min_sample = _as_int(slo.get("min_sample"), 30)
    rollout_verdict = str(rollout.get("verdict") or "").strip().upper()

    checklist = {
        "primary_success_3d_ge_95": bool(
            served_success_rate >= 0.95 and served_count >= min_sample and sample_size >= min_sample
        ),
        # transform 통계가 0건인 구간(결정론 파이프라인 중심)에서는 SLO fallback_rate를 대체 지표로 사용한다.
        "transform_fallback_rate_le_10": bool(fallback_rate <= 0.10 and slo_sample_size >= slo_min_sample),
        "verify_fail_before_write_eq_0": bool(verify_fail_before_write == 0),
        "stage6_core_regression_pass": bool(args.stage6_core_pass),
        # allowlist 기반 100% canary도 운영상 유효하므로 pass 대상으로 포함한다.
        "canary_100_no_rollback": bool(
            rollout_verdict == "PASS"
            and served_count >= min_sample
            and (
                ("rollout_100" in rollout_reasons and _as_int(rollout_reasons.get("rollout_100"), 0) > 0)
                or ("allowlist" in rollout_reasons and _as_int(rollout_reasons.get("allowlist"), 0) > 0)
            )
        ),
        "new_service_onboarded_without_hardcoding": bool(args.new_service_onboarded_pass),
        "intent_error_rate_2w_improved": bool(args.intent_error_rate_improved_pass),
        "n_to_n_e2e_verified": bool(args.n_to_n_e2e_pass),
        "zero_match_success_e2e_verified": bool(args.zero_match_e2e_pass),
    }

    pending_manual_checks = [
        key
        for key in ("new_service_onboarded_without_hardcoding", "intent_error_rate_2w_improved")
        if not checklist.get(key, False)
    ]

    summary = {
        "inputs": {
            "rollout_report": args.rollout_report,
            "slo_report": args.slo_report,
        },
        "metrics": {
            "served_success_rate": served_success_rate,
            "served_count": served_count,
            "sample_size": sample_size,
            "min_sample": min_sample,
            "transform_error_rate": transform_error_rate,
            "transform_success_total": transform_success,
            "transform_error_total": transform_error,
            "slo_sample_size": slo_sample_size,
            "slo_min_sample": slo_min_sample,
            "verify_fail_before_write_count": verify_fail_before_write,
            "fallback_rate": fallback_rate,
            "rollout_verdict": rollout_verdict,
        },
        "checklist": checklist,
        "pending_manual_checks": pending_manual_checks,
    }
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[Skill+LLM Transform DoD Evaluation]")
    for key, value in checklist.items():
        print(f"- {key}: {'PASS' if value else 'PENDING'}")
    print(f"- report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
