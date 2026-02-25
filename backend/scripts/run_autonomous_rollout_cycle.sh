#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

# gate params
LIMIT="${LIMIT:-200}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_AUTONOMOUS_SUCCESS="${TARGET_AUTONOMOUS_SUCCESS:-0.90}"
MAX_FALLBACK_RATE="${MAX_FALLBACK_RATE:-0.10}"
MAX_PLANNER_FAILED_RATE="${MAX_PLANNER_FAILED_RATE:-0.20}"
MAX_VERIFICATION_FAILED_RATE="${MAX_VERIFICATION_FAILED_RATE:-0.25}"
MAX_GUARDRAIL_DEGRADE_RATE="${MAX_GUARDRAIL_DEGRADE_RATE:-0.40}"
MIN_AUTONOMOUS_ATTEMPT_RATE="${MIN_AUTONOMOUS_ATTEMPT_RATE:-0.90}"
MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE="${MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE:-0.85}"

# decision params
CURRENT_PERCENT="${CURRENT_PERCENT:-0}"
MAX_FALLBACK_RATE_KILL="${MAX_FALLBACK_RATE_KILL:-0.20}"
MIN_SUCCESS_OVER_ATTEMPT_KILL="${MIN_SUCCESS_OVER_ATTEMPT_KILL:-0.75}"
AUTH_ERROR_SURGE_RATIO="${AUTH_ERROR_SURGE_RATIO:-2.0}"

REPORT_JSON="${REPORT_DIR}/agent_quality_latest.json"
PREV_REPORT_JSON="${REPORT_DIR}/agent_quality_prev.json"
DECISION_JSON="${REPORT_DIR}/autonomous_rollout_decision_latest.json"
ENV_FILE="${ENV_FILE:-.env}"
APPLY_DECISION="${APPLY_DECISION:-false}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-false}"

echo "[autonomous-cycle] running autonomous rollout cycle"
cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f "${REPORT_JSON}" ]]; then
  cp "${REPORT_JSON}" "${PREV_REPORT_JSON}"
fi

if [[ "${SKIP_PREFLIGHT}" != "true" ]]; then
  echo "[autonomous-cycle] preflight: supabase connectivity"
  PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5
fi

python scripts/eval_agent_quality.py \
  --limit "${LIMIT}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-autonomous-success "${TARGET_AUTONOMOUS_SUCCESS}" \
  --max-fallback-rate "${MAX_FALLBACK_RATE}" \
  --max-planner-failed-rate "${MAX_PLANNER_FAILED_RATE}" \
  --max-verification-failed-rate "${MAX_VERIFICATION_FAILED_RATE}" \
  --max-guardrail-degrade-rate "${MAX_GUARDRAIL_DEGRADE_RATE}" \
  --min-autonomous-attempt-rate "${MIN_AUTONOMOUS_ATTEMPT_RATE}" \
  --min-autonomous-success-over-attempt-rate "${MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE}" \
  --fail-on-insufficient-sample \
  --output "${REPORT_DIR}/agent_quality_latest.md" \
  --output-json "${REPORT_JSON}" || true

if [[ ! -f "${REPORT_JSON}" ]]; then
  echo "[autonomous-cycle] gate report not generated: ${REPORT_JSON}"
  exit 1
fi

DECIDE_ARGS=(
  --report-json "${REPORT_JSON}"
  --current-percent "${CURRENT_PERCENT}"
  --max-fallback-rate-kill "${MAX_FALLBACK_RATE_KILL}"
  --min-success-over-attempt-kill "${MIN_SUCCESS_OVER_ATTEMPT_KILL}"
  --auth-error-surge-ratio "${AUTH_ERROR_SURGE_RATIO}"
)
if [[ -f "${PREV_REPORT_JSON}" ]]; then
  DECIDE_ARGS+=(--previous-report-json "${PREV_REPORT_JSON}")
fi

echo "[autonomous-cycle] computing rollout decision"
python scripts/decide_autonomous_rollout.py "${DECIDE_ARGS[@]}" | tee "${DECISION_JSON}"

if [[ "${APPLY_DECISION}" == "true" ]]; then
  echo "[autonomous-cycle] applying decision to env file: ${ENV_FILE}"
  python scripts/apply_autonomous_rollout_decision.py \
    --from-json "${DECISION_JSON}" \
    --env-file "${ENV_FILE}" \
    --apply
fi

echo "[autonomous-cycle] done"
echo "[autonomous-cycle] report: ${REPORT_JSON}"
echo "[autonomous-cycle] decision: ${DECISION_JSON}"
