from __future__ import annotations

import argparse
import json
import pathlib


def _load_json(path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def evaluate_readiness(*, report: dict, required_percent: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    verdict = str(report.get("verdict") or "FAIL").strip().upper()
    current_percent = _to_int(report.get("current_percent"), default=required_percent)
    legacy_row_count = _to_int(report.get("legacy_row_count"), default=0)
    sample_size = _to_int(report.get("sample_size"), default=0)
    min_sample = _to_int(report.get("min_sample"), default=0)

    if verdict != "PASS":
        reasons.append("rollout gate verdict is FAIL")
    if current_percent < required_percent:
        reasons.append(f"traffic percent below required:{current_percent}<{required_percent}")
    if legacy_row_count > 0:
        reasons.append(f"legacy rows detected:{legacy_row_count}")
    if sample_size < min_sample:
        reasons.append(f"insufficient sample:{sample_size}<{min_sample}")

    return (len(reasons) == 0), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Atomic Overhaul cutover readiness from rollout report JSON")
    parser.add_argument(
        "--report-json",
        type=str,
        required=True,
        help="Path to atomic_overhaul_rollout_latest.json",
    )
    parser.add_argument(
        "--required-percent",
        type=int,
        default=100,
        help="Required ATOMIC_OVERHAUL_TRAFFIC_PERCENT for cutover",
    )
    args = parser.parse_args()

    report_path = pathlib.Path(args.report_json).resolve()
    report = _load_json(report_path)
    ready, reasons = evaluate_readiness(report=report, required_percent=max(0, min(100, int(args.required_percent))))

    print("[Atomic Overhaul Cutover Readiness]")
    print(f"- report: {report_path}")
    print(f"- verdict: {'PASS' if ready else 'FAIL'}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
