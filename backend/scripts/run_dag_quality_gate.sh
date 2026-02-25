#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-0}"
MIN_SAMPLE="${MIN_SAMPLE:-20}"
MAX_DSL_VALIDATION_FAILED_RATE="${MAX_DSL_VALIDATION_FAILED_RATE:-0.10}"
MAX_DSL_REF_NOT_FOUND_RATE="${MAX_DSL_REF_NOT_FOUND_RATE:-0.05}"
MAX_VERIFY_COUNT_MISMATCH_RATE="${MAX_VERIFY_COUNT_MISMATCH_RATE:-0.10}"
MAX_COMPENSATION_FAILED_RATE="${MAX_COMPENSATION_FAILED_RATE:-0.02}"
MAX_MANUAL_REQUIRED_RATE="${MAX_MANUAL_REQUIRED_RATE:-0.05}"
MIN_IDEMPOTENT_SUCCESS_REUSE_RATE="${MIN_IDEMPOTENT_SUCCESS_REUSE_RATE:-0.00}"

echo "[gate] running dag quality gate"
echo "[gate] limit=${LIMIT} days=${DAYS} min_sample=${MIN_SAMPLE}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[gate] preflight: supabase connectivity"
PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5

python scripts/eval_dag_quality.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --max-dsl-validation-failed-rate "${MAX_DSL_VALIDATION_FAILED_RATE}" \
  --max-dsl-ref-not-found-rate "${MAX_DSL_REF_NOT_FOUND_RATE}" \
  --max-verify-count-mismatch-rate "${MAX_VERIFY_COUNT_MISMATCH_RATE}" \
  --max-compensation-failed-rate "${MAX_COMPENSATION_FAILED_RATE}" \
  --max-manual-required-rate "${MAX_MANUAL_REQUIRED_RATE}" \
  --min-idempotent-success-reuse-rate "${MIN_IDEMPOTENT_SUCCESS_REUSE_RATE}" \
  --fail-on-insufficient-sample \
  --output-json "${REPORT_DIR}/dag_quality_latest.json"

echo "[gate] PASS"
