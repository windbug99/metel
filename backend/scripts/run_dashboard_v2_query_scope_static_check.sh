#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHELL_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/shell.tsx"
NAV_MODEL_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/nav-model.ts"
NAV_MAIN_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/sidebar07/nav-main.tsx"

for f in "${SHELL_PAGE}" "${NAV_MODEL_PAGE}" "${NAV_MAIN_PAGE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "[dashboard-v2-query-scope] ERROR: missing file ${f}"
    exit 1
  fi
done

match_pattern() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "${pattern}" "${file}"
  else
    grep -Eq "${pattern}" "${file}"
  fi
}

if [[ ! -f "${SHELL_PAGE}" ]]; then
  echo "[dashboard-v2-query-scope] ERROR: missing file ${SHELL_PAGE}"
  exit 1
fi

PASS=0
FAIL=0

pass() {
  echo "[PASS] $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "[FAIL] $1"
  FAIL=$((FAIL + 1))
}

expect_pattern() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if match_pattern "${pattern}" "${file}"; then
    pass "${label}"
  else
    fail "${label}"
  fi
}

echo "[dashboard-v2-query-scope] validate global/page query scope policy"

expect_pattern "${NAV_MODEL_PAGE}" "GLOBAL_QUERY_KEYS = \\[\"scope\", \"org\", \"team\", \"range\"\\]" "global query keys declared"
expect_pattern "${NAV_MODEL_PAGE}" "overview: \\[\"overview_window\"\\]" "overview page query key declared"
expect_pattern "${NAV_MODEL_PAGE}" "apiKeys: \\[\"keys_status\"\\]" "api-keys page query key declared"
expect_pattern "${NAV_MODEL_PAGE}" "auditEvents: \\[\"audit_status\"\\]" "audit-events page query key declared"
expect_pattern "${NAV_MODEL_PAGE}" "adminOps: \\[\"ops_tab\"\\]" "admin-ops page query key declared"
expect_pattern "${SHELL_PAGE}" "for \\(const key of GLOBAL_QUERY_KEYS\\)" "nav/global update iterates only global keys"
expect_pattern "${SHELL_PAGE}" "const allowed = new Set<string>\\(\\[\\.\\.\\.GLOBAL_QUERY_KEYS, \\.\\.\\.PAGE_QUERY_KEYS\\[pageKey\\]\\]\\)" "allowed set merges global + current page keys"
expect_pattern "${SHELL_PAGE}" "if \\(!allowed\\.has\\(key\\)\\) \\{" "unknown query keys are filtered"
expect_pattern "${SHELL_PAGE}" "params\\.delete\\(key\\);" "unknown/page-irrelevant query keys deleted"
expect_pattern "${NAV_MAIN_PAGE}" "href=\\{buildNavHref\\(item\\.href, item\\.section\\)\\}" "sidebar navigation keeps global query keys"

echo "[dashboard-v2-query-scope] pass=${PASS} fail=${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
echo "[dashboard-v2-query-scope] done"
