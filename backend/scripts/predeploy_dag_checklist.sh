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

echo "[predeploy-dag] 1) run DAG/core regression tests"
PYTHONPATH=. pytest -q \
  tests/test_pipeline_dag.py \
  tests/test_pipeline_dag_adapter.py \
  tests/test_pipeline_fixture_e2e.py \
  tests/test_pipeline_links.py \
  tests/test_pipeline_links_route.py \
  tests/test_eval_dag_quality.py \
  tests/test_apply_policy_recommendations.py

echo "[predeploy-dag] 2) run autonomous quality gate"
"${ROOT_DIR}/scripts/run_autonomous_gate.sh"

echo "[predeploy-dag] 3) run DAG quality gate"
"${ROOT_DIR}/scripts/run_dag_quality_gate.sh"

cat <<'EOF'
[predeploy-dag] 4) apply DB migrations (manual)
- docs/sql/009_create_pipeline_links_table.sql
- docs/sql/010_add_pipeline_links_error_columns.sql
- docs/sql/011_add_oauth_tokens_granted_scopes.sql

[predeploy-dag] 5) oauth granted_scopes backfill (manual)
- Dry-run:
  cd backend && . .venv/bin/activate && PYTHONPATH=. \
    python scripts/backfill_oauth_granted_scopes.py --limit 1000
- Apply:
  cd backend && . .venv/bin/activate && PYTHONPATH=. \
    python scripts/backfill_oauth_granted_scopes.py --apply --limit 1000

[predeploy-dag] 6) staging smoke scenario (manual)
- Run: "구글캘린더 오늘 회의를 notion 페이지로 만들고 linear 이슈로 등록해줘"
- Verify:
  1) command_logs.detail contains dag_pipeline=1 and pipeline_run_id
  2) pipeline_links row is created with status=succeeded
  3) dag_quality_latest.json is generated and PASS
- Optional auto-check:
  cd backend && . .venv/bin/activate && PYTHONPATH=. \
    python scripts/check_dag_smoke_result.py --limit 100

[predeploy-dag] checklist source:
- ${DOC_PATH}
EOF

echo "[predeploy-dag] done"
