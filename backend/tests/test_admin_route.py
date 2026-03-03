import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.admin import (
    IncidentBannerRevisionCreateRequest,
    IncidentBannerRevisionReviewRequest,
    IncidentBannerUpdateRequest,
    create_incident_banner_revision,
    external_health,
    get_incident_banner,
    review_incident_banner_revision,
    update_incident_banner,
)


def _request(path: str, method: str = "GET") -> Request:
    scope = {"type": "http", "method": method, "path": path, "headers": []}
    return Request(scope)


def test_external_health_aggregates_connectors(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {"connector": "notion", "tool_name": "notion_search", "status": "success", "error_code": None, "latency_ms": 100, "created_at": "2026-03-03T00:00:00+00:00"},
                    {"connector": "notion", "tool_name": "notion_delete_block", "status": "fail", "error_code": "upstream_temporary_failure", "latency_ms": 120, "created_at": "2026-03-03T00:01:00+00:00"},
                    {"connector": "linear", "tool_name": "linear_list_issues", "status": "fail", "error_code": "policy_blocked", "latency_ms": 80, "created_at": "2026-03-03T00:02:00+00:00"},
                ]
            )

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.admin.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.admin.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.admin.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(external_health(_request("/api/admin/external-health"), days=1))
    assert out["window_days"] == 1
    assert any(item["connector"] == "notion" for item in out["items"])
    assert any(item["connector"] == "linear" for item in out["items"])


def test_get_incident_banner_defaults_when_missing(monkeypatch):
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

    monkeypatch.setattr("app.routes.admin.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.admin.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.admin.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(get_incident_banner(_request("/api/admin/incident-banner")))
    assert out["enabled"] is False
    assert out["severity"] == "info"


def test_update_incident_banner_rejects_invalid_severity(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.admin.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.admin.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr("app.routes.admin.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    body = IncidentBannerUpdateRequest(enabled=True, message="x", severity="severe")
    try:
        asyncio.run(update_incident_banner(_request("/api/admin/incident-banner", "PATCH"), body))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_severity"
    else:
        assert False, "expected HTTPException"


def test_create_incident_banner_revision_returns_item(monkeypatch):
    class _Query:
        def __init__(self):
            self.payload = None

        def insert(self, payload: dict):
            self.payload = payload
            return self

        def execute(self):
            return SimpleNamespace(data=[self.payload])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.admin.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.admin.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.admin.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(
        create_incident_banner_revision(
            _request("/api/admin/incident-banner/revisions", "POST"),
            IncidentBannerRevisionCreateRequest(enabled=True, message="m", severity="warning"),
        )
    )
    assert out["item"]["status"] == "pending"
    assert out["item"]["severity"] == "warning"


def test_review_incident_banner_revision_rejects_invalid_decision(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.admin.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.admin.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr("app.routes.admin.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            review_incident_banner_revision(
                _request("/api/admin/incident-banner/revisions/1/review", "POST"),
                "1",
                IncidentBannerRevisionReviewRequest(decision="skip"),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_decision"
    else:
        assert False, "expected HTTPException"
