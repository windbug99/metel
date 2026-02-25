#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
QUALITY_JSON="${REPORT_DIR}/agent_quality_latest.json"
DAG_QUALITY_JSON="${REPORT_DIR}/dag_quality_latest.json"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"

APPLY_POLICY="${APPLY_POLICY:-false}"

echo "[learning-loop] start"
echo "[learning-loop] apply_policy=${APPLY_POLICY}"
echo "[learning-loop] env_file=${ENV_FILE}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[learning-loop] step1: run quality gate"
"${ROOT_DIR}/scripts/run_autonomous_gate.sh"

echo "[learning-loop] step2: run dag quality gate"
"${ROOT_DIR}/scripts/run_dag_quality_gate.sh"

echo "[learning-loop] step3: apply policy recommendations"
if [[ "${APPLY_POLICY}" == "true" ]]; then
  python scripts/apply_agent_policy_recommendations.py \
    --from-json "${QUALITY_JSON}" \
    --from-json "${DAG_QUALITY_JSON}" \
    --env-file "${ENV_FILE}" \
    --apply
else
  python scripts/apply_agent_policy_recommendations.py \
    --from-json "${QUALITY_JSON}" \
    --from-json "${DAG_QUALITY_JSON}" \
    --env-file "${ENV_FILE}"
fi

echo "[learning-loop] done"
