import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.organizations import (
    OrganizationCreateRequest,
    OrganizationMemberRequest,
    create_organization,
    list_organization_members,
    list_organizations,
    upsert_organization_member,
)


def _request(path: str = "/api/organizations", method: str = "GET") -> Request:
    scope = {"type": "http", "method": method, "path": path, "headers": []}
    return Request(scope)


def test_list_organizations_returns_memberships(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def in_(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"organization_id": 1, "role": "owner"}])
            if self.table_name == "organizations":
                return SimpleNamespace(data=[{"id": 1, "name": "Acme", "created_at": "2026-03-03T00:00:00+00:00", "updated_at": "2026-03-03T00:00:00+00:00"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(list_organizations(_request()))
    assert out["count"] == 1
    assert out["items"][0]["id"] == 1
    assert out["items"][0]["role"] == "owner"


def test_create_organization_inserts_owner_membership(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
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

        def execute(self):
            if self.mode == "insert" and self.table_name == "organizations":
                self.client.org_inserted = dict(self.payload or {})
                return SimpleNamespace(data=[{"id": 10, "name": "Core", "created_at": "2026-03-03T00:00:00+00:00", "updated_at": "2026-03-03T00:00:00+00:00"}])
            if self.mode == "upsert" and self.table_name == "org_memberships":
                self.client.membership_upserted = dict(self.payload or {})
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.org_inserted = None
            self.membership_upserted = None

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(create_organization(_request(method="POST"), OrganizationCreateRequest(name="Core")))
    assert out["item"]["id"] == 10
    assert client.org_inserted is not None
    assert client.membership_upserted is not None
    assert client.membership_upserted.get("role") == "owner"


def test_list_organization_members_requires_membership(monkeypatch):
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

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(list_organization_members(_request("/api/organizations/1/members"), "1"))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "organization_not_found"
    else:
        assert False, "expected HTTPException"


def test_upsert_organization_member_rejects_invalid_role(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": 1}])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            upsert_organization_member(
                _request("/api/organizations/1/members", "POST"),
                "1",
                OrganizationMemberRequest(user_id="user-2", role="bad-role"),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_member_role"
    else:
        assert False, "expected HTTPException"
