#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

DAYS="${DAYS:-3}"
LIMIT="${LIMIT:-200}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_V2_SUCCESS="${TARGET_V2_SUCCESS:-0.85}"
MAX_V2_ERROR_RATE="${MAX_V2_ERROR_RATE:-0.15}"
MAX_V2_P95_LATENCY_MS="${MAX_V2_P95_LATENCY_MS:-12000}"
CURRENT_PERCENT="${CURRENT_PERCENT:-0}"

echo "[stage6-quickcheck] start"
echo "[stage6-quickcheck] days=${DAYS} limit=${LIMIT} current_percent=${CURRENT_PERCENT}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[stage6-quickcheck] preflight"
python scripts/check_skill_v2_rollout_prereqs.py --check-dns

echo "[stage6-quickcheck] gate"
python scripts/eval_skill_v2_rollout.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-v2-success "${TARGET_V2_SUCCESS}" \
  --max-v2-error-rate "${MAX_V2_ERROR_RATE}" \
  --max-v2-p95-latency-ms "${MAX_V2_P95_LATENCY_MS}" \
  --output-json "${REPORT_DIR}/skill_v2_rollout_latest.json" || true

echo "[stage6-quickcheck] decision(dry-run)"
python scripts/decide_skill_v2_rollout.py \
  --report-json "${REPORT_DIR}/skill_v2_rollout_latest.json" \
  --current-percent "${CURRENT_PERCENT}" \
  --require-shadow-ok-for-promote | tee "${REPORT_DIR}/skill_v2_rollout_decision_latest.json"

echo "[stage6-quickcheck] done"
echo "- report: ${REPORT_DIR}/skill_v2_rollout_latest.json"
echo "- decision: ${REPORT_DIR}/skill_v2_rollout_decision_latest.json"
