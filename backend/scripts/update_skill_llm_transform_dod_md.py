from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CHECKLIST_TO_LABEL = {
    "primary_success_3d_ge_95": "Primary 시나리오 3일 연속 성공률 95% 이상",
    "transform_fallback_rate_le_10": "transform fallback률 10% 이하",
    "verify_fail_before_write_eq_0": "write 전 verify 누락 0건",
    "stage6_core_regression_pass": "기존 Stage6 핵심 회귀 테스트 전부 PASS",
    "canary_100_no_rollback": "rollback 없이 canary 100% 전환 완료",
    "new_service_onboarded_without_hardcoding": "신규 서비스 1건을 하드코딩 분기 추가 없이 contract+pipeline만으로 온보딩 완료",
    "intent_error_rate_2w_improved": "요청 이해 오류율 2주 이동평균 개선 확인",
    "n_to_n_e2e_verified": "N건 입력 시 N페이지 생성 정책이 E2E에서 일관되게 검증됨",
    "zero_match_success_e2e_verified": "조건 불일치 0건 시 성공형 응답 정책이 E2E에서 검증됨",
}


def _load_checklist(path: str) -> dict[str, bool]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    checklist = data.get("checklist")
    if not isinstance(checklist, dict):
        return {}
    return {str(k): bool(v) for k, v in checklist.items()}


def _set_checkbox_line(line: str, checked: bool) -> str:
    mark = "x" if checked else " "
    return re.sub(r"^- \[[ xX]\]", f"- [{mark}]", line, count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync DoD checklist JSON to markdown checkboxes.")
    parser.add_argument(
        "--dod-json",
        default="../docs/reports/skill_llm_transform_dod_latest.json",
        help="Path to DoD summary JSON",
    )
    parser.add_argument(
        "--plan-md",
        default="../docs/work-20260226-skill-llm-transform-pipeline-plan.md",
        help="Path to plan markdown file",
    )
    args = parser.parse_args()

    checklist = _load_checklist(args.dod_json)
    if not checklist:
        print("[dod-md-sync] checklist not found in JSON; nothing updated")
        return 1

    md_path = Path(args.plan_md)
    lines = md_path.read_text(encoding="utf-8").splitlines()
    updated = 0
    missing_labels: list[str] = []

    for key, label in CHECKLIST_TO_LABEL.items():
        matched = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("- ["):
                continue
            if label not in line:
                continue
            lines[i] = _set_checkbox_line(line, checklist.get(key, False))
            matched = True
            updated += 1
            break
        if not matched:
            missing_labels.append(label)

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("[dod-md-sync] updated checkboxes:", updated)
    if missing_labels:
        print("[dod-md-sync] missing labels:")
        for label in missing_labels:
            print("-", label)
    print("[dod-md-sync] file:", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
