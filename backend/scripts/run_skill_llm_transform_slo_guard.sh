#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-3}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_AUTONOMOUS_SUCCESS="${TARGET_AUTONOMOUS_SUCCESS:-0.80}"
MAX_FALLBACK_RATE="${MAX_FALLBACK_RATE:-0.10}"
MAX_PLANNER_FAILED_RATE="${MAX_PLANNER_FAILED_RATE:-0.20}"
MAX_VERIFICATION_FAILED_RATE="${MAX_VERIFICATION_FAILED_RATE:-0.25}"
MAX_GUARDRAIL_DEGRADE_RATE="${MAX_GUARDRAIL_DEGRADE_RATE:-0.40}"
MIN_AUTONOMOUS_ATTEMPT_RATE="${MIN_AUTONOMOUS_ATTEMPT_RATE:-0.50}"
MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE="${MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE:-0.70}"
MAX_TRANSFORM_ERROR_RATE="${MAX_TRANSFORM_ERROR_RATE:-0.10}"
MAX_VERIFY_FAIL_BEFORE_WRITE="${MAX_VERIFY_FAIL_BEFORE_WRITE:-0}"
MIN_COMPOSED_PIPELINE_COUNT="${MIN_COMPOSED_PIPELINE_COUNT:-10}"

echo "[skill-llm-transform-slo] running SLO guard"
echo "[skill-llm-transform-slo] days=${DAYS} limit=${LIMIT} min_sample=${MIN_SAMPLE}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[skill-llm-transform-slo] preflight: supabase connectivity"
PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5

JSON_REPORT="${REPORT_DIR}/skill_llm_transform_slo_latest.json"
MD_REPORT="${REPORT_DIR}/skill_llm_transform_slo_latest.md"

python scripts/eval_agent_quality.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-autonomous-success "${TARGET_AUTONOMOUS_SUCCESS}" \
  --max-fallback-rate "${MAX_FALLBACK_RATE}" \
  --max-planner-failed-rate "${MAX_PLANNER_FAILED_RATE}" \
  --max-verification-failed-rate "${MAX_VERIFICATION_FAILED_RATE}" \
  --max-guardrail-degrade-rate "${MAX_GUARDRAIL_DEGRADE_RATE}" \
  --min-autonomous-attempt-rate "${MIN_AUTONOMOUS_ATTEMPT_RATE}" \
  --min-autonomous-success-over-attempt-rate "${MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE}" \
  --fail-on-insufficient-sample \
  --output "${MD_REPORT}" \
  --output-json "${JSON_REPORT}"

python - <<'PY'
import json
import os
import sys

path = os.path.join("..", "docs", "reports", "skill_llm_transform_slo_latest.json")
with open(path, "r", encoding="utf-8") as fp:
    report = json.load(fp)

transform_success = int(report.get("transform_success_total") or 0)
transform_error = int(report.get("transform_error_total") or 0)
verify_fail_before_write = int(report.get("verify_fail_before_write_count") or 0)
composed_count = int(report.get("composed_pipeline_count") or 0)

denom = transform_success + transform_error
transform_error_rate = (transform_error / denom) if denom > 0 else 0.0

max_transform_error_rate = float(os.getenv("MAX_TRANSFORM_ERROR_RATE", "0.10"))
max_verify_fail_before_write = int(os.getenv("MAX_VERIFY_FAIL_BEFORE_WRITE", "0"))
min_composed_pipeline_count = int(os.getenv("MIN_COMPOSED_PIPELINE_COUNT", "10"))

reasons: list[str] = []
if transform_error_rate > max_transform_error_rate:
    reasons.append(
        f"transform_error_rate_above_target:{transform_error_rate:.3f}>{max_transform_error_rate:.3f}"
    )
if verify_fail_before_write > max_verify_fail_before_write:
    reasons.append(
        f"verify_fail_before_write_above_target:{verify_fail_before_write}>{max_verify_fail_before_write}"
    )
if composed_count < min_composed_pipeline_count:
    reasons.append(
        f"composed_pipeline_count_below_min:{composed_count}<{min_composed_pipeline_count}"
    )

print("[skill-llm-transform-slo] composed_pipeline_count=", composed_count)
print("[skill-llm-transform-slo] transform_error_rate=", f"{transform_error_rate:.4f}")
print("[skill-llm-transform-slo] verify_fail_before_write_count=", verify_fail_before_write)
if reasons:
    print("[skill-llm-transform-slo] FAIL")
    for reason in reasons:
        print(f"- {reason}")
    sys.exit(1)
print("[skill-llm-transform-slo] PASS")
PY

echo "[skill-llm-transform-slo] validating E2E invariants (N->N, zero-match success)"
PYTHONPATH=. pytest -q \
  tests/test_pipeline_fixture_e2e.py::test_google_calendar_to_notion_minutes_fixture_n_events_create_n_pages \
  tests/test_pipeline_fixture_e2e.py::test_google_calendar_to_notion_minutes_fixture_zero_meetings_success \
  tests/test_pipeline_fixture_e2e.py::test_google_calendar_to_linear_minutes_fixture_zero_meetings_success

echo "[skill-llm-transform-slo] PASS"
