#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-30}"
MIN_SAMPLE="${MIN_SAMPLE:-20}"
TARGET_AUTONOMOUS_SUCCESS="${TARGET_AUTONOMOUS_SUCCESS:-0.80}"
MAX_FALLBACK_RATE="${MAX_FALLBACK_RATE:-0.10}"   # stricter than default gate
MAX_PLANNER_FAILED_RATE="${MAX_PLANNER_FAILED_RATE:-0.20}"
MAX_VERIFICATION_FAILED_RATE="${MAX_VERIFICATION_FAILED_RATE:-0.25}"
MAX_GUARDRAIL_DEGRADE_RATE="${MAX_GUARDRAIL_DEGRADE_RATE:-0.40}"
MIN_AUTONOMOUS_ATTEMPT_RATE="${MIN_AUTONOMOUS_ATTEMPT_RATE:-0.50}"
MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE="${MIN_AUTONOMOUS_SUCCESS_OVER_ATTEMPT_RATE:-0.70}"

echo "[slo-guard] running autonomous SLO guard"
echo "[slo-guard] limit=${LIMIT} min_sample=${MIN_SAMPLE} max_fallback_rate=${MAX_FALLBACK_RATE}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[slo-guard] preflight: supabase connectivity"
PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5

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
  --output "${REPORT_DIR}/agent_quality_slo_latest.md" \
  --output-json "${REPORT_DIR}/agent_quality_slo_latest.json"

echo "[slo-guard] PASS"
