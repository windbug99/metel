from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ROLLOUT_STEPS = [0, 10, 30, 100]


def _next_step(current: int) -> int:
    for step in ROLLOUT_STEPS:
        if step > current:
            return step
    return 100


def _prev_step(current: int) -> int:
    prev = 0
    for step in ROLLOUT_STEPS:
        if step >= current:
            return prev
        prev = step
    return prev


def _bounded_percent(value: int) -> int:
    return max(0, min(100, int(value)))


def _auth_error_rate(report: dict) -> float:
    sample_size = int(report.get("sample_size") or 0)
    if sample_size <= 0:
        return 0.0
    counts = report.get("error_code_counts")
    if isinstance(counts, dict):
        auth = int(counts.get("auth_error") or 0)
        return auth / sample_size
    top = report.get("top_error_codes")
    if isinstance(top, list):
        for item in top:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            if str(item[0]) == "auth_error":
                return int(item[1]) / sample_size
    return 0.0


def _kill_conditions(
    *,
    report: dict,
    previous_report: dict | None,
    max_fallback_rate_kill: float,
    min_success_over_attempt_kill: float,
    auth_error_surge_ratio: float,
) -> list[str]:
    reasons: list[str] = []
    fallback_rate = float(report.get("fallback_rate") or 0.0)
    success_over_attempt = float(report.get("autonomous_success_over_attempt_rate") or 0.0)
    if fallback_rate > max_fallback_rate_kill:
        reasons.append(
            f"kill:fallback_rate_above_threshold:{fallback_rate:.3f}>{max_fallback_rate_kill:.3f}"
        )
    if success_over_attempt < min_success_over_attempt_kill:
        reasons.append(
            "kill:autonomous_success_over_attempt_below_threshold:"
            f"{success_over_attempt:.3f}<{min_success_over_attempt_kill:.3f}"
        )
    current_auth = _auth_error_rate(report)
    if previous_report:
        prev_auth = _auth_error_rate(previous_report)
        if prev_auth > 0.0 and current_auth >= prev_auth * auth_error_surge_ratio:
            reasons.append(
                "kill:auth_error_surge:"
                f"{current_auth:.3f}>={prev_auth:.3f}*{auth_error_surge_ratio:.2f}"
            )
    return reasons


def _recommend(
    *,
    report: dict,
    current_percent: int,
    previous_report: dict | None,
    max_fallback_rate_kill: float,
    min_success_over_attempt_kill: float,
    auth_error_surge_ratio: float,
) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    verdict = str(report.get("verdict") or "FAIL").strip().upper()
    sample_size = int(report.get("sample_size") or 0)
    min_sample = int(report.get("min_sample") or 0)
    current = _bounded_percent(current_percent)

    kill_reasons = _kill_conditions(
        report=report,
        previous_report=previous_report,
        max_fallback_rate_kill=max_fallback_rate_kill,
        min_success_over_attempt_kill=min_success_over_attempt_kill,
        auth_error_surge_ratio=auth_error_surge_ratio,
    )
    if kill_reasons:
        reasons.extend(kill_reasons)
        if current <= 0:
            return "hold", 0, reasons
        return "rollback", _prev_step(current), reasons

    if verdict != "PASS":
        reasons.append("gate verdict is FAIL")
        if current <= 0:
            return "hold", 0, reasons
        return "rollback", _prev_step(current), reasons

    if sample_size < min_sample:
        reasons.append(f"sample size is below minimum:{sample_size}<{min_sample}")
        return "hold", current, reasons

    if current >= 100:
        reasons.append("already at max rollout")
        return "hold", 100, reasons

    reasons.append("gate passed and sample is sufficient")
    return "promote", _next_step(current), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Decide autonomous rollout step from agent quality report")
    parser.add_argument("--report-json", type=str, required=True, help="Path to eval_agent_quality output json")
    parser.add_argument("--current-percent", type=int, default=0, help="Current LLM_AUTONOMOUS_TRAFFIC_PERCENT")
    parser.add_argument(
        "--previous-report-json",
        type=str,
        default="",
        help="Optional previous eval report for auth_error surge detection",
    )
    parser.add_argument("--max-fallback-rate-kill", type=float, default=0.20)
    parser.add_argument("--min-success-over-attempt-kill", type=float, default=0.75)
    parser.add_argument("--auth-error-surge-ratio", type=float, default=2.0)
    args = parser.parse_args()

    with open(args.report_json, "r", encoding="utf-8") as fp:
        report = json.load(fp)

    previous_report = None
    prev_path = str(args.previous_report_json or "").strip()
    if prev_path:
        path = pathlib.Path(prev_path)
        if path.exists():
            previous_report = json.loads(path.read_text(encoding="utf-8"))

    action, next_percent, reasons = _recommend(
        report=report,
        current_percent=args.current_percent,
        previous_report=previous_report,
        max_fallback_rate_kill=float(args.max_fallback_rate_kill),
        min_success_over_attempt_kill=float(args.min_success_over_attempt_kill),
        auth_error_surge_ratio=float(args.auth_error_surge_ratio),
    )
    rollback_or_hold = action in {"rollback", "hold"} and any(reason.startswith("kill:") for reason in reasons)

    suggested_env = {
        "LLM_AUTONOMOUS_ENABLED": "true",
        "LLM_AUTONOMOUS_TRAFFIC_PERCENT": str(next_percent),
        "LLM_AUTONOMOUS_SHADOW_MODE": "true" if next_percent <= 0 else "false",
        "LLM_HYBRID_EXECUTOR_FIRST": "true" if rollback_or_hold else "false",
    }
    if action == "rollback" and next_percent <= 0:
        suggested_env["LLM_AUTONOMOUS_ENABLED"] = "false"

    out = {
        "action": action,
        "current_percent": _bounded_percent(args.current_percent),
        "next_percent": next_percent,
        "reasons": reasons,
        "suggested_env": suggested_env,
        "kill_switch_triggered": rollback_or_hold,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
