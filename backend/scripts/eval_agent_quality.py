from __future__ import annotations

import argparse
import json
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


def _top_items(items: dict[str, int], limit: int = 5) -> list[tuple[str, int]]:
    return sorted(items.items(), key=lambda item: item[1], reverse=True)[:limit]


def _build_tuning_hints(
    *,
    top_fallback: list[tuple[str, int]],
    top_verification: list[tuple[str, int]],
    top_error_codes: list[tuple[str, int]],
) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    reason_hints = {
        "turn_limit": "turn_limit 비중이 높습니다. max_turns를 소폭 상향하고 도구 후보 수를 줄여 경로 수렴을 유도하세요.",
        "tool_call_limit": "tool_call_limit 비중이 높습니다. 요청별 필수 도구만 남기고 중복 호출 차단 규칙을 강화하세요.",
        "timeout": "timeout 비중이 높습니다. 요약 길이/페이지 수 기본값을 낮추고 timeout을 상황별로 조정하세요.",
        "replan_limit": "replan_limit 비중이 높습니다. replan 조건을 줄이고 초기 tool ranking 품질을 먼저 개선하세요.",
        "verification_failed": "verification_failed 비중이 높습니다. intent별 완료조건(verifier)을 세분화하고 final 허용 조건을 강화하세요.",
        "append_requires_multiple_targets": "복수 대상 append 검증 실패가 있습니다. 대상 수 추정 정확도를 높이고 append 실행 추적을 보강하세요.",
        "append_requires_append_block_children": "append 도구 누락이 반복됩니다. planner tool enrichment에서 append_block_children 우선순위를 높이세요.",
        "move_requires_update_page": "이동 요청에서 update_page 실행이 누락됩니다. move intent일 때 update_page를 필수 도구로 강제하세요.",
        "archive_requires_archive_tool": "삭제 요청에서 archive 도구 누락이 있습니다. delete intent일 때 update_page/delete_block 포함을 강제하세요.",
        "missing_search_tool": "조회성 요청에서 search 도구 누락이 있습니다. LLM plan 보강 단계에서 search 도구 자동 추가를 강화하세요.",
        "llm_planner_failed": "LLM planner 실패가 높습니다. 모델/프롬프트/타임아웃을 점검하고 fallback 없이도 plan 생성이 되는지 확인하세요.",
    }

    for reason, _count in top_fallback + top_verification + top_error_codes:
        hint = reason_hints.get(reason)
        if hint and hint not in seen:
            seen.add(hint)
            hints.append(hint)
    return hints[:5]


def _build_policy_recommendations(
    *,
    top_fallback: list[tuple[str, int]],
    top_verification: list[tuple[str, int]],
    top_error_codes: list[tuple[str, int]],
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(key: str, value: str, reason: str) -> None:
        token = f"{key}={value}"
        if token in seen:
            return
        seen.add(token)
        recommendations.append(
            {
                "env_key": key,
                "suggested_value": value,
                "reason": reason,
            }
        )

    for reason, _count in top_fallback + top_verification + top_error_codes:
        if reason == "turn_limit":
            _add(
                "LLM_AUTONOMOUS_MAX_TURNS",
                "8",
                "turn_limit 비중이 높아 자율 루프 turn 예산 상향이 필요합니다.",
            )
        elif reason == "tool_call_limit":
            _add(
                "LLM_AUTONOMOUS_MAX_TOOL_CALLS",
                "12",
                "tool_call_limit 비중이 높아 도구 호출 예산 상향이 필요합니다.",
            )
        elif reason == "timeout":
            _add(
                "LLM_AUTONOMOUS_TIMEOUT_SEC",
                "60",
                "timeout 비중이 높아 요청당 실행 시간 상향이 필요합니다.",
            )
        elif reason == "replan_limit":
            _add(
                "LLM_AUTONOMOUS_REPLAN_LIMIT",
                "2",
                "replan_limit 비중이 높아 재계획 허용 횟수 상향이 필요합니다.",
            )
        elif reason in {"verification_failed", "append_requires_multiple_targets"}:
            _add(
                "LLM_AUTONOMOUS_LIMIT_RETRY_ONCE",
                "true",
                "검증 실패 비중이 높아 자동 재시도 정책 유지/활성화가 필요합니다.",
            )
            _add(
                "LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED",
                "false",
                "mutation 요청은 rule fallback 대신 자율 재시도로 수렴시키는 것이 유리합니다.",
            )
        elif reason == "llm_planner_failed":
            _add(
                "LLM_PLANNER_RULE_FALLBACK_ENABLED",
                "true",
                "planner 실패 비중이 높아 서비스 연속성을 위해 planner fallback 유지가 필요합니다.",
            )
        elif reason in {"auth_error", "token_missing"}:
            _add(
                "TOOL_SPECS_VALIDATE_ON_STARTUP",
                "true",
                "초기 검증/구성 점검을 강화해 인증 관련 실패를 조기 탐지하세요.",
            )

    return recommendations[:6]


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
    top_error_codes: list[tuple[str, int]],
    autonomous_attempt_count: int,
    autonomous_attempt_rate: float,
    autonomous_success_over_attempt_rate: float,
    planner_failed_count: int,
    planner_failed_rate: float,
    max_planner_failed_rate: float,
    top_plan_source: list[tuple[str, int]],
    top_execution_mode: list[tuple[str, int]],
    tuning_hints: list[str],
    policy_recommendations: list[dict[str, str]],
    gate_reasons: list[str],
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
        (
            f"- autonomous attempt rate: {autonomous_attempt_rate * 100:.1f}% "
            f"({autonomous_attempt_count}/{total})"
        ),
        (
            f"- autonomous success over attempts: {autonomous_success_over_attempt_rate * 100:.1f}% "
            f"({autonomous_success}/{autonomous_attempt_count})"
        ),
        (
            f"- llm planner failed rate: {planner_failed_rate * 100:.1f}% "
            f"({planner_failed_count}/{total}, target <= {max_planner_failed_rate * 100:.1f}%)"
        ),
        f"- fallback rate: {fallback_rate * 100:.1f}% ({fallback_count}/{total}, target <= {max_fallback_rate * 100:.1f}%)",
        f"- verdict: {verdict}",
        "",
    ]
    if top_plan_source:
        lines.append("## Plan Source Distribution")
        lines.extend([f"- {source}: {count}" for source, count in top_plan_source])
        lines.append("")
    if top_execution_mode:
        lines.append("## Execution Mode Distribution")
        lines.extend([f"- {mode}: {count}" for mode, count in top_execution_mode])
        lines.append("")
    if top_fallback:
        lines.append("## Top Fallback Reasons")
        lines.extend([f"- {reason}: {count}" for reason, count in top_fallback])
        lines.append("")
    if top_verification:
        lines.append("## Top Verification Reasons")
        lines.extend([f"- {reason}: {count}" for reason, count in top_verification])
        lines.append("")
    if top_error_codes:
        lines.append("## Top Error Codes")
        lines.extend([f"- {code}: {count}" for code, count in top_error_codes])
        lines.append("")
    if tuning_hints:
        lines.append("## Tuning Hints")
        lines.extend([f"- {hint}" for hint in tuning_hints])
        lines.append("")
    if policy_recommendations:
        lines.append("## Policy Recommendations")
        for item in policy_recommendations:
            lines.append(
                f"- `{item['env_key']}={item['suggested_value']}`: {item['reason']}"
            )
        lines.append("")
    if gate_reasons:
        lines.append("## Gate Reasons")
        lines.extend([f"- {reason}" for reason in gate_reasons])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _evaluate_gate(
    *,
    total: int,
    min_sample: int,
    fail_on_insufficient_sample: bool,
    autonomous_success_rate: float,
    target_autonomous_success: float,
    fallback_rate: float,
    max_fallback_rate: float,
    planner_failed_rate: float,
    max_planner_failed_rate: float,
    autonomous_attempt_rate: float,
    min_autonomous_attempt_rate: float,
    autonomous_success_over_attempt_rate: float,
    min_autonomous_success_over_attempt_rate: float,
) -> tuple[str, list[str], bool]:
    gate_reasons: list[str] = []
    insufficient_sample = total < min_sample

    if insufficient_sample:
        gate_reasons.append(f"insufficient_sample: {total} < {min_sample}")
        verdict = "FAIL" if fail_on_insufficient_sample else "CHECK (insufficient sample)"
        return verdict, gate_reasons, False

    if autonomous_success_rate < target_autonomous_success:
        gate_reasons.append(
            f"autonomous_success_rate_below_target: {autonomous_success_rate:.3f} < {target_autonomous_success:.3f}"
        )
    if fallback_rate > max_fallback_rate:
        gate_reasons.append(f"fallback_rate_above_target: {fallback_rate:.3f} > {max_fallback_rate:.3f}")
    if planner_failed_rate > max_planner_failed_rate:
        gate_reasons.append(
            f"planner_failed_rate_above_target: {planner_failed_rate:.3f} > {max_planner_failed_rate:.3f}"
        )
    if autonomous_attempt_rate < min_autonomous_attempt_rate:
        gate_reasons.append(
            f"autonomous_attempt_rate_below_target: {autonomous_attempt_rate:.3f} < {min_autonomous_attempt_rate:.3f}"
        )
    if autonomous_success_over_attempt_rate < min_autonomous_success_over_attempt_rate:
        gate_reasons.append(
            "autonomous_success_over_attempt_below_target: "
            f"{autonomous_success_over_attempt_rate:.3f} < {min_autonomous_success_over_attempt_rate:.3f}"
        )

    passed = len(gate_reasons) == 0
    verdict = "PASS" if passed else "FAIL"
    return verdict, gate_reasons, passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate autonomous agent quality from command_logs.")
    parser.add_argument("--limit", type=int, default=30, help="Number of recent agent_plan logs to inspect")
    parser.add_argument("--min-sample", type=int, default=20, help="Minimum sample size for pass/fail judgment")
    parser.add_argument("--target-autonomous-success", type=float, default=0.80, help="Target autonomous success rate")
    parser.add_argument("--max-fallback-rate", type=float, default=0.20, help="Maximum fallback rate")
    parser.add_argument(
        "--max-planner-failed-rate",
        type=float,
        default=0.20,
        help="Maximum llm planner failed rate",
    )
    parser.add_argument(
        "--min-autonomous-attempt-rate",
        type=float,
        default=0.50,
        help="Minimum autonomous attempt rate",
    )
    parser.add_argument(
        "--min-autonomous-success-over-attempt-rate",
        type=float,
        default=0.70,
        help="Minimum autonomous success over attempt rate",
    )
    parser.add_argument(
        "--fail-on-insufficient-sample",
        action="store_true",
        help="Fail gate when sample size is below min-sample",
    )
    parser.add_argument("--output", type=str, default="", help="Optional markdown output path")
    parser.add_argument("--output-json", type=str, default="", help="Optional JSON output path")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    result = (
        supabase.table("command_logs")
        .select("status, execution_mode, plan_source, autonomous_fallback_reason, verification_reason, error_code, created_at")
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
    autonomous_attempt_rows = [
        row for row in rows if row.get("execution_mode") == "autonomous" or (row.get("autonomous_fallback_reason") or "").strip()
    ]
    autonomous_attempt_count = len(autonomous_attempt_rows)

    autonomous_success_rate = _pct(autonomous_success, autonomous_count)
    autonomous_attempt_rate = _pct(autonomous_attempt_count, total)
    autonomous_success_over_attempt_rate = _pct(autonomous_success, autonomous_attempt_count)
    fallback_rate = _pct(fallback_count, total)
    planner_failed_count = len([row for row in rows if (row.get("error_code") or "").strip() == "llm_planner_failed"])
    planner_failed_rate = _pct(planner_failed_count, total)

    fallback_reason_count: dict[str, int] = {}
    verification_reason_count: dict[str, int] = {}
    error_code_count: dict[str, int] = {}
    plan_source_count: dict[str, int] = {}
    execution_mode_count: dict[str, int] = {}
    for row in rows:
        fallback_reason = (row.get("autonomous_fallback_reason") or "").strip()
        if fallback_reason:
            fallback_reason_count[fallback_reason] = fallback_reason_count.get(fallback_reason, 0) + 1
        verification_reason = (row.get("verification_reason") or "").strip()
        if verification_reason:
            verification_reason_count[verification_reason] = verification_reason_count.get(verification_reason, 0) + 1
        error_code = (row.get("error_code") or "").strip()
        if error_code:
            error_code_count[error_code] = error_code_count.get(error_code, 0) + 1
        plan_source = (row.get("plan_source") or "").strip() or "unknown"
        plan_source_count[plan_source] = plan_source_count.get(plan_source, 0) + 1
        execution_mode = (row.get("execution_mode") or "").strip() or "unknown"
        execution_mode_count[execution_mode] = execution_mode_count.get(execution_mode, 0) + 1

    top_fallback = _top_items(fallback_reason_count)
    top_verification = _top_items(verification_reason_count)
    top_error_codes = _top_items(error_code_count)
    top_plan_source = _top_items(plan_source_count)
    top_execution_mode = _top_items(execution_mode_count)
    tuning_hints = _build_tuning_hints(
        top_fallback=top_fallback,
        top_verification=top_verification,
        top_error_codes=top_error_codes,
    )
    policy_recommendations = _build_policy_recommendations(
        top_fallback=top_fallback,
        top_verification=top_verification,
        top_error_codes=top_error_codes,
    )

    print("[Agent Quality Evaluation]")
    print(f"- sample size: {total} (min required: {args.min_sample})")
    print(
        f"- autonomous success rate: {autonomous_success_rate * 100:.1f}% "
        f"({autonomous_success}/{autonomous_count}, target >= {args.target_autonomous_success * 100:.1f}%)"
    )
    print(
        f"- autonomous attempt rate: {autonomous_attempt_rate * 100:.1f}% "
        f"({autonomous_attempt_count}/{total})"
    )
    print(
        f"- autonomous success over attempts: {autonomous_success_over_attempt_rate * 100:.1f}% "
        f"({autonomous_success}/{autonomous_attempt_count})"
    )
    print(
        f"- llm planner failed rate: {planner_failed_rate * 100:.1f}% "
        f"({planner_failed_count}/{total}, target <= {args.max_planner_failed_rate * 100:.1f}%)"
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
    if top_error_codes:
        print("- top error codes:")
        for code, count in top_error_codes:
            print(f"  - {code}: {count}")
    if tuning_hints:
        print("- tuning hints:")
        for hint in tuning_hints:
            print(f"  - {hint}")
    if policy_recommendations:
        print("- policy recommendations:")
        for item in policy_recommendations:
            print(f"  - {item['env_key']}={item['suggested_value']}  # {item['reason']}")

    verdict, gate_reasons, passed = _evaluate_gate(
        total=total,
        min_sample=args.min_sample,
        fail_on_insufficient_sample=bool(args.fail_on_insufficient_sample),
        autonomous_success_rate=autonomous_success_rate,
        target_autonomous_success=args.target_autonomous_success,
        fallback_rate=fallback_rate,
        max_fallback_rate=args.max_fallback_rate,
        planner_failed_rate=planner_failed_rate,
        max_planner_failed_rate=args.max_planner_failed_rate,
        autonomous_attempt_rate=autonomous_attempt_rate,
        min_autonomous_attempt_rate=args.min_autonomous_attempt_rate,
        autonomous_success_over_attempt_rate=autonomous_success_over_attempt_rate,
        min_autonomous_success_over_attempt_rate=args.min_autonomous_success_over_attempt_rate,
    )

    if gate_reasons:
        print("- gate reasons:")
        for reason in gate_reasons:
            print(f"  - {reason}")
    print(f"- verdict: {verdict}")

    if total < args.min_sample:
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
                top_error_codes=top_error_codes,
                autonomous_attempt_count=autonomous_attempt_count,
                autonomous_attempt_rate=autonomous_attempt_rate,
                autonomous_success_over_attempt_rate=autonomous_success_over_attempt_rate,
                planner_failed_count=planner_failed_count,
                planner_failed_rate=planner_failed_rate,
                max_planner_failed_rate=args.max_planner_failed_rate,
                top_plan_source=top_plan_source,
                top_execution_mode=top_execution_mode,
                tuning_hints=tuning_hints,
                policy_recommendations=policy_recommendations,
                gate_reasons=gate_reasons,
                verdict=verdict,
            )
            with open(args.output, "w", encoding="utf-8") as fp:
                fp.write(report)
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "sample_size": total,
                        "min_sample": args.min_sample,
                        "autonomous_success": autonomous_success,
                        "autonomous_count": autonomous_count,
                        "autonomous_success_rate": autonomous_success_rate,
                        "autonomous_attempt_count": autonomous_attempt_count,
                        "autonomous_attempt_rate": autonomous_attempt_rate,
                        "autonomous_success_over_attempt_rate": autonomous_success_over_attempt_rate,
                        "planner_failed_count": planner_failed_count,
                        "planner_failed_rate": planner_failed_rate,
                        "fallback_count": fallback_count,
                        "fallback_rate": fallback_rate,
                        "top_fallback": top_fallback,
                        "top_verification": top_verification,
                        "top_error_codes": top_error_codes,
                        "top_plan_source": top_plan_source,
                        "top_execution_mode": top_execution_mode,
                        "tuning_hints": tuning_hints,
                        "policy_recommendations": policy_recommendations,
                        "gate_reasons": gate_reasons,
                        "verdict": verdict,
                    },
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        return 0 if (not args.fail_on_insufficient_sample) else 1

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
            top_error_codes=top_error_codes,
            autonomous_attempt_count=autonomous_attempt_count,
            autonomous_attempt_rate=autonomous_attempt_rate,
            autonomous_success_over_attempt_rate=autonomous_success_over_attempt_rate,
            planner_failed_count=planner_failed_count,
            planner_failed_rate=planner_failed_rate,
            max_planner_failed_rate=args.max_planner_failed_rate,
            top_plan_source=top_plan_source,
            top_execution_mode=top_execution_mode,
            tuning_hints=tuning_hints,
            policy_recommendations=policy_recommendations,
            gate_reasons=gate_reasons,
            verdict=verdict,
        )
        with open(args.output, "w", encoding="utf-8") as fp:
            fp.write(report)
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "sample_size": total,
                    "min_sample": args.min_sample,
                    "autonomous_success": autonomous_success,
                    "autonomous_count": autonomous_count,
                    "autonomous_success_rate": autonomous_success_rate,
                    "autonomous_attempt_count": autonomous_attempt_count,
                    "autonomous_attempt_rate": autonomous_attempt_rate,
                    "autonomous_success_over_attempt_rate": autonomous_success_over_attempt_rate,
                    "planner_failed_count": planner_failed_count,
                    "planner_failed_rate": planner_failed_rate,
                    "fallback_count": fallback_count,
                    "fallback_rate": fallback_rate,
                    "top_fallback": top_fallback,
                    "top_verification": top_verification,
                    "top_error_codes": top_error_codes,
                    "top_plan_source": top_plan_source,
                    "top_execution_mode": top_execution_mode,
                    "tuning_hints": tuning_hints,
                    "policy_recommendations": policy_recommendations,
                    "gate_reasons": gate_reasons,
                    "verdict": verdict,
                },
                fp,
                ensure_ascii=False,
                indent=2,
            )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
