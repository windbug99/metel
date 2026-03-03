import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.audit import AuditSettingsUpdateRequest, export_audit_events, get_audit_settings, update_audit_settings


def _request(path: str) -> Request:
    scope = {"type": "http", "method": "GET", "path": path, "headers": []}
    return Request(scope)


def test_get_audit_settings_defaults(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.audit.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(get_audit_settings(_request("/api/audit/settings")))
    assert out["retention_days"] == 90
    assert out["export_enabled"] is True


def test_update_audit_settings_upsert(monkeypatch):
    class _Query:
        def __init__(self, client):
            self.client = client
            self._mode = "select"
            self._payload = None

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def upsert(self, payload: dict, **_kwargs):
            self._mode = "upsert"
            self._payload = payload
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[])
            if self._mode == "upsert":
                self.client.upsert_payload = dict(self._payload or {})
                return SimpleNamespace(data=[self._payload])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.upsert_payload = None

        def table(self, _name: str):
            return _Query(self)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.audit.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(
        update_audit_settings(
            _request("/api/audit/settings"),
            AuditSettingsUpdateRequest(retention_days=30, export_enabled=False, masking_policy={"mask_keys": ["token"]}),
        )
    )
    assert out["retention_days"] == 30
    assert out["export_enabled"] is False
    assert client.upsert_payload is not None


def test_export_audit_events_blocked_by_settings(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "audit_settings":
                return SimpleNamespace(data=[{"user_id": "user-1", "retention_days": 30, "export_enabled": False, "masking_policy": {}, "updated_at": "2026-03-03T00:00:00+00:00"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.audit.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            export_audit_events(
                _request("/api/audit/export"),
                format="csv",
                limit=10,
                status="all",
                tool_name="",
                api_key_id=None,
                error_code="",
                connector="",
                decision="all",
                from_="",
                to="",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "audit_export_disabled"
    else:
        assert False, "expected HTTPException"
