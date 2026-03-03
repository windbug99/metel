#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" ]]; then
  echo "[mcp-smoke] ERROR: API_BASE_URL is required"
  exit 1
fi
if [[ -z "${API_KEY:-}" ]]; then
  echo "[mcp-smoke] ERROR: API_KEY is required"
  exit 1
fi

RUN_RATE_LIMIT_TEST="${RUN_RATE_LIMIT_TEST:-0}"
RATE_LIMIT_CALLS="${RATE_LIMIT_CALLS:-40}"
MCP_BASE_URL="${API_BASE_URL%/}"
if [[ "${MCP_BASE_URL}" != */mcp ]]; then
  MCP_BASE_URL="${MCP_BASE_URL}/mcp"
fi

pass_count=0
fail_count=0

json_get() {
  local json="$1"
  local expr="$2"
  python3 - "$json" "$expr" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expr = sys.argv[2]

cur = payload
for token in expr.split("."):
    if token == "":
        continue
    if isinstance(cur, dict):
        cur = cur.get(token)
    else:
        cur = None
        break
if isinstance(cur, (dict, list)):
    print(json.dumps(cur))
elif cur is None:
    print("")
else:
    print(str(cur))
PY
}

rpc_call() {
  local path="$1"
  local payload="$2"
  curl -sS -X POST "${MCP_BASE_URL}/${path}" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

assert_eq() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    echo "[PASS] ${label}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] ${label}: expected='${expected}' actual='${actual}'"
    fail_count=$((fail_count + 1))
  fi
}

assert_non_empty() {
  local actual="$1"
  local label="$2"
  if [[ -n "${actual}" && "${actual}" != "[]" && "${actual}" != "null" ]]; then
    echo "[PASS] ${label}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] ${label}: value is empty"
    fail_count=$((fail_count + 1))
  fi
}

assert_valid_api_key_or_exit() {
  local response_body="$1"
  local context="$2"
  local err_message
  err_message="$(json_get "${response_body}" "error.message")"
  case "${err_message}" in
    missing_api_key|invalid_api_key_format|invalid_api_key|api_key_revoked)
      echo "[mcp-smoke] AUTH ERROR during ${context}: ${err_message}"
      echo "[mcp-smoke] response=${response_body}"
      cat <<'EOF'
[mcp-smoke] hint:
- Use an API key issued from the same environment (production key for production URL).
- Check `Authorization: Bearer metel_xxx` format (no quotes/newlines/spaces).
- If key was exposed earlier, revoke and reissue from `/api/api-keys`.
EOF
      exit 2
      ;;
    *)
      ;;
  esac
}

echo "[mcp-smoke] API_BASE_URL=${API_BASE_URL}"
echo "[mcp-smoke] MCP_BASE_URL=${MCP_BASE_URL}"
echo "[mcp-smoke] RUN_RATE_LIMIT_TEST=${RUN_RATE_LIMIT_TEST}"

echo "[mcp-smoke] 1) list_tools"
LIST_TOOLS_BODY="$(rpc_call "list_tools" '{"jsonrpc":"2.0","id":"1","method":"list_tools"}')"
assert_valid_api_key_or_exit "${LIST_TOOLS_BODY}" "list_tools"
assert_non_empty "$(json_get "${LIST_TOOLS_BODY}" "result.tools")" "list_tools.result.tools exists"

echo "[mcp-smoke] 2) notion_retrieve_bot_user"
NOTION_BODY="$(rpc_call "call_tool" '{"jsonrpc":"2.0","id":"2","method":"call_tool","params":{"name":"notion_retrieve_bot_user","arguments":{}}}')"
assert_eq "$(json_get "${NOTION_BODY}" "result.ok")" "True" "notion_retrieve_bot_user result.ok"

echo "[mcp-smoke] 3) linear_get_viewer"
LINEAR_BODY="$(rpc_call "call_tool" '{"jsonrpc":"2.0","id":"3","method":"call_tool","params":{"name":"linear_get_viewer","arguments":{}}}')"
assert_eq "$(json_get "${LINEAR_BODY}" "result.ok")" "True" "linear_get_viewer result.ok"

echo "[mcp-smoke] 4) structured schema error"
SCHEMA_BODY="$(rpc_call "call_tool" '{"jsonrpc":"2.0","id":"4","method":"call_tool","params":{"name":"linear_search_issues","arguments":{}}}')"
assert_eq "$(json_get "${SCHEMA_BODY}" "error.code")" "4001" "schema error code"
assert_eq "$(json_get "${SCHEMA_BODY}" "error.message")" "missing_required_field" "schema error message"
assert_eq "$(json_get "${SCHEMA_BODY}" "error.data.field")" "query" "schema error field"

echo "[mcp-smoke] 5) risk gate policy block"
RISK_BODY="$(rpc_call "call_tool" '{"jsonrpc":"2.0","id":"5","method":"call_tool","params":{"name":"notion_delete_block","arguments":{"block_id":"dummy"}}}')"
assert_eq "$(json_get "${RISK_BODY}" "error.code")" "4032" "policy blocked code"
assert_eq "$(json_get "${RISK_BODY}" "error.message")" "policy_blocked" "policy blocked message"

if [[ "${RUN_RATE_LIMIT_TEST}" == "1" ]]; then
  echo "[mcp-smoke] 6) optional rate limit (${RATE_LIMIT_CALLS} calls)"
  rate_limit_hits=0
  for i in $(seq 1 "${RATE_LIMIT_CALLS}"); do
    body="$(rpc_call "call_tool" '{"jsonrpc":"2.0","id":"rl","method":"call_tool","params":{"name":"linear_search_issues","arguments":{}}}')"
    code="$(json_get "${body}" "error.code")"
    if [[ "${code}" == "4290" ]]; then
      rate_limit_hits=$((rate_limit_hits + 1))
    fi
  done
  if [[ "${rate_limit_hits}" -ge 1 ]]; then
    echo "[PASS] rate_limit_exceeded observed: ${rate_limit_hits}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] rate_limit_exceeded not observed"
    fail_count=$((fail_count + 1))
  fi
fi

echo "[mcp-smoke] pass=${pass_count} fail=${fail_count}"
if [[ "${fail_count}" -gt 0 ]]; then
  exit 1
fi

echo "[mcp-smoke] done"
