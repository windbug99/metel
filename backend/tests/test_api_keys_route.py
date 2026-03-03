import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.api_keys import UpdateApiKeyRequest, update_api_key


def _request() -> Request:
    scope = {"type": "http", "method": "PATCH", "path": "/api/api-keys/1", "headers": []}
    return Request(scope)


def test_update_api_key_updates_allowed_tools_and_name(monkeypatch):
    class _Query:
        def __init__(self, client):
            self.client = client
            self._mode = ""
            self._payload = None

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def update(self, payload: dict):
            self._mode = "update"
            self._payload = payload
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1}])
            if self._mode == "update":
                self.client.updated_payload = dict(self._payload or {})
                return SimpleNamespace(data=[{"id": 1}])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.updated_payload = None

        def table(self, _name: str):
            return _Query(self)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr(
        "app.routes.api_keys.load_registry",
        lambda: SimpleNamespace(
            list_tools=lambda: [
                SimpleNamespace(tool_name="notion_search", service="notion"),
                SimpleNamespace(tool_name="linear_list_issues", service="linear"),
            ]
        ),
    )

    body = UpdateApiKeyRequest(
        name="prod",
        allowed_tools=["notion_search"],
        policy_json={"allow_high_risk": True, "allowed_services": ["notion"], "deny_tools": ["linear_list_issues"]},
        is_active=True,
    )
    out = asyncio.run(update_api_key(_request(), "1", body))
    assert out["ok"] is True
    assert out["updated"] is True
    assert client.updated_payload is not None
    assert client.updated_payload["name"] == "prod"
    assert client.updated_payload["allowed_tools"] == ["notion_search"]
    assert client.updated_payload["policy_json"]["allow_high_risk"] is True
    assert client.updated_payload["policy_json"]["allowed_services"] == ["notion"]
    assert client.updated_payload["policy_json"]["deny_tools"] == ["linear_list_issues"]
    assert client.updated_payload["is_active"] is True
    assert client.updated_payload["revoked_at"] is None


def test_update_api_key_rejects_invalid_allowed_tool(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr(
        "app.routes.api_keys.load_registry",
        lambda: SimpleNamespace(
            list_tools=lambda: [
                SimpleNamespace(tool_name="notion_search", service="notion"),
                SimpleNamespace(tool_name="linear_list_issues", service="linear"),
            ]
        ),
    )

    body = UpdateApiKeyRequest(allowed_tools=["google_calendar_list_events"])
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert str(exc.detail).startswith("invalid_allowed_tool:")
    else:
        assert False, "expected HTTPException"


def test_update_api_key_not_found(monkeypatch):
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
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    try:
        asyncio.run(update_api_key(_request(), "999", UpdateApiKeyRequest(name="x")))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "api_key_not_found"
    else:
        assert False, "expected HTTPException"


def test_update_api_key_rejects_invalid_allowed_service(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr(
        "app.routes.api_keys.load_registry",
        lambda: SimpleNamespace(
            list_tools=lambda: [
                SimpleNamespace(tool_name="notion_search", service="notion"),
                SimpleNamespace(tool_name="linear_list_issues", service="linear"),
            ]
        ),
    )

    body = UpdateApiKeyRequest(policy_json={"allowed_services": ["google"]})
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_allowed_service:google"
    else:
        assert False, "expected HTTPException"


def test_update_api_key_rejects_policy_conflict_allowed_and_denied(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1, "allowed_tools": ["notion_search"], "policy_json": None}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr(
        "app.routes.api_keys.load_registry",
        lambda: SimpleNamespace(
            list_tools=lambda: [
                SimpleNamespace(tool_name="notion_search", service="notion"),
                SimpleNamespace(tool_name="linear_list_issues", service="linear"),
            ]
        ),
    )

    body = UpdateApiKeyRequest(
        allowed_tools=["notion_search"],
        policy_json={"deny_tools": ["notion_search"]},
    )
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 409
        assert str(exc.detail).startswith("policy_conflict:")
    else:
        assert False, "expected HTTPException"


def test_update_api_key_rejects_policy_conflict_tool_outside_allowed_services(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1, "allowed_tools": ["linear_list_issues"], "policy_json": None}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr(
        "app.routes.api_keys.load_registry",
        lambda: SimpleNamespace(
            list_tools=lambda: [
                SimpleNamespace(tool_name="notion_search", service="notion"),
                SimpleNamespace(tool_name="linear_list_issues", service="linear"),
            ]
        ),
    )

    body = UpdateApiKeyRequest(policy_json={"allowed_services": ["notion"]})
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 409
        assert str(exc.detail).startswith("policy_conflict:")
    else:
        assert False, "expected HTTPException"


def test_update_api_key_rejects_invalid_linear_team_policy_type(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1, "allowed_tools": None, "policy_json": None}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    body = UpdateApiKeyRequest(policy_json={"allowed_linear_team_ids": "team-a"})
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_policy_json:allowed_linear_team_ids"
    else:
        assert False, "expected HTTPException"


def test_update_api_key_rejects_linear_team_policy_without_linear_service(monkeypatch):
    class _Query:
        def __init__(self):
            self._mode = ""

        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "select":
                return SimpleNamespace(data=[{"id": 1, "allowed_tools": None, "policy_json": None}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    body = UpdateApiKeyRequest(policy_json={"allowed_services": ["notion"], "allowed_linear_team_ids": ["team-a"]})
    try:
        asyncio.run(update_api_key(_request(), "1", body))
    except HTTPException as exc:
        assert exc.status_code == 409
        assert str(exc.detail).startswith("policy_conflict:")
    else:
        assert False, "expected HTTPException"
