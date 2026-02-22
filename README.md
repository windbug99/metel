# metel

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)](#)
[![Database](https://img.shields.io/badge/database-Supabase-3FCF8E?logo=supabase&logoColor=white)](#)
[![Deploy Backend](https://img.shields.io/badge/deploy-Railway-7B3FE4?logo=railway&logoColor=white)](#)
[![Deploy Frontend](https://img.shields.io/badge/deploy-Vercel-000000?logo=vercel&logoColor=white)](#)
[![Status](https://img.shields.io/badge/status-prototype-orange)](#)

AI-native operations assistant prototype.  
Users connect services once on the web dashboard, then request tasks in Telegram.  
`metel` plans, executes, verifies, and returns results with execution traces.

## Live Product

- Frontend: `https://metel-frontend.vercel.app`
- Backend: `https://metel-production.up.railway.app`

## What Works Now

- Notion OAuth connect/disconnect/status
- Linear OAuth connect/disconnect/status
- Telegram connect/disconnect/status + deep link flow
- Natural language task execution on Notion:
  - search/list pages
  - create/update/archive (with safety handling)
  - append content blocks
  - summarize selected page contents
- Agent telemetry in `command_logs`:
  - `plan_source`, `execution_mode`, `autonomous_fallback_reason`
  - `verification_reason`, `llm_provider`, `llm_model`
- Autonomous runtime guardrails:
  - turn/tool/replan/timeout budgets
  - completion verification gate
  - duplicate mutation call block
  - progressive no-fallback option

## Core Flow

```text
Telegram User Request
  -> LLM Planner
  -> Autonomous Executor Loop (tool_call / verify / replan)
  -> Notion Tool Runner (API)
  -> Execution Summary + Logs
  -> Telegram Response
```

## Demo Requests (Copy/Paste)

Use these in Telegram after connecting Notion:

1. `Notion에서 최근 생성된 페이지 3개를 요약해서 "Daily Briefing Test" 페이지로 만들어줘`
2. `Notion에서 "더 코어 3", "사이먼 블로그" 페이지의 핵심 주제 3문장으로 정리해서 각각 페이지에 추가해줘`
3. `Notion에서 "Daily Briefing Test" 페이지에 "Action Item: API test done" 추가해줘`
4. `Notion에서 "Daily Briefing Test" 페이지를 삭제해줘`

## Known Limits (Current Prototype)

- Some Notion pages at workspace root may not support archive/delete via API depending on page type and ownership.
- Complex cross-domain tasks (e.g. external URL crawling + summarize + write) are partially implemented and still being hardened.
- Autonomous mode still requires fallback-rate reduction for full production reliability.

## Quick Start (Local)

### 1) Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### 3) Check

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`

## Environment Variables

Set required keys from:

- `backend/.env.example`
- `frontend/.env.example`

Important agent flags:

- `LLM_PLANNER_ENABLED`
- `LLM_PLANNER_PROVIDER`
- `LLM_PLANNER_MODEL`
- `LLM_PLANNER_FALLBACK_PROVIDER`
- `LLM_PLANNER_FALLBACK_MODEL`
- `LLM_AUTONOMOUS_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED`
- `LLM_AUTONOMOUS_PROGRESSIVE_NO_FALLBACK_ENABLED`
- `TOOL_SPECS_VALIDATE_ON_STARTUP`

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Core regression gate (recommended):

```bash
cd backend
./scripts/run_core_regression.sh
```

Note:
- `tests/test_agent_executor_e2e.py` is kept as a legacy suite and skipped by default.
- Current primary quality gate is the common-orchestration regression set above.

Tool spec validation:

```bash
cd backend
source .venv/bin/activate
python scripts/check_tool_specs.py --json
```

Autonomous quality gate:

```bash
cd backend
./scripts/run_autonomous_gate.sh
```

Auto-apply policy recommendations (dry-run by default):

```bash
cd backend
python scripts/apply_agent_policy_recommendations.py \
  --from-json ../docs/reports/agent_quality_latest.json

# apply
python scripts/apply_agent_policy_recommendations.py \
  --from-json ../docs/reports/agent_quality_latest.json \
  --apply
```

## Repository Structure

```text
frontend/                  Next.js dashboard
backend/                   FastAPI + agent runtime
backend/agent/             planner / autonomous / registry / tool_runner
backend/agent/tool_specs/  service tool specs (json)
backend/tests/             unit + integration tests
docs/                      plan, architecture, setup, SQL migrations
docs/sql/                  schema migration scripts
```

## Execution-Focused Roadmap

- [x] End-to-end Notion + Telegram prototype
- [x] LLM planner + autonomous execution loop
- [x] command-level telemetry and verification reasons
- [ ] Reduce rule fallback dependency (raise autonomous success rate)
- [ ] Expand Notion endpoint coverage + improve planner tool selection
- [ ] Cross-service workflow execution (Notion + external sources)
- [ ] Workflow mining -> reusable skill candidates
- [ ] Production hardening (rate limit, retries, alerting, runbook)

## Docs

- `docs/work_plan.md` - implementation priorities and current progress
- `docs/service_plan.md` - product direction and architecture
- `docs/openclaw_analysis.md` - positioning and comparative analysis
- `docs/setup_guild.md` - setup guide

---

Promethium internal prototype.
