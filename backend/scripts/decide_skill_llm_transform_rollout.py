from __future__ import annotations

import argparse
import json


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


def _recommend(
    *,
    report: dict,
    current_percent: int,
    require_shadow_ok_for_promote: bool,
    shadow_ok_threshold: float,
) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    verdict = str(report.get("verdict") or "FAIL").strip().upper()
    sample_size = int(report.get("sample_size") or 0)
    min_sample = int(report.get("min_sample") or 0)
    shadow_ok_rate = float(report.get("shadow_ok_rate") or 0.0)
    shadow_count = int(report.get("shadow_count") or 0)
    served_count = int(report.get("served_count") or 0)

    current = _bounded_percent(current_percent)

    if verdict != "PASS":
        reasons.append("gate verdict is FAIL")
        if current <= 0:
            return "hold", current, reasons
        return "rollback", _prev_step(current), reasons

    if sample_size < min_sample:
        reasons.append("sample size is below minimum")
        return "hold", current, reasons

    if require_shadow_ok_for_promote and current == 0 and shadow_ok_rate < shadow_ok_threshold:
        reasons.append(f"shadow_ok_rate below promote threshold ({shadow_ok_threshold:.2f})")
        return "hold", current, reasons
    if require_shadow_ok_for_promote and current == 0 and shadow_count < min_sample:
        reasons.append(f"shadow_count below minimum sample:{shadow_count}<{min_sample}")
        return "hold", current, reasons

    if current > 0 and served_count <= 0:
        reasons.append("no served samples in current window")
        return "hold", current, reasons

    if current >= 100:
        reasons.append("already at max rollout")
        return "hold", 100, reasons

    reasons.append("gate passed and sample is sufficient")
    return "promote", _next_step(current), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Decide next rollout step from skill+llm transform gate report")
    parser.add_argument("--report-json", type=str, required=True, help="Path to eval_skill_llm_transform_rollout output json")
    parser.add_argument("--current-percent", type=int, default=0, help="Current SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT")
    parser.add_argument(
        "--require-shadow-ok-for-promote",
        action="store_true",
        help="When current=0, require shadow_ok_rate >= threshold for first promotion",
    )
    parser.add_argument("--shadow-ok-threshold", type=float, default=0.95, help="Shadow ok threshold for first promote")
    args = parser.parse_args()

    with open(args.report_json, "r", encoding="utf-8") as fp:
        report = json.load(fp)

    action, next_percent, reasons = _recommend(
        report=report,
        current_percent=args.current_percent,
        require_shadow_ok_for_promote=bool(args.require_shadow_ok_for_promote),
        shadow_ok_threshold=float(args.shadow_ok_threshold),
    )

    out = {
        "action": action,
        "current_percent": _bounded_percent(args.current_percent),
        "next_percent": next_percent,
        "reasons": reasons,
        "suggested_env": {
            "SKILL_LLM_TRANSFORM_PIPELINE_ENABLED": "true",
            "SKILL_LLM_TRANSFORM_PIPELINE_SHADOW_MODE": "false" if next_percent > 0 else "true",
            "SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT": str(next_percent),
        },
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
