#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-1}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_SUCCESS_RATE="${TARGET_SUCCESS_RATE:-0.85}"
MAX_VALIDATION_ERROR_RATE="${MAX_VALIDATION_ERROR_RATE:-0.10}"
MAX_USER_VISIBLE_ERROR_RATE="${MAX_USER_VISIBLE_ERROR_RATE:-0.15}"
MAX_P95_LATENCY_MS="${MAX_P95_LATENCY_MS:-12000}"
REQUIRED_PERCENT="${REQUIRED_PERCENT:-100}"
SINCE_UTC="${SINCE_UTC:-}"

REPORT_JSON="${REPORT_DIR}/atomic_overhaul_rollout_latest.json"

echo "[cutover] evaluating atomic rollout with zero-legacy requirement"
cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -n "${SINCE_UTC}" ]]; then
  python scripts/eval_atomic_overhaul_rollout.py \
    --limit "${LIMIT}" \
    --since-utc "${SINCE_UTC}" \
    --min-sample "${MIN_SAMPLE}" \
    --target-success-rate "${TARGET_SUCCESS_RATE}" \
    --max-validation-error-rate "${MAX_VALIDATION_ERROR_RATE}" \
    --max-user-visible-error-rate "${MAX_USER_VISIBLE_ERROR_RATE}" \
    --max-p95-latency-ms "${MAX_P95_LATENCY_MS}" \
    --require-zero-legacy \
    --output-json "${REPORT_JSON}"
else
  python scripts/eval_atomic_overhaul_rollout.py \
    --limit "${LIMIT}" \
    --days "${DAYS}" \
    --min-sample "${MIN_SAMPLE}" \
    --target-success-rate "${TARGET_SUCCESS_RATE}" \
    --max-validation-error-rate "${MAX_VALIDATION_ERROR_RATE}" \
    --max-user-visible-error-rate "${MAX_USER_VISIBLE_ERROR_RATE}" \
    --max-p95-latency-ms "${MAX_P95_LATENCY_MS}" \
    --require-zero-legacy \
    --output-json "${REPORT_JSON}"
fi

python scripts/check_atomic_cutover_readiness.py \
  --report-json "${REPORT_JSON}" \
  --required-percent "${REQUIRED_PERCENT}"

echo "[cutover] PASS: ready to disable legacy path"
