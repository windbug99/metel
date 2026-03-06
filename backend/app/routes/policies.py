from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from supabase import create_client

from agent.registry import load_registry
from app.core.auth import get_authenticated_user_id
from app.core.authz import Role, get_authz_context, require_min_role
from app.core.config import get_settings
from app.core.error_codes import ERR_ACCESS_DENIED, ERR_POLICY_BLOCKED, ERR_SERVICE_NOT_ALLOWED
from app.core.risk_gate import evaluate_risk_with_policy

router = APIRouter(prefix="/api/policies", tags=["policies"])
_PHASE1_SERVICES = {"notion", "linear"}


class SimulatePolicyRequest(BaseModel):
    api_key_id: int | None = None
    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


def _allowed_set(api_key: dict[str, Any]) -> set[str] | None:
    raw = api_key.get("allowed_tools")
    if not isinstance(raw, list):
        return None
    items = {str(item).strip() for item in raw if str(item).strip()}
    return items or None


def _policy(api_key: dict[str, Any]) -> dict[str, Any]:
    raw_effective = api_key.get("effective_policy_json")
    if isinstance(raw_effective, dict):
        return raw_effective
    raw = api_key.get("policy_json")
    return raw if isinstance(raw, dict) else {}


def _normalized_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    out: dict[str, Any] = {}
    if "allow_high_risk" in policy:
        out["allow_high_risk"] = bool(policy.get("allow_high_risk"))
    for key in ("allowed_services", "deny_tools", "allowed_linear_team_ids"):
        raw = policy.get(key)
        if isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
            out[key] = [item.lower() for item in values] if key == "allowed_services" else values
    return out


def _merge_team_and_key_policy(team_policy: dict[str, Any] | None, key_policy: dict[str, Any] | None) -> dict[str, Any]:
    team = _normalized_policy(team_policy)
    key = _normalized_policy(key_policy)
    if not team and not key:
        return {}
    merged: dict[str, Any] = {}
    if "allow_high_risk" in key:
        merged["allow_high_risk"] = bool(key["allow_high_risk"])
    elif "allow_high_risk" in team:
        merged["allow_high_risk"] = bool(team["allow_high_risk"])

    def _merge_allowlist(field: str) -> list[str] | None:
        team_values = set(team.get(field) or []) if isinstance(team.get(field), list) else None
        key_values = set(key.get(field) or []) if isinstance(key.get(field), list) else None
        if team_values is not None and key_values is not None:
            return sorted(team_values.intersection(key_values))
        if key_values is not None:
            return sorted(key_values)
        if team_values is not None:
            return sorted(team_values)
        return None

    allowed_services = _merge_allowlist("allowed_services")
    if allowed_services is not None:
        merged["allowed_services"] = allowed_services
    allowed_linear_team_ids = _merge_allowlist("allowed_linear_team_ids")
    if allowed_linear_team_ids is not None:
        merged["allowed_linear_team_ids"] = allowed_linear_team_ids

    deny_tools = set(team.get("deny_tools") or []) if isinstance(team.get("deny_tools"), list) else set()
    deny_tools.update(set(key.get("deny_tools") or []) if isinstance(key.get("deny_tools"), list) else set())
    if deny_tools:
        merged["deny_tools"] = sorted(deny_tools)
    return merged


def _enforce_member_simulation_scope(*, role: Role, team_ids: set[int], arguments: dict[str, Any]) -> None:
    if role != Role.MEMBER:
        return
    raw_org_id = arguments.get("organization_id")
    if raw_org_id not in (None, "", 0, "0"):
        raise HTTPException(
            status_code=403,
            detail={"code": "access_denied", "reason": "member_organization_scope_forbidden"},
        )

    raw_team_id = arguments.get("team_id")
    if raw_team_id in (None, ""):
        return
    team_id_text = str(raw_team_id).strip()
    if not team_id_text:
        return
    allowed_team_ids = {str(item) for item in team_ids}
    if team_id_text not in allowed_team_ids:
        raise HTTPException(
            status_code=403,
            detail={"code": "access_denied", "reason": "member_team_scope_mismatch"},
        )


@router.post("/simulate")
async def simulate_policy(request: Request, body: SimulatePolicyRequest):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    authz_ctx = await get_authz_context(request, user_id=user_id, supabase=supabase)
    require_min_role(authz_ctx, Role.MEMBER, method=request.method)

    tool_name = body.tool_name.strip()
    arguments = body.arguments if isinstance(body.arguments, dict) else {}
    _enforce_member_simulation_scope(role=authz_ctx.role, team_ids=authz_ctx.team_ids, arguments=arguments)
    registry = load_registry()
    try:
        tool = registry.get_tool(tool_name)
    except KeyError:
        examples = [item.tool_name for item in registry.list_tools() if item.service in _PHASE1_SERVICES][:20]
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unknown_tool",
                "message": "Unknown tool_name. Use exact tool identifier (e.g. notion_search, linear_list_issues).",
                "examples": examples,
            },
        )
    if tool.service not in _PHASE1_SERVICES:
        raise HTTPException(status_code=400, detail="tool_not_available_in_phase1")

    api_key: dict[str, Any] = {
        "id": None,
        "allowed_tools": None,
        "policy_json": None,
    }
    if body.api_key_id is not None:
        rows = (
            supabase.table("api_keys")
            .select("id,name,key_prefix,is_active,team_id,allowed_tools,policy_json")
            .eq("id", body.api_key_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            raise HTTPException(status_code=404, detail="api_key_not_found")
        api_key = rows[0]
        team_id = api_key.get("team_id")
        team_policy_rows = (
            supabase.table("team_policies")
            .select("policy_json")
            .eq("team_id", team_id)
            .limit(1)
            .execute()
        ).data or []
        team_policy = team_policy_rows[0].get("policy_json") if team_policy_rows else None
        api_key["effective_policy_json"] = _merge_team_and_key_policy(
            team_policy if isinstance(team_policy, dict) else None,
            api_key.get("policy_json") if isinstance(api_key.get("policy_json"), dict) else None,
        )

    reasons: list[dict[str, Any]] = []
    allowed = True

    allowed_tools = _allowed_set(api_key)
    if allowed_tools is not None and tool_name not in allowed_tools:
        allowed = False
        reasons.append(
            {
                "code": "tool_not_allowed_for_api_key",
                "message": "Tool is not in API key allowlist.",
                "source": "api_key.allowed_tools",
            }
        )

    policy_json = _policy(api_key)
    deny_tools_raw = policy_json.get("deny_tools")
    deny_tools = {str(item).strip() for item in deny_tools_raw if str(item).strip()} if isinstance(deny_tools_raw, list) else set()
    if tool_name in deny_tools:
        allowed = False
        reasons.append({"code": ERR_ACCESS_DENIED, "message": "Tool denied by policy.", "source": "policy.deny_tools"})

    allowed_services_raw = policy_json.get("allowed_services")
    allowed_services = (
        {str(item).strip().lower() for item in allowed_services_raw if str(item).strip()}
        if isinstance(allowed_services_raw, list)
        else set()
    )
    if allowed_services and tool.service not in allowed_services:
        allowed = False
        reasons.append({"code": ERR_SERVICE_NOT_ALLOWED, "message": "Service denied by policy.", "source": "policy.allowed_services"})

    risk = evaluate_risk_with_policy(tool_name=tool_name, payload=arguments, policy=policy_json)
    if not risk.allowed:
        allowed = False
        reasons.append(
            {
                "code": ERR_POLICY_BLOCKED,
                "message": "Risk gate blocked this request.",
                "source": "risk_gate",
                "risk_reason": risk.reason,
                "risk_type": risk.risk_type,
            }
        )

    allowed_linear_team_ids_raw = policy_json.get("allowed_linear_team_ids")
    if tool.service == "linear" and isinstance(allowed_linear_team_ids_raw, list):
        allowed_team_ids = {str(item).strip() for item in allowed_linear_team_ids_raw if str(item).strip()}
        team_id = str(arguments.get("team_id") or "").strip()
        if team_id and team_id not in allowed_team_ids:
            allowed = False
            reasons.append(
                {
                    "code": ERR_ACCESS_DENIED,
                    "message": "Linear team is not allowed.",
                    "source": "policy.allowed_linear_team_ids",
                    "team_id": team_id,
                }
            )

    decision = "allowed" if allowed else "blocked"
    return {
        "decision": decision,
        "tool_name": tool_name,
        "service": tool.service,
        "api_key_id": api_key.get("id"),
        "reasons": reasons,
        "risk": {"allowed": risk.allowed, "reason": risk.reason, "risk_type": risk.risk_type},
    }
