#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

# gate params
LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-0}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_V2_SUCCESS="${TARGET_V2_SUCCESS:-0.85}"
MAX_V2_ERROR_RATE="${MAX_V2_ERROR_RATE:-0.15}"
MAX_V2_P95_LATENCY_MS="${MAX_V2_P95_LATENCY_MS:-12000}"

# decision params
CURRENT_PERCENT="${CURRENT_PERCENT:-0}"
REQUIRE_SHADOW_OK_FOR_PROMOTE="${REQUIRE_SHADOW_OK_FOR_PROMOTE:-true}"

REPORT_JSON="${REPORT_DIR}/skill_v2_rollout_latest.json"
DECISION_JSON="${REPORT_DIR}/skill_v2_rollout_decision_latest.json"
ENV_FILE="${ENV_FILE:-.env}"
APPLY_DECISION="${APPLY_DECISION:-false}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-false}"

echo "[cycle] running skill v2 rollout gate"
cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ "${SKIP_PREFLIGHT}" != "true" ]]; then
  echo "[cycle] preflight check"
  python scripts/check_skill_v2_rollout_prereqs.py --check-dns
fi

python scripts/eval_skill_v2_rollout.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --min-sample "${MIN_SAMPLE}" \
  --target-v2-success "${TARGET_V2_SUCCESS}" \
  --max-v2-error-rate "${MAX_V2_ERROR_RATE}" \
  --max-v2-p95-latency-ms "${MAX_V2_P95_LATENCY_MS}" \
  --output-json "${REPORT_JSON}" || true

if [[ ! -f "${REPORT_JSON}" ]]; then
  echo "[cycle] gate report not generated: ${REPORT_JSON}"
  echo "[cycle] check network access and SUPABASE_* settings, then retry."
  exit 1
fi

echo "[cycle] computing rollout decision"
DECIDE_ARGS=(
  --report-json "${REPORT_JSON}"
  --current-percent "${CURRENT_PERCENT}"
)
if [[ "${REQUIRE_SHADOW_OK_FOR_PROMOTE}" == "true" ]]; then
  DECIDE_ARGS+=(--require-shadow-ok-for-promote)
fi

python scripts/decide_skill_v2_rollout.py "${DECIDE_ARGS[@]}" | tee "${DECISION_JSON}"

if [[ "${APPLY_DECISION}" == "true" ]]; then
  echo "[cycle] applying decision to env file: ${ENV_FILE}"
  python scripts/apply_skill_v2_rollout_decision.py \
    --from-json "${DECISION_JSON}" \
    --env-file "${ENV_FILE}" \
    --apply
fi

echo "[cycle] done"
echo "[cycle] report: ${REPORT_JSON}"
echo "[cycle] decision: ${DECISION_JSON}"
