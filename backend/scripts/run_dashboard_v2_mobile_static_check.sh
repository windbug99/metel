#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHELL_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/shell.tsx"
SITE_HEADER_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/sidebar07/site-header.tsx"
APP_SIDEBAR_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/app-sidebar.tsx"
NAV_MAIN_PAGE="${ROOT_DIR}/frontend/components/dashboard-v2/sidebar07/nav-main.tsx"
API_KEYS_PAGE="${ROOT_DIR}/frontend/app/dashboard/(v2)/access/api-keys/page.tsx"
AUDIT_PAGE="${ROOT_DIR}/frontend/app/dashboard/(v2)/control/audit-events/page.tsx"
ADMIN_OPS_PAGE="${ROOT_DIR}/frontend/app/dashboard/(v2)/admin/ops/page.tsx"

for f in "${SHELL_PAGE}" "${SITE_HEADER_PAGE}" "${APP_SIDEBAR_PAGE}" "${NAV_MAIN_PAGE}" "${API_KEYS_PAGE}" "${AUDIT_PAGE}" "${ADMIN_OPS_PAGE}"; do
  if [[ ! -f "${f}" ]]; then
    echo "[dashboard-v2-mobile-static] ERROR: missing file ${f}"
    exit 1
  fi
done

PASS=0
FAIL=0

match_pattern() {
  local pattern="$1"
  local file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "${pattern}" "${file}"
  else
    grep -Eq "${pattern}" "${file}"
  fi
}

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

echo "[dashboard-v2-mobile-static] validate responsive + touch-target guardrails"

expect_pattern "${SHELL_PAGE}" "md:hidden" "mobile overlay/backdrop exists"
expect_pattern "${SHELL_PAGE}" "fixed inset-0 z-30 bg-black\\/50" "mobile overlay style exists"
expect_pattern "${SITE_HEADER_PAGE}" "onToggleSidebar" "header has sidebar toggle handler"
expect_pattern "${SITE_HEADER_PAGE}" "PanelLeft" "header sidebar toggle icon exists"
expect_pattern "${APP_SIDEBAR_PAGE}" "md:hidden" "sidebar close button visible on mobile only"
expect_pattern "${APP_SIDEBAR_PAGE}" "translate-x-0\" : \"-translate-x-full" "sidebar slide-in mobile transition exists"
expect_pattern "${NAV_MAIN_PAGE}" "px-3 py-2" "navigation links provide touch-friendly vertical padding"

expect_pattern "${API_KEYS_PAGE}" "overflow-x-auto" "api keys table allows horizontal scroll on mobile"
expect_pattern "${API_KEYS_PAGE}" "min-w-\\[640px\\]" "api keys table keeps minimum width for readable columns"
expect_pattern "${AUDIT_PAGE}" "overflow-x-auto" "audit table allows horizontal scroll on mobile"
expect_pattern "${AUDIT_PAGE}" "min-w-\\[640px\\]" "audit table keeps minimum width for readable columns"

expect_pattern "${AUDIT_PAGE}" "h-11" "audit owner-only action has mobile touch target"
expect_pattern "${ADMIN_OPS_PAGE}" "h-11" "admin/ops owner-only action has mobile touch target"

echo "[dashboard-v2-mobile-static] pass=${PASS} fail=${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
echo "[dashboard-v2-mobile-static] done"
