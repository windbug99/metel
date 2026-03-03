# Claude Desktop MCP Connection Guide

This project currently exposes MCP features through HTTP JSON-RPC endpoints:
- `POST /mcp/list_tools`
- `POST /mcp/call_tool`

Claude Desktop expects an MCP server process, so use the included stdio bridge:
- `backend/scripts/mcp_stdio_bridge.py`

## 1) Prerequisites

- Python environment with backend dependencies installed
- A valid `metel_...` API key
- Backend URL (production/staging/local)

## 2) Verify Bridge Locally

```bash
cd backend
API_BASE_URL="https://metel-production.up.railway.app" \
API_KEY="metel_xxx" \
python scripts/mcp_stdio_bridge.py
```

Then send a JSON-RPC line manually:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
```

You should receive a JSON response line with `result.protocolVersion`.

Automated quick check (recommended):

```bash
cd backend
API_BASE_URL="https://metel-production.up.railway.app" \
API_KEY="metel_xxx" \
python scripts/check_claude_bridge_tools.py
```

Expected:
- `OK tools_count=N` (N >= 1)

## 3) Claude Desktop config

Add an MCP server entry in `claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "metel": {
      "command": "python",
      "args": ["/Users/tomato/cursor/metel/backend/scripts/mcp_stdio_bridge.py"],
      "env": {
        "API_BASE_URL": "https://metel-production.up.railway.app",
        "API_KEY": "metel_xxx",
        "BRIDGE_DEBUG": "1"
      }
    }
  }
}
```

## 4) Expected behavior in Claude Desktop

- Tool list should include Notion/Linear tools allowed by your API key.
- Tool calls should route through existing backend `/mcp/*`.
- Errors are returned as MCP tool call failures with structured text payload.

## 5) Troubleshooting

- No tools shown:
  - Check OAuth connection status in dashboard (Notion/Linear).
  - Check API key validity and `allowed_tools`.
  - Run `python scripts/check_claude_bridge_tools.py` first.
- Bridge exits immediately:
  - Ensure `API_BASE_URL` and `API_KEY` are set.
- Tool call fails:
  - Test backend directly with `curl` to isolate bridge vs backend issue.

## 6) Security note

- Never reuse API keys that were exposed in logs/chats.
- Revoke test keys after validation.
