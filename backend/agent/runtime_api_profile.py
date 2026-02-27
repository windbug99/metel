from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent.registry import ToolDefinition, load_registry


@dataclass(frozen=True)
class ApiBlockReason:
    api_id: str
    reason: str


_SCOPE_ALIASES: dict[str, dict[str, str]] = {
    "google": {
        "https://www.googleapis.com/auth/calendar.readonly": "calendar.read",
        "https://www.googleapis.com/auth/calendar": "calendar.read",
    },
}


def _canonical_scope(provider: str, scope: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    value = str(scope or "").strip()
    if not value:
        return ""
    alias_map = _SCOPE_ALIASES.get(normalized_provider, {})
    return alias_map.get(value, value)


def _normalize_services(connected_services: Iterable[str]) -> set[str]:
    return {str(item or "").strip().lower() for item in connected_services if str(item or "").strip()}


def _is_high_risk_tool(tool_name: str) -> bool:
    lowered = str(tool_name or "").strip().lower()
    return any(token in lowered for token in ("delete", "archive", "remove", "purge"))


def _scope_allowed(tool: ToolDefinition, granted_scopes: dict[str, set[str]] | None) -> bool:
    provider = str(tool.service or "").strip().lower()
    required = {_canonical_scope(provider, item) for item in (tool.required_scopes or ()) if _canonical_scope(provider, item)}
    if not required:
        return True
    scope_map = {
        str(k or "").strip().lower(): {
            _canonical_scope(str(k or "").strip().lower(), item)
            for item in (v or set())
            if _canonical_scope(str(k or "").strip().lower(), item)
        }
        for k, v in (granted_scopes or {}).items()
    }
    granted = scope_map.get(provider, set())
    return required.issubset(granted)


def build_runtime_api_profile(
    *,
    connected_services: list[str],
    granted_scopes: dict[str, set[str]] | None = None,
    tenant_policy: dict[str, object] | None = None,
    risk_policy: dict[str, object] | None = None,
) -> dict[str, object]:
    registry = load_registry()
    connected = _normalize_services(connected_services)
    tenant = tenant_policy or {}
    risk = risk_policy or {}
    blocked_tools = {str(item or "").strip() for item in (tenant.get("blocked_tools") or []) if str(item or "").strip()}
    allow_high_risk = bool(risk.get("allow_high_risk", False))

    enabled_api_ids: list[str] = []
    blocked: list[ApiBlockReason] = []

    for tool in registry.list_tools():
        if tool.service not in connected:
            continue
        if tool.tool_name in blocked_tools:
            blocked.append(ApiBlockReason(api_id=tool.tool_name, reason="tenant_policy_blocked"))
            continue
        if not _scope_allowed(tool, granted_scopes):
            blocked.append(ApiBlockReason(api_id=tool.tool_name, reason="missing_required_scope"))
            continue
        if _is_high_risk_tool(tool.tool_name) and not allow_high_risk:
            blocked.append(ApiBlockReason(api_id=tool.tool_name, reason="risk_policy_blocked"))
            continue
        enabled_api_ids.append(tool.tool_name)

    return {
        "enabled_api_ids": sorted(enabled_api_ids),
        "blocked_api_ids": [entry.api_id for entry in blocked],
        "blocked_reason": [{"api_id": entry.api_id, "reason": entry.reason} for entry in blocked],
    }
