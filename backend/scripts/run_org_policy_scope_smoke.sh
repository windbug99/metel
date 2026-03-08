#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" ]]; then
  echo "[org-policy-smoke] ERROR: API_BASE_URL is required"
  exit 1
fi
if [[ -z "${ORG_ID:-}" || -z "${TEAM_ID:-}" ]]; then
  echo "[org-policy-smoke] ERROR: ORG_ID and TEAM_ID are required"
  exit 1
fi
if [[ -z "${OWNER_JWT:-}" || -z "${ADMIN_JWT:-}" || -z "${MEMBER_JWT:-}" ]]; then
  echo "[org-policy-smoke] ERROR: OWNER_JWT, ADMIN_JWT, MEMBER_JWT are required"
  exit 1
fi

API_BASE_URL="${API_BASE_URL%/}"
PASS=0
FAIL=0

record_pass() {
  echo "[PASS] $1"
  PASS=$((PASS + 1))
}

record_fail() {
  echo "[FAIL] $1"
  FAIL=$((FAIL + 1))
}

http_status() {
  local token="$1"
  local method="$2"
  local path="$3"
  local data="${4:-}"
  if [[ -n "${data}" ]]; then
    curl -sS -o /dev/null -w "%{http_code}" \
      -X "${method}" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "${data}" \
      "${API_BASE_URL}${path}"
    return
  fi
  curl -sS -o /dev/null -w "%{http_code}" \
    -X "${method}" \
    -H "Authorization: Bearer ${token}" \
    "${API_BASE_URL}${path}"
}

http_status_and_body() {
  local token="$1"
  local method="$2"
  local path="$3"
  local data="${4:-}"
  local out
  local code
  out="$(mktemp)"
  if [[ -n "${data}" ]]; then
    code="$(curl -sS -o "${out}" -w "%{http_code}" \
      -X "${method}" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "${data}" \
      "${API_BASE_URL}${path}")"
  else
    code="$(curl -sS -o "${out}" -w "%{http_code}" \
      -X "${method}" \
      -H "Authorization: Bearer ${token}" \
      "${API_BASE_URL}${path}")"
  fi
  printf "%s\n" "${code}"
  cat "${out}"
  rm -f "${out}"
}

echo "[org-policy-smoke] API_BASE_URL=${API_BASE_URL} ORG_ID=${ORG_ID} TEAM_ID=${TEAM_ID}"

owner_org_get="$(http_status "${OWNER_JWT}" GET "/api/organizations/${ORG_ID}/policy")"
admin_org_get="$(http_status "${ADMIN_JWT}" GET "/api/organizations/${ORG_ID}/policy")"
member_org_get="$(http_status "${MEMBER_JWT}" GET "/api/organizations/${ORG_ID}/policy")"

[[ "${owner_org_get}" == "200" ]] && record_pass "owner GET /organizations/{org}/policy=200" || record_fail "owner GET /organizations/{org}/policy expected 200 got ${owner_org_get}"
[[ "${admin_org_get}" == "200" ]] && record_pass "admin GET /organizations/{org}/policy=200" || record_fail "admin GET /organizations/{org}/policy expected 200 got ${admin_org_get}"
[[ "${member_org_get}" == "200" ]] && record_pass "member GET /organizations/{org}/policy=200" || record_fail "member GET /organizations/{org}/policy expected 200 got ${member_org_get}"

current_org_policy_body="$(
  curl -sS -H "Authorization: Bearer ${OWNER_JWT}" \
    "${API_BASE_URL}/api/organizations/${ORG_ID}/policy"
)"
current_org_policy_json="$(
  python3 - <<'PY' "${current_org_policy_body}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
item = payload.get("item") or {}
policy = item.get("policy_json") if isinstance(item.get("policy_json"), dict) else {}
print(json.dumps(policy))
PY
)"
owner_org_patch_payload="$(
  python3 - <<'PY' "${current_org_policy_json}"
import json
import sys
policy = json.loads(sys.argv[1] or "{}")
print(json.dumps({"policy_json": policy}))
PY
)"
owner_org_patch="$(http_status "${OWNER_JWT}" PATCH "/api/organizations/${ORG_ID}/policy" "${owner_org_patch_payload}")"
member_org_patch="$(http_status "${MEMBER_JWT}" PATCH "/api/organizations/${ORG_ID}/policy" "${owner_org_patch_payload}")"
[[ "${owner_org_patch}" == "200" ]] && record_pass "owner PATCH /organizations/{org}/policy=200" || record_fail "owner PATCH /organizations/{org}/policy expected 200 got ${owner_org_patch}"
[[ "${member_org_patch}" == "403" ]] && record_pass "member PATCH /organizations/{org}/policy=403" || record_fail "member PATCH /organizations/{org}/policy expected 403 got ${member_org_patch}"

owner_oauth_get="$(http_status "${OWNER_JWT}" GET "/api/organizations/${ORG_ID}/oauth-policy")"
admin_oauth_get="$(http_status "${ADMIN_JWT}" GET "/api/organizations/${ORG_ID}/oauth-policy")"
member_oauth_get="$(http_status "${MEMBER_JWT}" GET "/api/organizations/${ORG_ID}/oauth-policy")"
[[ "${owner_oauth_get}" == "200" ]] && record_pass "owner GET /organizations/{org}/oauth-policy=200" || record_fail "owner GET /organizations/{org}/oauth-policy expected 200 got ${owner_oauth_get}"
[[ "${admin_oauth_get}" == "200" ]] && record_pass "admin GET /organizations/{org}/oauth-policy=200" || record_fail "admin GET /organizations/{org}/oauth-policy expected 200 got ${admin_oauth_get}"
[[ "${member_oauth_get}" == "200" ]] && record_pass "member GET /organizations/{org}/oauth-policy=200" || record_fail "member GET /organizations/{org}/oauth-policy expected 200 got ${member_oauth_get}"

admin_oauth_patch="$(http_status "${ADMIN_JWT}" PATCH "/api/organizations/${ORG_ID}/oauth-policy" '{"allowed_providers":["notion","linear"],"required_providers":["notion"],"blocked_providers":[],"approval_workflow":{"mode":"manual"}}')"
member_oauth_patch="$(http_status "${MEMBER_JWT}" PATCH "/api/organizations/${ORG_ID}/oauth-policy" '{"allowed_providers":["notion"],"required_providers":[],"blocked_providers":[]}')"
[[ "${admin_oauth_patch}" == "200" ]] && record_pass "admin PATCH /organizations/{org}/oauth-policy=200" || record_fail "admin PATCH /organizations/{org}/oauth-policy expected 200 got ${admin_oauth_patch}"
[[ "${member_oauth_patch}" == "403" ]] && record_pass "member PATCH /organizations/{org}/oauth-policy=403" || record_fail "member PATCH /organizations/{org}/oauth-policy expected 403 got ${member_oauth_patch}"

# Team policy write smoke: patch current policy with same payload to avoid accidental baseline violation.
team_list="$(
  curl -sS -H "Authorization: Bearer ${OWNER_JWT}" \
    "${API_BASE_URL}/api/teams?organization_id=${ORG_ID}"
)"
team_policy_json="$(
  python3 - <<'PY' "${team_list}" "${TEAM_ID}"
import json
import sys
payload = json.loads(sys.argv[1] or "{}")
team_id = str(sys.argv[2])
items = payload.get("items") or []
for item in items:
    if str(item.get("id")) == team_id:
        print(json.dumps(item.get("policy_json") if isinstance(item.get("policy_json"), dict) else {}))
        break
else:
    print("{}")
PY
)"
owner_team_patch_payload="$(python3 - <<'PY' "${team_policy_json}"
import json
import sys
policy = json.loads(sys.argv[1] or "{}")
print(json.dumps({"policy_json": policy}))
PY
)"
owner_team_patch="$(http_status "${OWNER_JWT}" PATCH "/api/teams/${TEAM_ID}" "${owner_team_patch_payload}")"
if [[ "${owner_team_patch}" == "200" ]]; then
  record_pass "owner PATCH /teams/{team}=200 (policy roundtrip)"
elif [[ "${owner_team_patch}" == "422" ]]; then
  record_fail "owner PATCH /teams/{team} got 422 (baseline violation)"
  team_patch_result="$(http_status_and_body "${OWNER_JWT}" PATCH "/api/teams/${TEAM_ID}" "${owner_team_patch_payload}")"
  team_patch_body="$(printf "%s\n" "${team_patch_result}" | sed '1d')"
  echo "[org-policy-smoke] team policy 422 detail: ${team_patch_body}"
else
  record_fail "owner PATCH /teams/{team} expected 200 got ${owner_team_patch}"
fi

echo "[org-policy-smoke] pass=${PASS} fail=${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
echo "[org-policy-smoke] done"
