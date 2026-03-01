#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-0}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_SUCCESS_RATE="${TARGET_SUCCESS_RATE:-0.85}"
MAX_VALIDATION_ERROR_RATE="${MAX_VALIDATION_ERROR_RATE:-0.10}"
MAX_USER_VISIBLE_ERROR_RATE="${MAX_USER_VISIBLE_ERROR_RATE:-0.15}"
MAX_P95_LATENCY_MS="${MAX_P95_LATENCY_MS:-12000}"

CURRENT_PERCENT="${CURRENT_PERCENT:-0}"
ENV_FILE="${ENV_FILE:-.env}"
APPLY_DECISION="${APPLY_DECISION:-false}"

REPORT_JSON="${REPORT_DIR}/atomic_overhaul_rollout_latest.json"
DECISION_JSON="${REPORT_DIR}/atomic_overhaul_rollout_decision_latest.json"

echo "[cycle] running atomic overhaul rollout gate"
cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python scripts/eval_atomic_overhaul_rollout.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-success-rate "${TARGET_SUCCESS_RATE}" \
  --max-validation-error-rate "${MAX_VALIDATION_ERROR_RATE}" \
  --max-user-visible-error-rate "${MAX_USER_VISIBLE_ERROR_RATE}" \
  --max-p95-latency-ms "${MAX_P95_LATENCY_MS}" \
  --output-json "${REPORT_JSON}" || true

if [[ ! -f "${REPORT_JSON}" ]]; then
  echo "[cycle] gate report not generated: ${REPORT_JSON}"
  exit 1
fi

echo "[cycle] computing rollout decision"
python scripts/decide_atomic_overhaul_rollout.py \
  --report-json "${REPORT_JSON}" \
  --current-percent "${CURRENT_PERCENT}" | tee "${DECISION_JSON}"

if [[ "${APPLY_DECISION}" == "true" ]]; then
  echo "[cycle] applying decision to env file: ${ENV_FILE}"
  python scripts/apply_atomic_overhaul_rollout_decision.py \
    --from-json "${DECISION_JSON}" \
    --env-file "${ENV_FILE}" \
    --apply
fi

echo "[cycle] done"
echo "[cycle] report: ${REPORT_JSON}"
echo "[cycle] decision: ${DECISION_JSON}"
