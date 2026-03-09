import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.authz import AuthzContext, Role
from app.routes.admin import IncidentBannerUpdateRequest, external_health, update_incident_banner
from app.routes.audit import AuditSettingsUpdateRequest, get_audit_settings, update_audit_settings
from app.routes.integrations import WebhookCreateRequest, create_webhook, list_webhooks
from app.routes.teams import TeamCreateRequest, create_team


def _request(path: str, method: str = "GET") -> Request:
    scope = {"type": "http", "method": method, "path": path, "query_string": b"", "headers": []}
    return Request(scope)


class _Query:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.mode = "select"
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def insert(self, payload: dict):
        self.mode = "insert"
        self.payload = payload
        return self

    def upsert(self, payload: dict, **_kwargs):
        self.mode = "upsert"
        self.payload = payload
        return self

    def update(self, payload: dict):
        self.mode = "update"
        self.payload = payload
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.mode == "select":
            return SimpleNamespace(data=[])
        if self.mode == "insert":
            if self.table_name == "teams":
                payload = dict(self.payload or {})
                payload.setdefault("id", 1)
                payload.setdefault("name", "Core")
                return SimpleNamespace(data=[payload])
            return SimpleNamespace(data=[dict(self.payload or {})])
        if self.mode in {"upsert", "update", "delete"}:
            return SimpleNamespace(data=[dict(self.payload or {})] if self.payload else [])
        return SimpleNamespace(data=[])


class _Client:
    def table(self, name: str):
        return _Query(name)


def _patch_authz(monkeypatch, role: Role):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="user-1", role=role, org_ids={1}, team_ids={1})

    modules = [
        "app.routes.audit",
        "app.routes.admin",
        "app.routes.teams",
        "app.routes.integrations",
    ]
    for module in modules:
        monkeypatch.setattr(f"{module}.get_authenticated_user_id", _fake_user)
        monkeypatch.setattr(f"{module}.get_authz_context", _fake_authz)
        monkeypatch.setattr(f"{module}.create_client", lambda *_args, **_kwargs: _Client())
        monkeypatch.setattr(f"{module}.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))


_ROLE_RANK = {
    Role.MEMBER: 10,
    Role.ADMIN: 20,
    Role.OWNER: 30,
}


@pytest.mark.parametrize("role", [Role.MEMBER, Role.ADMIN, Role.OWNER])
@pytest.mark.parametrize(
    ("case_id", "required_role"),
    [
        ("audit_get_settings", Role.ADMIN),
        ("audit_patch_settings", Role.OWNER),
        ("admin_external_health", Role.ADMIN),
        ("admin_patch_incident", Role.OWNER),
        ("teams_create", Role.ADMIN),
        ("integrations_create_webhook", Role.ADMIN),
        ("integrations_list_webhooks", Role.MEMBER),
    ],
)
def test_rbac_authorization_matrix(monkeypatch, role: Role, case_id: str, required_role: Role):
    _patch_authz(monkeypatch, role)

    async def _invoke():
        if case_id == "audit_get_settings":
            return await get_audit_settings(_request("/api/audit/settings"))
        if case_id == "audit_patch_settings":
            return await update_audit_settings(
                _request("/api/audit/settings", "PATCH"),
                AuditSettingsUpdateRequest(retention_days=30, export_enabled=True, masking_policy={"mask_keys": ["token"]}),
            )
        if case_id == "admin_external_health":
            return await external_health(_request("/api/admin/external-health"), days=1)
        if case_id == "admin_patch_incident":
            return await update_incident_banner(
                _request("/api/admin/incident-banner", "PATCH"),
                IncidentBannerUpdateRequest(enabled=True, message="m", severity="warning"),
            )
        if case_id == "teams_create":
            return await create_team(
                _request("/api/teams", "POST"),
                TeamCreateRequest(name="Core", description="d", policy_json={"allowed_services": ["notion"]}),
            )
        if case_id == "integrations_create_webhook":
            return await create_webhook(
                _request("/api/integrations/webhooks", "POST"),
                WebhookCreateRequest(
                    name="hook",
                    endpoint_url="https://example.com/webhook",
                    secret=None,
                    event_types=["tool_called"],
                ),
            )
        if case_id == "integrations_list_webhooks":
            return await list_webhooks(_request("/api/integrations/webhooks"))
        raise AssertionError(f"unknown case: {case_id}")

    should_allow = _ROLE_RANK[role] >= _ROLE_RANK[required_role]
    if should_allow:
        out = asyncio.run(_invoke())
        assert out is not None
    else:
        try:
            asyncio.run(_invoke())
        except HTTPException as exc:
            assert exc.status_code == 403
            assert isinstance(exc.detail, dict)
            assert exc.detail.get("code") == "access_denied"
            assert exc.detail.get("reason") == "insufficient_role"
        else:
            assert False, "expected HTTPException"
