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
- DAG quality gate (includes preflight):
  - `cd backend && . .venv/bin/activate && ./scripts/run_dag_quality_gate.sh`
- DAG smoke/gate cycle loop (retries until pass or attempts exhausted):
  - `cd backend && . .venv/bin/activate && ATTEMPTS=8 SLEEP_SEC=15 ./scripts/run_dag_smoke_cycle.sh`
- DAG smoke/gate cycle loop with auto webhook injection (no manual Telegram send):
  - `cd backend && . .venv/bin/activate && AUTO_INJECT_WEBHOOK=1 WEBHOOK_URL=https://<backend>/api/telegram/webhook CHAT_ID=<telegram_chat_id> ATTEMPTS=8 SLEEP_SEC=15 ./scripts/run_dag_smoke_cycle.sh`
