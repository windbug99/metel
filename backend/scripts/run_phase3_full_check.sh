#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"

RUN_MCP_SMOKE="${RUN_MCP_SMOKE:-0}"
RUN_POLICY_SCENARIOS="${RUN_POLICY_SCENARIOS:-0}"
RUN_DASHBOARD_CONSISTENCY="${RUN_DASHBOARD_CONSISTENCY:-0}"
RUN_STRICT_HIGH_RISK="${RUN_STRICT_HIGH_RISK:-1}"

echo "[phase3-full] start"
echo "[phase3-full] backend_dir=${BACKEND_DIR}"
echo "[phase3-full] repo_dir=${REPO_DIR}"
echo "[phase3-full] RUN_MCP_SMOKE=${RUN_MCP_SMOKE}"
echo "[phase3-full] RUN_POLICY_SCENARIOS=${RUN_POLICY_SCENARIOS}"
echo "[phase3-full] RUN_DASHBOARD_CONSISTENCY=${RUN_DASHBOARD_CONSISTENCY}"
echo "[phase3-full] RUN_STRICT_HIGH_RISK=${RUN_STRICT_HIGH_RISK}"

echo "[phase3-full] 1/6 backend phase3 regression"
(
  cd "${BACKEND_DIR}"
  ./scripts/run_phase3_regression.sh
)

echo "[phase3-full] 2/6 backend core regression"
(
  cd "${BACKEND_DIR}"
  ./scripts/run_core_regression.sh
)

echo "[phase3-full] 3/6 frontend typecheck"
(
  cd "${REPO_DIR}/frontend"
  pnpm -s tsc --noEmit
)

if [[ "${RUN_MCP_SMOKE}" == "1" ]]; then
  echo "[phase3-full] 4/6 mcp smoke"
  (
    cd "${BACKEND_DIR}"
    ./scripts/run_mcp_smoke.sh
  )
else
  echo "[phase3-full] 4/6 mcp smoke skipped (set RUN_MCP_SMOKE=1 to enable)"
fi

if [[ "${RUN_POLICY_SCENARIOS}" == "1" ]]; then
  echo "[phase3-full] 5/6 policy scenarios"
  (
    cd "${BACKEND_DIR}"
    ./scripts/run_phase3_policy_scenarios.sh
  )
else
  echo "[phase3-full] 5/6 policy scenarios skipped (set RUN_POLICY_SCENARIOS=1 to enable)"
fi

if [[ "${RUN_DASHBOARD_CONSISTENCY}" == "1" ]]; then
  echo "[phase3-full] 6/6 dashboard consistency"
  (
    cd "${BACKEND_DIR}"
    ./scripts/run_phase3_dashboard_consistency.sh
  )
else
  echo "[phase3-full] 6/6 dashboard consistency skipped (set RUN_DASHBOARD_CONSISTENCY=1 to enable)"
fi

echo "[phase3-full] done"
