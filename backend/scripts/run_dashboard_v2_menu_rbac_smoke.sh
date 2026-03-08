#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" ]]; then
  echo "[dashboard-v2-menu-rbac] ERROR: API_BASE_URL is required"
  exit 1
fi

if [[ -z "${OWNER_JWT:-}" || -z "${ADMIN_JWT:-}" || -z "${MEMBER_JWT:-}" ]]; then
  echo "[dashboard-v2-menu-rbac] ERROR: OWNER_JWT, ADMIN_JWT, MEMBER_JWT are required"
  exit 1
fi

API_BASE_URL="${API_BASE_URL%/}"

echo "[dashboard-v2-menu-rbac] API_BASE_URL=${API_BASE_URL}"

owner_perm="$(
  curl -sS -H "Authorization: Bearer ${OWNER_JWT}" \
    "${API_BASE_URL}/api/me/permissions"
)"
admin_perm="$(
  curl -sS -H "Authorization: Bearer ${ADMIN_JWT}" \
    "${API_BASE_URL}/api/me/permissions"
)"
member_perm="$(
  curl -sS -H "Authorization: Bearer ${MEMBER_JWT}" \
    "${API_BASE_URL}/api/me/permissions"
)"

python3 - "${owner_perm}" "${admin_perm}" "${member_perm}" <<'PY'
import json
import sys

owner = json.loads(sys.argv[1])
admin = json.loads(sys.argv[2])
member = json.loads(sys.argv[3])

TEAM_MENU = [
    "team-overview",
    "team-usage",
    "team-policy",
    "team-agent-guide",
    "team-api-keys",
    "team-policy-simulator",
    "team-audit-events",
]
USER_MENU = [
    "user-profile",
    "user-my-requests",
    "user-security",
    "user-oauth-connections",
]
ORG_MENU_BASE = [
    "org-access",
    "org-integrations",
    "org-oauth-governance",
    "org-audit-settings",
]

def visible_menu_keys(row: dict) -> list[str]:
    role = str(row.get("role") or "")
    perms = row.get("permissions") or {}
    can_read_admin_ops = bool(perms.get("can_read_admin_ops"))
    is_admin_plus = role in {"owner", "admin"}
    keys: list[str] = []
    if is_admin_plus:
        keys.extend(ORG_MENU_BASE)
        if can_read_admin_ops:
            keys.append("org-admin-ops")
    keys.extend(TEAM_MENU)
    keys.extend(USER_MENU)
    return keys

def expect(cond: bool, label: str):
    if not cond:
        raise AssertionError(label)
    print(f"[PASS] {label}")

expect(owner.get("role") == "owner", "owner.role == owner")
expect(admin.get("role") == "admin", "admin.role == admin")
expect(member.get("role") == "member", "member.role == member")

expect(
    visible_menu_keys(owner)
    == ORG_MENU_BASE + ["org-admin-ops"] + TEAM_MENU + USER_MENU,
    "owner visible menu keys",
)
expect(
    visible_menu_keys(admin)
    == ORG_MENU_BASE + ["org-admin-ops"] + TEAM_MENU + USER_MENU,
    "admin visible menu keys",
)
expect(visible_menu_keys(member) == TEAM_MENU + USER_MENU, "member visible menu keys")

expect(bool((owner.get("permissions") or {}).get("can_manage_incident_banner")) is True, "owner incident-banner manage")
expect(bool((admin.get("permissions") or {}).get("can_manage_incident_banner")) is False, "admin incident-banner denied")
expect(bool((member.get("permissions") or {}).get("can_manage_incident_banner")) is False, "member incident-banner denied")

print("[dashboard-v2-menu-rbac] done")
PY
