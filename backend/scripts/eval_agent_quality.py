from __future__ import annotations

import argparse
import pathlib
import sys

from supabase import create_client

# Allow running as: python scripts/eval_agent_quality.py
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _build_markdown_report(
    *,
    total: int,
    min_sample: int,
    autonomous_success: int,
    autonomous_count: int,
    autonomous_success_rate: float,
    target_autonomous_success: float,
    fallback_count: int,
    fallback_rate: float,
    max_fallback_rate: float,
    top_fallback: list[tuple[str, int]],
    top_verification: list[tuple[str, int]],
    verdict: str,
) -> str:
    lines = [
        "# Agent Quality Report",
        "",
        f"- sample size: {total} (min required: {min_sample})",
        (
            f"- autonomous success rate: {autonomous_success_rate * 100:.1f}% "
            f"({autonomous_success}/{autonomous_count}, target >= {target_autonomous_success * 100:.1f}%)"
        ),
        f"- fallback rate: {fallback_rate * 100:.1f}% ({fallback_count}/{total}, target <= {max_fallback_rate * 100:.1f}%)",
        f"- verdict: {verdict}",
        "",
    ]
    if top_fallback:
        lines.append("## Top Fallback Reasons")
        lines.extend([f"- {reason}: {count}" for reason, count in top_fallback])
        lines.append("")
    if top_verification:
        lines.append("## Top Verification Reasons")
        lines.extend([f"- {reason}: {count}" for reason, count in top_verification])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate autonomous agent quality from command_logs.")
    parser.add_argument("--limit", type=int, default=30, help="Number of recent agent_plan logs to inspect")
    parser.add_argument("--min-sample", type=int, default=20, help="Minimum sample size for pass/fail judgment")
    parser.add_argument("--target-autonomous-success", type=float, default=0.80, help="Target autonomous success rate")
    parser.add_argument("--max-fallback-rate", type=float, default=0.20, help="Maximum fallback rate")
    parser.add_argument("--output", type=str, default="", help="Optional markdown output path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    result = (
        supabase.table("command_logs")
        .select("status, execution_mode, autonomous_fallback_reason, verification_reason, created_at")
        .eq("command", "agent_plan")
        .order("created_at", desc=True)
        .limit(max(1, args.limit))
        .execute()
    )
    rows = result.data or []
    total = len(rows)
    autonomous_rows = [row for row in rows if row.get("execution_mode") == "autonomous"]
    autonomous_count = len(autonomous_rows)
    autonomous_success = len([row for row in autonomous_rows if row.get("status") == "success"])
    fallback_count = len([row for row in rows if row.get("autonomous_fallback_reason")])

    autonomous_success_rate = _pct(autonomous_success, autonomous_count)
    fallback_rate = _pct(fallback_count, total)

    fallback_reason_count: dict[str, int] = {}
    verification_reason_count: dict[str, int] = {}
    for row in rows:
        fallback_reason = (row.get("autonomous_fallback_reason") or "").strip()
        if fallback_reason:
            fallback_reason_count[fallback_reason] = fallback_reason_count.get(fallback_reason, 0) + 1
        verification_reason = (row.get("verification_reason") or "").strip()
        if verification_reason:
            verification_reason_count[verification_reason] = verification_reason_count.get(verification_reason, 0) + 1

    top_fallback = sorted(fallback_reason_count.items(), key=lambda item: item[1], reverse=True)[:5]
    top_verification = sorted(verification_reason_count.items(), key=lambda item: item[1], reverse=True)[:5]

    print("[Agent Quality Evaluation]")
    print(f"- sample size: {total} (min required: {args.min_sample})")
    print(
        f"- autonomous success rate: {autonomous_success_rate * 100:.1f}% "
        f"({autonomous_success}/{autonomous_count}, target >= {args.target_autonomous_success * 100:.1f}%)"
    )
    print(f"- fallback rate: {fallback_rate * 100:.1f}% ({fallback_count}/{total}, target <= {args.max_fallback_rate * 100:.1f}%)")

    if top_fallback:
        print("- top fallback reasons:")
        for reason, count in top_fallback:
            print(f"  - {reason}: {count}")
    if top_verification:
        print("- top verification reasons:")
        for reason, count in top_verification:
            print(f"  - {reason}: {count}")

    verdict = "CHECK (insufficient sample)"
    if total < args.min_sample:
        print(f"- verdict: {verdict}")
        if args.output:
            report = _build_markdown_report(
                total=total,
                min_sample=args.min_sample,
                autonomous_success=autonomous_success,
                autonomous_count=autonomous_count,
                autonomous_success_rate=autonomous_success_rate,
                target_autonomous_success=args.target_autonomous_success,
                fallback_count=fallback_count,
                fallback_rate=fallback_rate,
                max_fallback_rate=args.max_fallback_rate,
                top_fallback=top_fallback,
                top_verification=top_verification,
                verdict=verdict,
            )
            with open(args.output, "w", encoding="utf-8") as fp:
                fp.write(report)
        return 0

    passed = autonomous_success_rate >= args.target_autonomous_success and fallback_rate <= args.max_fallback_rate
    verdict = "PASS" if passed else "FAIL"
    print(f"- verdict: {verdict}")
    if args.output:
        report = _build_markdown_report(
            total=total,
            min_sample=args.min_sample,
            autonomous_success=autonomous_success,
            autonomous_count=autonomous_count,
            autonomous_success_rate=autonomous_success_rate,
            target_autonomous_success=args.target_autonomous_success,
            fallback_count=fallback_count,
            fallback_rate=fallback_rate,
            max_fallback_rate=args.max_fallback_rate,
            top_fallback=top_fallback,
            top_verification=top_verification,
            verdict=verdict,
        )
        with open(args.output, "w", encoding="utf-8") as fp:
            fp.write(report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
