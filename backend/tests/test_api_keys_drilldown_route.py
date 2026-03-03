import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.api_keys import api_key_drilldown


def _request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/api-keys/1/drilldown", "headers": []}
    return Request(scope)


def test_api_key_drilldown_returns_summary(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 1, "name": "prod", "key_prefix": "metel_prod"}])
            if self.table_name == "tool_calls":
                return SimpleNamespace(
                    data=[
                        {"tool_name": "notion_search", "status": "success", "error_code": None, "latency_ms": 100, "created_at": "2026-03-03T00:00:00+00:00"},
                        {"tool_name": "notion_search", "status": "fail", "error_code": "policy_blocked", "latency_ms": 200, "created_at": "2026-03-03T01:00:00+00:00"},
                    ]
                )
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.api_keys.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(api_key_drilldown(_request(), key_id=1, days=7))
    assert out["api_key"]["id"] == 1
    assert out["summary"]["total_calls"] == 2
    assert out["summary"]["success_count"] == 1
    assert out["summary"]["fail_count"] == 1
    assert out["summary"]["p95_latency_ms"] == 200


def test_api_key_drilldown_not_found(monkeypatch):
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

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.api_keys.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(api_key_drilldown(_request(), key_id=1, days=7))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "api_key_not_found"
    else:
        assert False, "expected HTTPException"
