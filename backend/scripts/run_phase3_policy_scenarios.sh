#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" ]]; then
  echo "[phase3-policy] ERROR: API_BASE_URL is required"
  exit 1
fi
if [[ -z "${USER_JWT:-}" ]]; then
  echo "[phase3-policy] ERROR: USER_JWT is required"
  exit 1
fi

LINEAR_ALLOWED_TEAM_ID="${LINEAR_ALLOWED_TEAM_ID:-team-a}"
LINEAR_BLOCKED_TEAM_ID="${LINEAR_BLOCKED_TEAM_ID:-team-b}"
HIGH_RISK_TOOL_NAME="${HIGH_RISK_TOOL_NAME:-notion_delete_block}"
HIGH_RISK_PAYLOAD_JSON="${HIGH_RISK_PAYLOAD_JSON:-{\"block_id\":\"dummy\"}}"
RUN_STRICT_HIGH_RISK="${RUN_STRICT_HIGH_RISK:-1}"

API_BASE_URL="${API_BASE_URL%/}"
pass_count=0
fail_count=0
created_key_ids=()

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

assert_ne() {
  local actual="$1"
  local unexpected="$2"
  local label="$3"
  if [[ "${actual}" != "${unexpected}" ]]; then
    echo "[PASS] ${label}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] ${label}: unexpected='${unexpected}'"
    fail_count=$((fail_count + 1))
  fi
}

api_create_key() {
  local name="$1"
  local allowed_tools_json="$2"
  local policy_json="$3"

  python3 - "$name" "$allowed_tools_json" "$policy_json" <<'PY'
import json
import sys

name = sys.argv[1]
allowed_tools_json = sys.argv[2]
policy_json = sys.argv[3]
payload = {"name": name}
if allowed_tools_json:
    payload["allowed_tools"] = json.loads(allowed_tools_json)
if policy_json:
    payload["policy_json"] = json.loads(policy_json)
print(json.dumps(payload))
PY
}

create_api_key() {
  local name="$1"
  local allowed_tools_json="$2"
  local policy_json="$3"

  local payload
  payload="$(api_create_key "${name}" "${allowed_tools_json}" "${policy_json}")"
  local body
  body="$(curl -sS -X POST "${API_BASE_URL}/api/api-keys" \
    -H "Authorization: Bearer ${USER_JWT}" \
    -H "Content-Type: application/json" \
    -d "${payload}")"
  local key
  key="$(json_get "${body}" "api_key")"
  local key_id
  key_id="$(json_get "${body}" "id")"
  if [[ -z "${key}" || -z "${key_id}" ]]; then
    echo "[phase3-policy] ERROR: failed to create api key, response=${body}"
    exit 1
  fi
  created_key_ids+=("${key_id}")
  echo "${key_id}|${key}"
}

revoke_created_keys() {
  for key_id in "${created_key_ids[@]-}"; do
    curl -sS -X DELETE "${API_BASE_URL}/api/api-keys/${key_id}" \
      -H "Authorization: Bearer ${USER_JWT}" >/dev/null || true
  done
}

mcp_call_tool() {
  local api_key="$1"
  local tool_name="$2"
  local args_json="$3"
  local payload
  payload="$(python3 - "$tool_name" "$args_json" <<'PY'
import json
import sys
print(json.dumps({
    "jsonrpc": "2.0",
    "id": "policy",
    "method": "call_tool",
    "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])},
}))
PY
)"
  curl -sS -X POST "${API_BASE_URL}/mcp/call_tool" \
    -H "Authorization: Bearer ${api_key}" \
    -H "Content-Type: application/json" \
    -d "${payload}"
}

trap revoke_created_keys EXIT

echo "[phase3-policy] API_BASE_URL=${API_BASE_URL}"
echo "[phase3-policy] running policy scenarios"

echo "[phase3-policy] 4-1 allowed_tools restriction"
case1="$(create_api_key "phase3-case1" "[\"notion_retrieve_bot_user\"]" "")"
case1_key="${case1#*|}"
body1="$(mcp_call_tool "${case1_key}" "linear_get_viewer" "{}")"
assert_eq "$(json_get "${body1}" "error.message")" "tool_not_allowed_for_api_key" "4-1 tool_not_allowed_for_api_key"

echo "[phase3-policy] 4-2 deny_tools priority"
case2="$(create_api_key "phase3-case2" "" "{\"deny_tools\":[\"linear_get_viewer\"]}")"
case2_key="${case2#*|}"
body2="$(mcp_call_tool "${case2_key}" "linear_get_viewer" "{}")"
assert_eq "$(json_get "${body2}" "error.message")" "access_denied" "4-2 access_denied"

echo "[phase3-policy] 4-3 allowed_services restriction"
case3="$(create_api_key "phase3-case3" "" "{\"allowed_services\":[\"notion\"]}")"
case3_key="${case3#*|}"
body3="$(mcp_call_tool "${case3_key}" "linear_get_viewer" "{}")"
assert_eq "$(json_get "${body3}" "error.message")" "service_not_allowed" "4-3 service_not_allowed"

echo "[phase3-policy] 4-4 allowed_linear_team_ids restriction"
case4_policy="$(python3 - "${LINEAR_ALLOWED_TEAM_ID}" <<'PY'
import json
import sys
print(json.dumps({"allowed_services": ["linear"], "allowed_linear_team_ids": [sys.argv[1]]}))
PY
)"
case4="$(create_api_key "phase3-case4" "" "${case4_policy}")"
case4_key="${case4#*|}"
case4_args="$(python3 - "${LINEAR_BLOCKED_TEAM_ID}" <<'PY'
import json
import sys
print(json.dumps({"team_id": sys.argv[1], "title": "phase3-policy-test"}))
PY
)"
body4="$(mcp_call_tool "${case4_key}" "linear_create_issue" "${case4_args}")"
assert_eq "$(json_get "${body4}" "error.message")" "access_denied" "4-4 access_denied"
assert_eq "$(json_get "${body4}" "error.data.reason")" "team_not_allowed" "4-4 reason.team_not_allowed"

echo "[phase3-policy] 4-5 allow_high_risk override"
case5="$(create_api_key "phase3-case5" "" "{\"allow_high_risk\":true}")"
case5_id="${case5%%|*}"
case5_key="${case5#*|}"
body5="$(mcp_call_tool "${case5_key}" "${HIGH_RISK_TOOL_NAME}" "${HIGH_RISK_PAYLOAD_JSON}")"
assert_ne "$(json_get "${body5}" "error.message")" "policy_blocked" "4-5 not blocked by policy gate"

if [[ "${RUN_STRICT_HIGH_RISK}" == "1" ]]; then
  echo "[phase3-policy] strict high-risk verification enabled"
  high_risk_ok="$(json_get "${body5}" "result.ok")"
  # Strict mode focuses on policy-gate behavior, not upstream SaaS success.
  high_risk_error_message="$(json_get "${body5}" "error.message")"
  assert_ne "${high_risk_error_message}" "policy_blocked" "4-5 strict not blocked by policy gate"
  if [[ "${high_risk_ok}" == "True" ]]; then
    logs_body="$(curl -sS -H "Authorization: Bearer ${USER_JWT}" \
      "${API_BASE_URL}/api/tool-calls?limit=20&api_key_id=${case5_id}&tool_name=${HIGH_RISK_TOOL_NAME}")"
    strict_result="$(
      python3 - "${logs_body}" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
rows = payload.get("items") or []
print("PASS" if any((row.get("status") == "success" and row.get("error_code") == "policy_override_allowed") for row in rows) else "FAIL")
PY
    )"
    assert_eq "${strict_result}" "PASS" "4-5 strict policy_override_allowed log"
  else
    echo "[phase3-policy] strict note: high-risk call failed upstream (policy gate passed)"
  fi
fi

echo "[phase3-policy] pass=${pass_count} fail=${fail_count}"
if [[ "${fail_count}" -gt 0 ]]; then
  exit 1
fi
echo "[phase3-policy] done"
