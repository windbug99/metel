#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIRE_MOBILE_MANUAL_QA="${REQUIRE_MOBILE_MANUAL_QA:-0}"

PASS=0
FAIL=0
SKIP=0

pass() {
  echo "[PASS] $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "[FAIL] $1"
  FAIL=$((FAIL + 1))
}

skip() {
  echo "[SKIP] $1"
  SKIP=$((SKIP + 1))
}

run_step() {
  local label="$1"
  shift
  if "$@"; then
    pass "${label}"
    return 0
  else
    fail "${label}"
    return 1
  fi
}

echo "[dashboard-v2-qa-gate] 1/2 static checks"
run_step "deeplink static check" "${SCRIPT_DIR}/run_dashboard_v2_deeplink_static_check.sh"
run_step "query scope static check" "${SCRIPT_DIR}/run_dashboard_v2_query_scope_static_check.sh"
run_step "mobile static check" "${SCRIPT_DIR}/run_dashboard_v2_mobile_static_check.sh"

echo "[dashboard-v2-qa-gate] 2/2 runtime checks (optional env)"
if [[ -n "${API_BASE_URL:-}" && -n "${OWNER_JWT:-}" && -n "${ADMIN_JWT:-}" && -n "${MEMBER_JWT:-}" ]]; then
  if run_step "rbac test token validation" "${SCRIPT_DIR}/validate_rbac_test_tokens.sh"; then
    run_step "menu rbac smoke" "${SCRIPT_DIR}/run_dashboard_v2_menu_rbac_smoke.sh"
    run_step "phase3 dashboard consistency" "${SCRIPT_DIR}/run_phase3_dashboard_consistency.sh"
  else
    skip "menu rbac smoke (skipped due to invalid role tokens)"
    skip "phase3 dashboard consistency (skipped due to invalid role tokens)"
  fi
else
  skip "menu rbac smoke (requires API_BASE_URL, OWNER_JWT, ADMIN_JWT, MEMBER_JWT)"
  skip "phase3 dashboard consistency (requires API_BASE_URL, OWNER_JWT, ADMIN_JWT, MEMBER_JWT)"
fi

if [[ "${REQUIRE_MOBILE_MANUAL_QA}" == "1" ]]; then
  run_step "mobile manual qa log check" "${SCRIPT_DIR}/check_dashboard_mobile_manual_qa_log.sh"
else
  skip "mobile manual qa log check (set REQUIRE_MOBILE_MANUAL_QA=1 to enforce)"
fi

echo "[dashboard-v2-qa-gate] pass=${PASS} fail=${FAIL} skip=${SKIP}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
echo "[dashboard-v2-qa-gate] done"
