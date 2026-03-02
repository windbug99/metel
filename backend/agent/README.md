# Agent Folder Guide

This folder contains the LLM agent runtime contract for metel.

## Tool Spec Source of Truth

- `tool_specs/schema.json`: validation schema for service tool specs
- `tool_specs/notion.json`: Notion executable tool spec
- `tool_specs/spotify.json`: Spotify executable tool spec
- `pipeline_dsl_schema.json`: pipeline DAG DSL v1 schema (planning contract)
- `pipeline_error_codes.py`: pipeline-level error code enum and retryability policy

## Planned Runtime Modules

- `planner.py`: build execution plan from user goal + guide context
- `service_resolver.py`: infer target services from user request
- `guide_retriever.py`: load summarized guide snippets from `docs/api_guides`
- `registry.py`: load/validate tool specs and dispatch adapter functions
- `pipeline_dag.py`: validate/evaluate/execute Pipeline DSL DAG (`when`, `$ref`, `for_each`)
- `loop.py`: tool-calling loop with verification and retry policy
- `safety.py`: hard limits and guardrails
- `observability.py`: step-level logs and request tracing

## Design Rule

LLM must only call tools declared in `tool_specs/*.json`.
Human-readable API guides are references for planning, not direct execution contracts.

## DAG Ops Quickcheck

- Supabase connectivity preflight:
  - `cd backend && . .venv/bin/activate && PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5`
- Agent quality gate (includes preflight):
  - `cd backend && . .venv/bin/activate && ./scripts/run_autonomous_gate.sh`
- Autonomous SLO guard (`fallback<=10%`) for steady-state ops:
  - `cd backend && . .venv/bin/activate && ./scripts/run_autonomous_slo_guard.sh`
- DAG quality gate (includes preflight):
  - `cd backend && . .venv/bin/activate && ./scripts/run_dag_quality_gate.sh`
- Note:
  - Telegram webhook smoke/traffic scripts were removed in the Phase 1 MCP overhaul.
  - Use MCP endpoint smoke checks (`/mcp/list_tools`, `/mcp/call_tool`) instead.

## Autonomous Rollout Runbook (Railway)

- Required Railway env keys:
  - `LLM_AUTONOMOUS_ENABLED`
  - `LLM_AUTONOMOUS_TRAFFIC_PERCENT`
  - `LLM_AUTONOMOUS_SHADOW_MODE`
  - `LLM_HYBRID_EXECUTOR_FIRST`
- Recommended start (shadow-only):
  - `LLM_AUTONOMOUS_ENABLED=true`
  - `LLM_AUTONOMOUS_TRAFFIC_PERCENT=0`
  - `LLM_AUTONOMOUS_SHADOW_MODE=true`
  - `LLM_HYBRID_EXECUTOR_FIRST=true`
- Canary promote target:
  - `10% -> 30% -> 100%`
  - `TRAFFIC_PERCENT >= 10`부터 `LLM_AUTONOMOUS_SHADOW_MODE=false`

- Decision cycle (dry-run):
  - `cd backend && . .venv/bin/activate && CURRENT_PERCENT=0 ./scripts/run_autonomous_rollout_cycle.sh`
  - outputs:
    - `docs/reports/agent_quality_latest.json`
    - `docs/reports/autonomous_rollout_decision_latest.json`
- Decision cycle (apply to env file):
  - `cd backend && . .venv/bin/activate && CURRENT_PERCENT=0 APPLY_DECISION=true ENV_FILE=.env ./scripts/run_autonomous_rollout_cycle.sh`
- Apply decision only:
  - dry-run: `cd backend && . .venv/bin/activate && python scripts/apply_autonomous_rollout_decision.py --from-json ../docs/reports/autonomous_rollout_decision_latest.json --env-file .env`
  - apply: `cd backend && . .venv/bin/activate && python scripts/apply_autonomous_rollout_decision.py --from-json ../docs/reports/autonomous_rollout_decision_latest.json --env-file .env --apply`

- Kill-switch policy (30-minute moving window):
  - `fallback_rate > 20%`
  - `autonomous_success_over_attempt < 75%`
  - `auth_error` ratio surge (`>= 2x` vs previous window)
- Emergency rollback values:
  - `LLM_AUTONOMOUS_ENABLED=false`
  - `LLM_AUTONOMOUS_TRAFFIC_PERCENT=0`
  - `LLM_AUTONOMOUS_SHADOW_MODE=true`
  - `LLM_HYBRID_EXECUTOR_FIRST=true`
