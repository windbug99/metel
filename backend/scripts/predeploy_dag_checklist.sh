#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOC_PATH="${ROOT_DIR}/../docs/work-20260223-skill-pipeline-dag-plan.md"

echo "[predeploy-dag] start"
echo "[predeploy-dag] root=${ROOT_DIR}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[predeploy-dag] 0) preflight supabase connectivity"
PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5

echo "[predeploy-dag] 1) run core regression tests"
PYTHONPATH=. pytest -q \
  tests/test_mcp_routes.py \
  tests/test_api_keys_route.py \
  tests/test_tool_calls_route.py \
  tests/test_tool_runner.py \
  tests/test_registry_extensibility.py

echo "[predeploy-dag] 2) run autonomous quality gate"
"${ROOT_DIR}/scripts/run_autonomous_gate.sh"

cat <<'EOF'
[predeploy-dag] 4) apply DB migrations (manual)
- docs/sql/015_create_api_keys_and_tool_calls_tables.sql
- docs/sql/016_add_api_keys_allowed_tools.sql
- docs/sql/011_add_oauth_tokens_granted_scopes.sql

[predeploy-dag] 5) oauth granted_scopes backfill (manual)
- Dry-run:
  cd backend && . .venv/bin/activate && PYTHONPATH=. \
    python scripts/backfill_oauth_granted_scopes.py --limit 1000
- Apply:
  cd backend && . .venv/bin/activate && PYTHONPATH=. \
    python scripts/backfill_oauth_granted_scopes.py --apply --limit 1000

[predeploy-dag] 6) staging smoke scenario (manual)
- Run: MCP `list_tools`, `call_tool` smoke request
- Verify:
  1) `list_tools` returns connected notion/linear tools
  2) `call_tool` succeeds and logs to `tool_calls`
  3) `tool_calls` dashboard/API reflects recent call

[predeploy-dag] checklist source:
- ${DOC_PATH}
EOF

echo "[predeploy-dag] done"
