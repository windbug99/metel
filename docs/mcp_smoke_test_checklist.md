# MCP Smoke Test Checklist

Last verified: 2026-03-02

## 0) Variables

```bash
export API_BASE_URL="https://metel-production.up.railway.app"
export API_KEY="metel_xxx"
```

## 0.1) Automated smoke (recommended)

```bash
cd backend
API_BASE_URL="$API_BASE_URL" API_KEY="$API_KEY" ./scripts/run_mcp_smoke.sh
```

Optional rate limit check:

```bash
cd backend
API_BASE_URL="$API_BASE_URL" API_KEY="$API_KEY" RUN_RATE_LIMIT_TEST=1 RATE_LIMIT_CALLS=40 ./scripts/run_mcp_smoke.sh
```

Expected:
- exit code `0` when all checks pass
- non-zero exit code if any check fails

## 1) list_tools

```bash
curl -s -X POST "$API_BASE_URL/mcp/list_tools" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"list_tools"}'
```

Expected:
- HTTP 200
- `result.tools` exists
- `notion_*`, `linear_*` tools are visible

## 2) Notion call_tool

```bash
curl -s -X POST "$API_BASE_URL/mcp/call_tool" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"call_tool","params":{"name":"notion_retrieve_bot_user","arguments":{}}}'
```

Expected:
- HTTP 200
- `result.ok=true`

## 3) Linear call_tool

```bash
curl -s -X POST "$API_BASE_URL/mcp/call_tool" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"call_tool","params":{"name":"linear_get_viewer","arguments":{}}}'
```

Expected:
- HTTP 200
- `result.ok=true`

## 4) Structured schema error

```bash
curl -s -X POST "$API_BASE_URL/mcp/call_tool" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"8","method":"call_tool","params":{"name":"linear_search_issues","arguments":{}}}'
```

Expected:
- `error.code=4001`
- `error.message=missing_required_field`
- `error.data.field=query`

## 5) Rate limit

```bash
count=0
for i in $(seq 1 40); do
  res=$(curl -s -X POST "${API_BASE_URL}/mcp/call_tool" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":"rl","method":"call_tool","params":{"name":"linear_search_issues","arguments":{}}}')
  echo "$res" | grep -q "rate_limit_exceeded" && count=$((count+1))
done
echo "rate_limit_exceeded_count=$count"
```

Expected:
- `rate_limit_exceeded_count >= 1`

## 6) Usage log verification

Supabase SQL Editor:

```sql
select tool_name, status, error_code, latency_ms, created_at
from public.tool_calls
order by created_at desc
limit 30;
```

Expected:
- success and fail rows both visible
- `missing_required_field` / `rate_limit_exceeded` visible when tested

## 7) Security cleanup

- Revoke all exposed/temporary test API keys after verification.
