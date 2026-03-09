import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.authz import AuthzContext, Role
from app.routes.organizations import (
    OrganizationCreateRequest,
    OrganizationInviteCreateRequest,
    OrganizationInviteAcceptRequest,
    OrganizationMemberRequest,
    OrganizationRoleRequestCreateRequest,
    OrganizationRoleRequestReviewRequest,
    OrganizationUpdateRequest,
    accept_organization_invite,
    create_organization_invite,
    get_organization_oauth_policy,
    get_organization_policy,
    create_organization,
    create_organization_role_request,
    delete_organization,
    delete_organization_member,
    list_organization_members,
    list_organization_role_requests,
    list_organizations,
    reissue_organization_invite,
    revoke_organization_invite,
    review_organization_role_request,
    update_organization_oauth_policy,
    update_organization_policy,
    update_organization,
    upsert_organization_member,
    OrganizationOAuthPolicyUpdateRequest,
    OrganizationPolicyUpdateRequest,
)


def _request(path: str = "/api/organizations", method: str = "GET") -> Request:
    scope = {"type": "http", "method": method, "path": path, "headers": []}
    return Request(scope)


@pytest.fixture(autouse=True)
def _default_authz_admin(monkeypatch):
    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="owner-user", role=Role.OWNER, org_ids={1}, team_ids={1})

    monkeypatch.setattr("app.routes.organizations.get_authz_context", _fake_authz)


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
            return SimpleNamespace(data=[{"role": "owner"}])

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


def test_update_organization_requires_owner(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def update(self, *_args, **_kwargs):
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
        asyncio.run(update_organization(_request("/api/organizations/1", "PATCH"), "1", body=OrganizationUpdateRequest(name="Renamed")))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "organization_not_found"
    else:
        assert False, "expected HTTPException"


def test_delete_organization_requires_owner(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def delete(self):
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
        asyncio.run(delete_organization(_request("/api/organizations/1", "DELETE"), "1"))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "organization_not_found"
    else:
        assert False, "expected HTTPException"


def test_delete_organization_deletes_row(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.mode = "select"

        def select(self, *_args, **_kwargs):
            self.mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def delete(self):
            self.mode = "delete"
            return self

        def execute(self):
            if self.table_name == "org_memberships" and self.mode == "select":
                return SimpleNamespace(data=[{"organization_id": 1}])
            if self.table_name == "organizations" and self.mode == "delete":
                self.client.deleted = True
                return SimpleNamespace(data=[{"id": 1}])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.deleted = False

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(delete_organization(_request("/api/organizations/1", "DELETE"), "1"))
    assert out["ok"] is True
    assert client.deleted is True


def test_delete_organization_member_blocks_owner_self_removal(monkeypatch):
    class _OwnerQuery:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"role": "owner"}])

    class _Client:
        def table(self, name: str):
            if name == "organizations":
                return _OwnerQuery()
            return _OwnerQuery()

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(delete_organization_member(_request("/api/organizations/1/members/owner-user", "DELETE"), "1", "owner-user"))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "cannot_remove_owner_self"
    else:
        assert False, "expected HTTPException"


def test_create_organization_invite_requires_owner(monkeypatch):
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
        asyncio.run(create_organization_invite(_request("/api/organizations/1/invites", "POST"), "1", OrganizationInviteCreateRequest(role="member")))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "organization_not_found"
    else:
        assert False, "expected HTTPException"


def test_review_role_request_approve_updates_membership(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.mode = "select"
            self.payload = None

        def select(self, *_args, **_kwargs):
            self.mode = "select"
            return self

        def update(self, payload: dict):
            self.mode = "update"
            self.payload = payload
            return self

        def upsert(self, payload: dict, **_kwargs):
            self.mode = "upsert"
            self.payload = payload
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.mode == "select" and self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"organization_id": 1, "role": "owner"}])
            if self.mode == "select" and self.table_name == "org_role_change_requests":
                return SimpleNamespace(data=[{"id": 3, "organization_id": 1, "target_user_id": "user-2", "requested_role": "admin", "status": "pending"}])
            if self.mode == "update" and self.table_name == "org_role_change_requests":
                self.client.updated = True
                return SimpleNamespace(data=[self.payload])
            if self.mode == "upsert" and self.table_name == "org_memberships":
                self.client.membership_upserted = dict(self.payload or {})
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.updated = False
            self.membership_upserted = None

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(
        review_organization_role_request(
            _request("/api/organizations/1/role-requests/3/review", "POST"),
            "1",
            "3",
            OrganizationRoleRequestReviewRequest(decision="approve"),
        )
    )
    assert out["ok"] is True
    assert out["status"] == "approved"
    assert client.updated is True
    assert client.membership_upserted is not None
    assert client.membership_upserted.get("role") == "admin"


def test_create_role_request_blocks_admin_requesting_owner(monkeypatch):
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

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.mode == "select" and self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "admin"}])
            if self.mode == "insert" and self.table_name == "org_role_change_requests":
                self.client.inserted = True
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.inserted = False

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "admin-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            create_organization_role_request(
                _request("/api/organizations/1/role-requests", "POST"),
                "1",
                OrganizationRoleRequestCreateRequest(target_user_id="user-2", requested_role="owner"),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "owner_role_request_forbidden"
    else:
        assert False, "expected HTTPException"
    assert client.inserted is False


def test_review_role_request_blocks_self_review(monkeypatch):
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
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"organization_id": 1, "role": "owner"}])
            if self.table_name == "org_role_change_requests":
                return SimpleNamespace(data=[{"id": 3, "organization_id": 1, "target_user_id": "user-2", "requested_role": "admin", "status": "pending", "requested_by": "owner-user"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            review_organization_role_request(
                _request("/api/organizations/1/role-requests/3/review", "POST"),
                "1",
                "3",
                OrganizationRoleRequestReviewRequest(decision="approve"),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "self_review_not_allowed"
    else:
        assert False, "expected HTTPException"


def test_revoke_and_reissue_organization_invite(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.mode = "select"
            self.payload = None

        def select(self, *_args, **_kwargs):
            self.mode = "select"
            return self

        def update(self, payload: dict):
            self.mode = "update"
            self.payload = payload
            return self

        def insert(self, payload: dict):
            self.mode = "insert"
            self.payload = payload
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.mode == "select" and self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"organization_id": 1, "role": "owner"}])
            if self.mode == "select" and self.table_name == "org_invites":
                return SimpleNamespace(data=[{"id": 8, "organization_id": 1, "invited_email": "test@example.com", "role": "member", "accepted_at": None, "revoked_at": None}])
            if self.mode == "update" and self.table_name == "org_invites":
                self.client.updated = True
                return SimpleNamespace(data=[self.payload])
            if self.mode == "insert" and self.table_name == "org_invites":
                return SimpleNamespace(data=[{**(self.payload or {}), "id": 9}])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.updated = False

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    revoked = asyncio.run(revoke_organization_invite(_request("/api/organizations/1/invites/8/revoke", "POST"), "1", "8"))
    assert revoked["ok"] is True
    reissued = asyncio.run(reissue_organization_invite(_request("/api/organizations/1/invites/8/reissue", "POST"), "1", "8"))
    assert reissued["item"]["id"] == 9
    assert client.updated is True


def test_list_role_requests_filters_to_self_for_member(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.eq_calls: list[tuple[str, object]] = []

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, field: str, value):
            self.eq_calls.append((field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "member"}])
            if self.table_name == "org_role_change_requests":
                assert ("requested_by", "member-user") in self.eq_calls
                return SimpleNamespace(data=[{"id": 1, "requested_by": "member-user"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "member-user"

    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="member-user", role=Role.MEMBER, org_ids={1}, team_ids=set())

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.get_authz_context", _fake_authz)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(list_organization_role_requests(_request("/api/organizations/1/role-requests"), "1"))
    assert out["count"] == 1


def test_get_organization_oauth_policy_masks_sensitive_fields_for_member(monkeypatch):
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
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "member"}])
            if self.table_name == "org_oauth_policies":
                return SimpleNamespace(
                    data=[
                        {
                            "organization_id": 1,
                            "version": 2,
                            "policy_json": {
                                "allowed_providers": ["google"],
                                "required_providers": ["google"],
                                "approval_workflow": {"mode": "manual"},
                            },
                        }
                    ]
                )
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "member-user"

    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="member-user", role=Role.MEMBER, org_ids={1}, team_ids=set())

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.get_authz_context", _fake_authz)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(get_organization_oauth_policy(_request("/api/organizations/1/oauth-policy"), "1"))
    policy = out["item"]["policy_json"]
    assert policy.get("allowed_providers") == ["google"]
    assert "approval_workflow" not in policy


def test_update_organization_policy_upserts_for_admin(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.mode = "select"
            self.payload = None

        def select(self, *_args, **_kwargs):
            self.mode = "select"
            return self

        def upsert(self, payload: dict, **_kwargs):
            self.mode = "upsert"
            self.payload = payload
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.mode == "select" and self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "admin"}])
            if self.mode == "upsert" and self.table_name == "org_policies":
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "admin-user"

    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="admin-user", role=Role.ADMIN, org_ids={1}, team_ids=set())

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.get_authz_context", _fake_authz)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(
        update_organization_policy(
            _request("/api/organizations/1/policy", "PATCH"),
            "1",
            OrganizationPolicyUpdateRequest(policy_json={"allowed_services": ["notion"]}),
        )
    )
    assert isinstance(out.get("item"), dict)
    assert out["item"].get("policy_json", {}).get("allowed_services") == ["notion"]


def test_update_oauth_policy_rejects_required_not_in_allowed(monkeypatch):
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
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "owner"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "owner-user"

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    try:
        asyncio.run(
            update_organization_oauth_policy(
                _request("/api/organizations/1/oauth-policy", "PATCH"),
                "1",
                OrganizationOAuthPolicyUpdateRequest(
                    allowed_providers=["google"],
                    required_providers=["notion"],
                ),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_oauth_policy:required_not_subset_of_allowed"
    else:
        assert False, "expected HTTPException"


def test_get_organization_policy_returns_empty_default(monkeypatch):
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
            if self.table_name == "org_memberships":
                return SimpleNamespace(data=[{"role": "member"}])
            if self.table_name == "org_policies":
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "member-user"

    async def _fake_authz(_request: Request, **_kwargs) -> AuthzContext:
        return AuthzContext(user_id="member-user", role=Role.MEMBER, org_ids={1}, team_ids=set())

    monkeypatch.setattr("app.routes.organizations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.organizations.get_authz_context", _fake_authz)
    monkeypatch.setattr("app.routes.organizations.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr("app.routes.organizations.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))

    out = asyncio.run(get_organization_policy(_request("/api/organizations/1/policy"), "1"))
    assert out["item"]["policy_json"] == {}
