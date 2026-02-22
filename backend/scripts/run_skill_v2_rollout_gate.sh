#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-0}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_V2_SUCCESS="${TARGET_V2_SUCCESS:-0.85}"
MAX_V2_ERROR_RATE="${MAX_V2_ERROR_RATE:-0.15}"
MAX_V2_P95_LATENCY_MS="${MAX_V2_P95_LATENCY_MS:-12000}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-false}"

echo "[gate] running skill v2 rollout gate"
echo "[gate] limit=${LIMIT} days=${DAYS} min_sample=${MIN_SAMPLE} target_v2_success=${TARGET_V2_SUCCESS} max_v2_error_rate=${MAX_V2_ERROR_RATE} max_v2_p95_latency_ms=${MAX_V2_P95_LATENCY_MS}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ "${SKIP_PREFLIGHT}" != "true" ]]; then
  echo "[gate] preflight check"
  python scripts/check_skill_v2_rollout_prereqs.py --check-dns
fi

python scripts/eval_skill_v2_rollout.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-v2-success "${TARGET_V2_SUCCESS}" \
  --max-v2-error-rate "${MAX_V2_ERROR_RATE}" \
  --max-v2-p95-latency-ms "${MAX_V2_P95_LATENCY_MS}" \
  --output-json "${REPORT_DIR}/skill_v2_rollout_latest.json"

echo "[gate] PASS"
