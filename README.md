# metel

> Current baseline (2026-03-02):
> metel is currently evolving as an **MCP Gateway + Safe Execution Core**.
> The source-of-truth plan is `docs/overhaul-20260302.md`.
> Legacy Telegram/agent documents are retained for history and are marked with `Legacy notice`.

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)](#)
[![Database](https://img.shields.io/badge/database-Supabase-3FCF8E?logo=supabase&logoColor=white)](#)
[![Deploy Backend](https://img.shields.io/badge/deploy-Railway-7B3FE4?logo=railway&logoColor=white)](#)
[![Deploy Frontend](https://img.shields.io/badge/deploy-Vercel-000000?logo=vercel&logoColor=white)](#)
[![Status](https://img.shields.io/badge/status-prototype-orange)](#)

metel is an execution-first AI operations prototype.
It is currently focused on a controlled MCP execution path for SaaS tools.

Core position:
- Not just "chat with tools"
- An operational execution layer with guardrails

## Live Product

- Frontend: `https://metel-frontend.vercel.app`
- Backend: `https://metel-production.up.railway.app`

## Why metel

Most automation surfaces are strong at notifications and simple trigger-action flows.  
metel focuses on reliable execution for multi-step requests:

- controlled MCP tool execution
- structured policy/error handling
- mutation safety controls (schema, allowlist, rate limit)
- structured run logs for traceability

## How It Works (Current Baseline)

```text
[AI Agent / Client]
   |
   v
[MCP Gateway Layer]
   |
   v
[Execution Control Core]
   |-- API Key Auth
   |-- Tool Registry
   |-- Schema Validation
   |-- Rate Limit / Quota
   |-- Usage Logging (tool_calls)
   |
   v
[SaaS APIs: Notion / Linear]
```

Operationally, metel records:
- API key metadata (`api_keys`)
- execution logs (`tool_calls`)
- structured JSON-RPC error codes

## What Works Now

Service connection (OAuth / status / disconnect):
- Notion
- Linear
- Google Calendar

MCP and control features (implemented):
- `POST /mcp/list_tools`
- `POST /mcp/call_tool`
- API key issue/revoke/update (`/api/api-keys`)
- API key scoped tool allowlist (`allowed_tools`)
- rate limit + structured error responses
- usage logs API + dashboard section (`/api/tool-calls`)

## Reliability Model (Current)

Guardrails currently in runtime:
- API key authentication
- tool allowlist enforcement by key
- schema-based input validation
- per-key rate limiting
- structured execution logging (`tool_calls`)

Quality gates in repo:
- core regression script (`backend/scripts/run_core_regression.sh`)
- MCP/API key/tool-calls unit tests
- tool spec validation script (`backend/scripts/check_tool_specs.py`)

This repository prioritizes execution reliability before adding many new integrations.

## Example MCP Requests

- `list_tools` with API key
- `call_tool` for `notion_search`
- `call_tool` for `linear_list_issues`

## Current Limits

- Prototype quality, not production SLA.
- Some external API constraints still apply by provider policy and token state.
- Policy/risk controls are still expanding in Phase 2+.
- Enterprise features (approval flow, RBAC, billing) are not yet complete.

## Direction (Execution-First Roadmap)

Near term:
- complete Phase 1 MCP baseline hardening
- ship safe execution controls (Phase 2)
- expand policy/risk controls for enterprise path

Service expansion priority (planned direction, not all implemented):
1. deeper Notion/Linear coverage
2. policy and risk controls
3. enterprise auth/governance features

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

Key runtime flags:
- `TOOL_SPECS_VALIDATE_ON_STARTUP`
- OAuth provider envs (Notion / Linear / Google)
- Supabase service credentials

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
backend/                   FastAPI + MCP/control routes
backend/agent/             registry / tool_runner / tool specs
backend/agent/tool_specs/  service tool specs (json)
backend/tests/             unit + integration tests
docs/                      plans, release notes, architecture notes
docs/sql/                  schema migration scripts
docs/sql/legacy/           archived (non-baseline) migrations
```

## Related Docs

- `docs/overhaul-20260302.md` (source-of-truth)
- `docs/sql/legacy/README.md` (migration policy)
- `docs/work_plan.md` (legacy)
- `docs/service_plan.md` (legacy)
