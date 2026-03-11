# Metel.ai

Control layer between AI agents and SaaS APIs.
Policy, audit, and risk gate on every tool call — so your agents
can execute Notion, Linear, and GitHub actions safely.

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)](#)
[![Database](https://img.shields.io/badge/database-Supabase-3FCF8E?logo=supabase&logoColor=white)](#)
[![Deploy Backend](https://img.shields.io/badge/deploy-Railway-7B3FE4?logo=railway&logoColor=white)](#)
[![Deploy Frontend](https://img.shields.io/badge/deploy-Vercel-000000?logo=vercel&logoColor=white)](#)
[![Live](https://img.shields.io/badge/live-metel--frontend.vercel.app-blue)](https://metel-frontend.vercel.app)

```text
AI Agents (Claude / GPT / CrewAI / Custom)
            ↓
      MCP Gateway            ← list_tools / call_tool
            ↓
  Execution Control Core     ← policy · risk · audit · RBAC
            ↓
      SaaS APIs              ← Notion / Linear / GitHub
```

## Quick Start

### HTTP (any agent)

```bash
# 1. Get an API key from the dashboard
#    https://metel-frontend.vercel.app → API Keys → Create

# 2. Set env
export API_BASE_URL="https://metel-production.up.railway.app"
export MCP_API_KEY="mcp_live_xxx"

# 3. List available tools
curl -sS -X POST "$API_BASE_URL/mcp/list_tools" \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"list_tools","params":{}}'

# 4. Call a tool (example: Notion search)
curl -sS -X POST "$API_BASE_URL/mcp/call_tool" \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"call_tool",
       "params":{"name":"notion_search","arguments":{"query":"roadmap"}}}'
```

### Claude Desktop

1. Run **Claude Desktop**.
2. Go to **Settings** > **Developer** > **Edit Config**.
3. Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "metel": {
      "command": "node",
      "args": ["path/to/metel-bridge/index.js"],
      "env": {
        "METEL_API_KEY": "mcp_live_xxx",
        "METEL_BASE_URL": "https://metel-production.up.railway.app"
      }
    }
  }
}
```

4. After adding `mcpServers`, verify that **Metel** is listed in **Settings** > **Connectors**.


### Local development

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

Health check: `http://localhost:3000` · `http://localhost:8000/api/health`

## Supported Tools

### Notion — 30 tools

| Category | Read | Write |
|----------|------|-------|
| Search | `notion_search` | — |
| Users | `retrieve_user`, `list_users`, `retrieve_bot_user` | — |
| Pages | `retrieve_page`, `retrieve_page_property_item` | `create_page`, `update_page` |
| Blocks | `retrieve_block`, `retrieve_block_children` | `update_block`, `delete_block`, `append_block_children` |
| Comments | `list_comments`, `retrieve_comment` | `create_comment` |
| Data Sources | `query_data_source`, `retrieve_data_source`, `list_data_source_templates` | `create_data_source`, `update_data_source` |
| Databases | `retrieve_database`, `query_database` | `create_database`, `update_database` |
| File Uploads | `retrieve_file_upload`, `list_file_uploads` | `create_file_upload`, `send_file_upload`, `complete_file_upload` |

### Linear — 8 tools

| Category | Read | Write |
|----------|------|-------|
| Viewer | `get_viewer` | — |
| Issues | `list_issues`, `search_issues` | `create_issue`, `update_issue` |
| Teams | `list_teams` | — |
| Workflow | `list_workflow_states` | — |
| Comments | — | `create_comment` |

### GitHub — 5 tools

| Category | Read | Write |
|----------|------|-------|
| User | `get_me` | — |
| Repositories | `list_repos` | — |
| Issues | `list_issues` | `create_issue` |
| Comments | — | `create_issue_comment` |

Tool schemas: `backend/agent/tool_specs/*.json` or call `POST /mcp/list_tools`.

## Execution Control

Every `call_tool` request passes through:

| Layer | What it does |
|-------|-------------|
| **Auth** | API key validation with scoped tool permissions |
| **Schema** | JSON Schema check on every tool input |
| **Policy** | Allow/deny rules by key, team, and tool (merge-based) |
| **Risk Gate** | Blocks destructive ops (delete, archive) by default |
| **Resolver** | Converts human-readable names to system IDs |
| **Retry & Quota** | Per-key rate limits with backoff and dead-letter alerting |
| **Audit** | Every call logged with actor, decision, latency, error |
| **RBAC** | Organization roles: `owner` · `admin` · `member` |

## Dashboard

Web dashboard at [metel-frontend.vercel.app](https://metel-frontend.vercel.app)
with role-based menu visibility (`owner` / `admin` / `member`).

- **Organization** — members, invites, audit settings, OAuth governance, webhooks
- **Team** — usage analytics, team policy, policy simulator, API keys
- **User** — profile, security, OAuth connections, requests

> Setup guide: [`docs/user-guide-initial-setup-and-menu-settings-20260309.md`](docs/user-guide-initial-setup-and-menu-settings-20260309.md)

## API Reference

### MCP

| Endpoint | Description |
|----------|-------------|
| `POST /mcp/list_tools` | List available tools (filtered by connected services) |
| `POST /mcp/call_tool` | Execute a tool with policy and schema enforcement |

### Management

| Endpoint | Description |
|----------|-------------|
| `/api/api-keys` | Create, update, rotate, revoke API keys |
| `/api/organizations/*` | Org membership, invites, role requests |
| `/api/teams/*` | Team policy, revision, rollback |
| `/api/policies/simulate` | Test policy outcomes before rollout |
| `/api/audit/*` | Audit events, detail, export, settings |
| `/api/tool-calls/*` | Usage overview, trends, failure breakdown |
| `/api/integrations/*` | Webhook subscriptions, deliveries, retry |
| `/api/admin/*` | System health, diagnostics, incident banner |
| `/api/me/permissions` | Current role, scopes, capabilities |

### Error Codes

| Code | Meaning |
|------|---------|
| `missing_required_field` | Required input field missing |
| `invalid_field_type` | Field type mismatch |
| `rate_limit_exceeded` | Per-key rate limit hit |
| `tool_not_found` | Unknown tool name |
| `oauth_required` | OAuth connection not found for service |
| `policy_denied` | Blocked by key/team policy |
| `risk_blocked` | Destructive operation blocked by risk gate |
| `access_denied` | RBAC permission denied |
| `scope_mismatch` | Scope does not match |
| `insufficient_role` | Role lacks required capability |

## Architecture

```text
[AI Agent / Client]
   |
   v
[MCP Gateway Layer]
   |
   v
[Execution Control Core]
   |-- API Key Auth + RBAC (owner/admin/member)
   |-- Tool Registry + Schema Validation
   |-- Team/Key Policy Merge + Risk Gate
   |-- Resolver + Retry/Backoff + Quota
   |-- Audit Log + Usage Analytics
   |-- Integrations (Webhook/Export/Dead-letter Alert)
   |-- Admin/Ops Diagnostics + Incident Banner
   |
   v
[SaaS APIs: Notion / Linear / GitHub]
```

Runtime guardrails:
- API key auth + organization RBAC + role-scoped data filtering
- tool/service allowlist + deny policy by key/team
- schema validation + resolver pipeline + risk gate
- per-key quota/rate limit + retry/backoff + dead-letter alerting
- structured execution/audit logging

## Development

### Environment variables

See `backend/.env.example` and `frontend/.env.example`.

Key flags: `RBAC_READ_GUARD_ENABLED`, `RBAC_WRITE_GUARD_ENABLED`,
`UI_RBAC_STRICT_ENABLED`, `TOOL_SPECS_VALIDATE_ON_STARTUP`.

### Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest -q                                       # unit tests
./scripts/run_phase3_regression.sh                        # regression gate
./scripts/run_phase3_rbac_smoke.sh                        # RBAC smoke
MODE=full_guard ./scripts/run_rbac_rollout_stage_gate.sh  # rollout gate
./scripts/run_rbac_monitoring_snapshot.sh                  # monitoring
./scripts/run_dashboard_v2_qa_stage_gate.sh               # dashboard QA
python scripts/check_tool_specs.py --json                 # tool spec validation
```

### Repository structure

```text
frontend/                  Next.js landing + dashboard (V2 route-based)
backend/                   FastAPI + MCP/control routes
backend/app/core/          authz (RBAC), config, state
backend/agent/             registry / tool_runner / tool specs
backend/agent/tool_specs/  service tool specs (json)
backend/tests/             unit + integration tests (RBAC/route/IDOR)
backend/scripts/           regression, rollout, monitoring scripts
docs/                      plans, release notes, architecture notes
docs/sql/                  schema migration scripts
docs/sql/legacy/           archived (non-baseline) migrations
```

## Roadmap

Current status:
- RBAC `full_guard` active in production (48h monitoring complete)
- Provider-side constraints apply (OAuth scopes, upstream API limits, token status)

Next:
- SIEM/ticket template standardization (Jira/Linear mapping)
- Enterprise approval workflows (dual-approval, escalation)
- Deeper Notion/Linear coverage
- Policy DSL, SSO/SAML, SOC2 process, usage-based billing

Principle: prioritize trust and deterministic behavior over integration count.

## Docs

- [`docs/overhaul-20260302.md`](docs/overhaul-20260302.md) — source-of-truth plan
- [`docs/user-guide-initial-setup-and-menu-settings-20260309.md`](docs/user-guide-initial-setup-and-menu-settings-20260309.md) — user guide
- [`docs/dashboard-menu-structure-improvement-plan-20260307.md`](docs/dashboard-menu-structure-improvement-plan-20260307.md) — dashboard menu structure
- [`docs/dashboard-ia-navigation-proposal-20260305.md`](docs/dashboard-ia-navigation-proposal-20260305.md) — dashboard IA/routing
- [`docs/dashboard-design-system-draft-20260305.md`](docs/dashboard-design-system-draft-20260305.md) — design system tokens
- [`docs/rbac-production-monitoring-log-20260305.md`](docs/rbac-production-monitoring-log-20260305.md) — RBAC monitoring log
- [`docs/rbac-production-rollout-runbook-20260304.md`](docs/rbac-production-rollout-runbook-20260304.md) — RBAC rollout runbook
- [`docs/rbac-dashboard-e2e-smoke-checklist-20260304.md`](docs/rbac-dashboard-e2e-smoke-checklist-20260304.md) — RBAC e2e smoke
- [`docs/phase3-gap-closing-backlog-20260303.md`](docs/phase3-gap-closing-backlog-20260303.md) — phase3 gap closing
- [`docs/mcp_smoke_test_checklist.md`](docs/mcp_smoke_test_checklist.md) — deploy smoke test
- [`docs/sql/legacy/README.md`](docs/sql/legacy/README.md) — migration policy
