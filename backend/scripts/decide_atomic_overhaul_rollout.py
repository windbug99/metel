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


def _recommend(*, report: dict, current_percent: int) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    verdict = str(report.get("verdict") or "FAIL").strip().upper()
    sample_size = int(report.get("sample_size") or 0)
    min_sample = int(report.get("min_sample") or 0)
    current = _bounded_percent(current_percent)

    if verdict != "PASS":
        reasons.append("gate verdict is FAIL")
        if current <= 0:
            return "hold", current, reasons
        return "rollback", _prev_step(current), reasons

    if sample_size < min_sample:
        reasons.append("sample size is below minimum")
        return "hold", current, reasons

    if current >= 100:
        reasons.append("already at max rollout")
        return "hold", 100, reasons

    reasons.append("gate passed and sample is sufficient")
    return "promote", _next_step(current), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Decide Atomic Overhaul rollout step from evaluation report")
    parser.add_argument("--report-json", type=str, required=True, help="Path to eval_atomic_overhaul_rollout output")
    parser.add_argument("--current-percent", type=int, default=0, help="Current ATOMIC_OVERHAUL_TRAFFIC_PERCENT")
    args = parser.parse_args()

    with open(args.report_json, "r", encoding="utf-8") as fp:
        report = json.load(fp)

    action, next_percent, reasons = _recommend(report=report, current_percent=args.current_percent)
    out = {
        "action": action,
        "current_percent": _bounded_percent(args.current_percent),
        "next_percent": next_percent,
        "reasons": reasons,
        "suggested_env": {
            "ATOMIC_OVERHAUL_ENABLED": "true",
            "ATOMIC_OVERHAUL_SHADOW_MODE": "false",
            "ATOMIC_OVERHAUL_TRAFFIC_PERCENT": str(next_percent),
            "ATOMIC_OVERHAUL_LEGACY_FALLBACK_ENABLED": "false" if next_percent >= 100 else "true",
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
