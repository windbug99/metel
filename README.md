# metel

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)](#)
[![Database](https://img.shields.io/badge/database-Supabase-3FCF8E?logo=supabase&logoColor=white)](#)
[![Deploy Backend](https://img.shields.io/badge/deploy-Railway-7B3FE4?logo=railway&logoColor=white)](#)
[![Deploy Frontend](https://img.shields.io/badge/deploy-Vercel-000000?logo=vercel&logoColor=white)](#)
[![Status](https://img.shields.io/badge/status-prototype-orange)](#)

metel is an execution-first AI operations prototype.  
It is designed to turn one natural-language request into multi-step, cross-service actions with verification and logs.

Core position:
- Not just "chat with tools"
- An operational execution layer with guardrails

## Live Product

- Frontend: `https://metel-frontend.vercel.app`
- Backend: `https://metel-production.up.railway.app`

## Why metel

Most automation surfaces are strong at notifications and simple trigger-action flows.  
metel focuses on reliable execution for multi-step requests:

- planner + autonomous executor loop
- verification/fallback telemetry
- mutation safety controls (budget, duplicate block, validation)
- structured run logs for traceability

## How It Works

```text
[User Request]
   |
   v
[Telegram Ingress]
   |
   v
[Planner (LLM + constrained tool specs)]
   |
   v
[Autonomous Executor Loop]
   |-- tool_call --> [Tool Runner: Notion / Linear / Google Calendar]
   |-- verify -----> [Verification Gate]
   |-- replan? ----> [Planner] (if needed)
   |
   v
[Execution Summary + command_logs telemetry]
   |
   v
[Telegram Response]
```

Operationally, metel records:
- `plan_source` (`llm` / `rule`)
- `execution_mode` (`autonomous` / `rule`)
- `autonomous_fallback_reason`
- `verification_reason`
- `llm_provider`, `llm_model`

## What Works Now

Service connection (OAuth / status / disconnect):
- Notion
- Linear
- Google Calendar
- Telegram bot connection flow (deep link + status)

Execution capabilities (implemented):
- Notion search/list/create/update/archive + append content
- Linear search/list/create/update flows
- Linear due-date filtered issue listing (`linear_list_issues` with `due_date`)
- Google Calendar event listing (`google_calendar_list_events`)
- Multi-step request handling with autonomous loop + guardrails
- Execution logs UI in dashboard (`command_logs`)

## Recent Update (2026-02-27)

- Added support for "today due issues" lookup in Linear.
- Requests like `리니어에서 오늘 마감 이슈 조회` now map to `linear_list_issues` with `due_date=<today>`.
- Empty-result message is now intent-aware:
  - `Linear 오늘 마감 이슈 조회 결과가 없습니다.`
  - (instead of generic recent-issues empty message)

## Reliability Model (Current)

Guardrails currently in runtime:
- turn/tool/replan/timeout budgets
- verification gate before completion
- duplicate mutation-call blocking
- rule fallback controls via env flags

Quality gates in repo:
- core regression script
- autonomous gate script
- tool spec validation script

This repository prioritizes execution reliability before adding many new integrations.

## Example Requests

- `Fetch today's meetings from Google Calendar.`
- `Fetch today's meetings from Google Calendar, create a Notion meeting-note draft for each meeting, and create a Linear issue for each one.`
- `Find the latest 5 Linear issues and summarize them in a Notion page.`
- `구글캘린더에서 오늘 회의 일정 조회`
- `구글캘린더에서 오늘 회의일정 조회해서 각 회의마다 노션에 회의록 초안 생성하고 각 회의를 리니어 이슈로 등록해줘`
- `linear 최근 이슈 5개 검색해줘`
- `리니어에서 오늘 마감 이슈 조회해줘`
- `notion 페이지를 생성하고 오늘 작업 요약을 추가해줘`

## Current Limits

- Prototype quality, not production SLA.
- Some external API constraints still apply by provider policy and token state.
- Autonomous success/fallback ratio is still being tuned to reduce rule dependency.
- Complex high-variance tasks may require tighter tool/slot guidance.

## Direction (Execution-First Roadmap)

Near term:
- reduce fallback dependency and raise autonomous success rate
- harden SKILL_THEN_SKILL style multi-step execution
- improve failure transparency (reason clarity + user-facing guidance)
- strengthen all-or-nothing behavior for critical chained writes

Service expansion priority (planned direction, not all implemented):
1. Gmail / Google Workspace
2. Calendar depth
3. Slack as team interface
4. RSS monitoring
5. GitHub-oriented operational workflows

Principle:
- prioritize trust and deterministic behavior over integration count

## Quick Start (Local)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

### Health check

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000/api/health`

## Environment Variables

Use:
- `backend/.env.example`
- `frontend/.env.example`

Key agent/runtime flags:
- `LLM_PLANNER_ENABLED`
- `LLM_PLANNER_PROVIDER`
- `LLM_PLANNER_MODEL`
- `LLM_PLANNER_FALLBACK_PROVIDER`
- `LLM_PLANNER_FALLBACK_MODEL`
- `LLM_AUTONOMOUS_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED`
- `LLM_AUTONOMOUS_PROGRESSIVE_NO_FALLBACK_ENABLED`
- `SKILL_RUNNER_V2_ENABLED`
- `TOOL_SPECS_VALIDATE_ON_STARTUP`

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Recommended regression gates:

```bash
cd backend
./scripts/run_core_regression.sh
./scripts/run_autonomous_gate.sh
```

Tool spec validation:

```bash
cd backend
source .venv/bin/activate
python scripts/check_tool_specs.py --json
```

## Repository Structure

```text
frontend/                  Next.js landing + dashboard
backend/                   FastAPI + agent runtime
backend/agent/             planner / autonomous / registry / tool_runner
backend/agent/tool_specs/  service tool specs (json)
backend/tests/             unit + integration tests
docs/                      plans, release notes, architecture notes
docs/sql/                  schema migration scripts
```

## Related Docs

- `docs/work_plan.md`
- `docs/work-20260223-skill-pipeline-dag-plan.md`
- `docs/release-20260224-google-calendar-pipeline.md`
- `docs/service_plan.md`
