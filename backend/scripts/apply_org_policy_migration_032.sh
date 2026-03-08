#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION_FILE="${MIGRATION_FILE:-${ROOT_DIR}/docs/sql/032_create_org_policy_tables.sql}"
DB_URL="${STAGING_DB_URL:-${DATABASE_URL:-}}"
HOMEBREW_LIBPQ_BIN="/opt/homebrew/opt/libpq/bin"

if [[ -z "${DB_URL}" ]]; then
  echo "[org-policy-migration] ERROR: STAGING_DB_URL (or DATABASE_URL) is required"
  exit 1
fi

if [[ ! -f "${MIGRATION_FILE}" ]]; then
  echo "[org-policy-migration] ERROR: migration file not found: ${MIGRATION_FILE}"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  if [[ -x "${HOMEBREW_LIBPQ_BIN}/psql" ]]; then
    export PATH="${HOMEBREW_LIBPQ_BIN}:${PATH}"
  fi
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "[org-policy-migration] ERROR: psql is required"
  echo "[org-policy-migration] hint: brew install libpq && export PATH=\"/opt/homebrew/opt/libpq/bin:\$PATH\""
  exit 1
fi

echo "[org-policy-migration] applying ${MIGRATION_FILE}"
psql "${DB_URL}" -v ON_ERROR_STOP=1 -f "${MIGRATION_FILE}"

echo "[org-policy-migration] verifying tables and RLS policies"
psql "${DB_URL}" -v ON_ERROR_STOP=1 <<'SQL'
\pset tuples_only on
\pset format unaligned

select coalesce(to_regclass('public.org_policies')::text, '');
select coalesce(to_regclass('public.org_oauth_policies')::text, '');

select count(*) from pg_policies
where schemaname = 'public'
  and tablename = 'org_policies'
  and policyname in ('org_policies_select_org_member', 'org_policies_upsert_org_owner');

select count(*) from pg_policies
where schemaname = 'public'
  and tablename = 'org_oauth_policies'
  and policyname in ('org_oauth_policies_select_org_member', 'org_oauth_policies_upsert_org_owner');
SQL

echo "[org-policy-migration] done"
