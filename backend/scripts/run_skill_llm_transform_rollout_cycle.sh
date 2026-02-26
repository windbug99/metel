#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-200}"
DAYS="${DAYS:-0}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
TARGET_SUCCESS="${TARGET_SUCCESS:-0.95}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-0.05}"
MAX_P95_LATENCY_MS="${MAX_P95_LATENCY_MS:-12000}"
SINCE_UTC="${SINCE_UTC:-}"

CURRENT_PERCENT="${CURRENT_PERCENT:-0}"
REQUIRE_SHADOW_OK_FOR_PROMOTE="${REQUIRE_SHADOW_OK_FOR_PROMOTE:-true}"
SHADOW_OK_THRESHOLD="${SHADOW_OK_THRESHOLD:-0.95}"

REPORT_JSON="${REPORT_DIR}/skill_llm_transform_rollout_latest.json"
DECISION_JSON="${REPORT_DIR}/skill_llm_transform_rollout_decision_latest.json"
ENV_FILE="${ENV_FILE:-.env}"
APPLY_DECISION="${APPLY_DECISION:-false}"

echo "[skill-llm-transform-cycle] running rollout gate"
cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

EVAL_ARGS=(
  --limit "${LIMIT}"
  --min-sample "${MIN_SAMPLE}"
  --target-success "${TARGET_SUCCESS}"
  --max-error-rate "${MAX_ERROR_RATE}"
  --max-p95-latency-ms "${MAX_P95_LATENCY_MS}"
  --output-json "${REPORT_JSON}"
)
if [[ -n "${SINCE_UTC}" ]]; then
  EVAL_ARGS+=(--since "${SINCE_UTC}")
else
  EVAL_ARGS+=(--days "${DAYS}")
fi
python scripts/eval_skill_llm_transform_rollout.py "${EVAL_ARGS[@]}" || true

if [[ ! -f "${REPORT_JSON}" ]]; then
  echo "[skill-llm-transform-cycle] gate report not generated: ${REPORT_JSON}"
  exit 1
fi

echo "[skill-llm-transform-cycle] computing rollout decision"
DECIDE_ARGS=(
  --report-json "${REPORT_JSON}"
  --current-percent "${CURRENT_PERCENT}"
  --shadow-ok-threshold "${SHADOW_OK_THRESHOLD}"
)
if [[ "${REQUIRE_SHADOW_OK_FOR_PROMOTE}" == "true" ]]; then
  DECIDE_ARGS+=(--require-shadow-ok-for-promote)
fi

python scripts/decide_skill_llm_transform_rollout.py "${DECIDE_ARGS[@]}" | tee "${DECISION_JSON}"

if [[ "${APPLY_DECISION}" == "true" ]]; then
  echo "[skill-llm-transform-cycle] applying decision to env file: ${ENV_FILE}"
  python scripts/apply_skill_llm_transform_rollout_decision.py \
    --from-json "${DECISION_JSON}" \
    --env-file "${ENV_FILE}" \
    --apply
fi

echo "[skill-llm-transform-cycle] done"
echo "[skill-llm-transform-cycle] report: ${REPORT_JSON}"
echo "[skill-llm-transform-cycle] decision: ${DECISION_JSON}"
