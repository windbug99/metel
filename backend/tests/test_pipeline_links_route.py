import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.pipeline_links import list_recent_pipeline_links


def _request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/pipeline-links/recent", "headers": []}
    return Request(scope)


def test_list_recent_pipeline_links_returns_rows(monkeypatch):
    class _Resp:
        data = [{"event_id": "evt-1", "status": "succeeded"}]

    class _Query:
        def __init__(self):
            self.lt_calls = []

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def lt(self, field: str, value: str):
            self.lt_calls.append((field, value))
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return _Resp()

    class _Client:
        last_query = None

        def table(self, _name: str):
            query = _Query()
            self.last_query = query
            return query

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.pipeline_links.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.pipeline_links.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.pipeline_links.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            pipeline_links_table="pipeline_links",
        ),
    )

    out = asyncio.run(list_recent_pipeline_links(_request(), limit=20, cursor_updated_at="2026-02-25T10:00:00Z"))
    assert out["count"] == 1
    assert out["items"][0]["event_id"] == "evt-1"
    assert "next_cursor_updated_at" in out


def test_list_recent_pipeline_links_rejects_invalid_cursor(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.pipeline_links.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr(
        "app.routes.pipeline_links.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            pipeline_links_table="pipeline_links",
        ),
    )

    try:
        asyncio.run(list_recent_pipeline_links(_request(), limit=20, cursor_updated_at="not-a-date"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_cursor_updated_at"
    else:
        assert False, "expected HTTPException"
