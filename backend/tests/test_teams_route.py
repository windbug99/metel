import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.teams import delete_team_member


def _request(path: str) -> Request:
    scope = {"type": "http", "method": "DELETE", "path": path, "headers": []}
    return Request(scope)


def test_delete_team_member_success(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self._mode = "select"

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def delete(self):
            self._mode = "delete"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "delete":
                return SimpleNamespace(data=[])
            if self.table_name == "teams":
                return SimpleNamespace(data=[{"id": 1}])
            if self.table_name == "team_memberships":
                return SimpleNamespace(data=[{"id": 10}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.teams.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.teams.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.teams.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(delete_team_member(_request("/api/teams/1/members/10"), "1", "10"))
    assert out["ok"] is True


def test_delete_team_member_not_found(monkeypatch):
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
            if self.table_name == "teams":
                return SimpleNamespace(data=[{"id": 1}])
            if self.table_name == "team_memberships":
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.teams.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.teams.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.teams.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(delete_team_member(_request("/api/teams/1/members/99"), "1", "99"))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "team_member_not_found"
    else:
        assert False, "expected HTTPException"
