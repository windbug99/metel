import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from app.routes.api_keys import list_api_keys
from app.routes.audit import export_audit_events, list_audit_events
from app.routes.tool_calls import list_tool_calls


def _request(path: str) -> Request:
    scope = {"type": "http", "method": "GET", "path": path, "headers": []}
    return Request(scope)


def test_list_api_keys_enforces_user_scope(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.ops: list[tuple[str, str, object]] = []

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def execute(self):
            self.client.logs.append((self.table_name, list(self.ops)))
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.logs: list[tuple[str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-a"

    monkeypatch.setattr("app.routes.api_keys.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.api_keys.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.api_keys.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(list_api_keys(_request("/api/api-keys")))
    assert out["count"] == 0
    assert ("api_keys", [("eq", "user_id", "user-a")]) in client.logs


def test_list_tool_calls_enforces_user_scope(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.selected = ""
            self.ops: list[tuple[str, str, object]] = []

        def select(self, fields: str, **_kwargs):
            self.selected = fields
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def gte(self, field: str, value):
            self.ops.append(("gte", field, value))
            return self

        def lte(self, field: str, value):
            self.ops.append(("lte", field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            self.client.logs.append((self.table_name, self.selected, list(self.ops)))
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.logs: list[tuple[str, str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-a"

    monkeypatch.setattr("app.routes.tool_calls.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.tool_calls.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.tool_calls.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_tool_calls(
            _request("/api/tool-calls"),
            limit=20,
            status="all",
            tool_name="",
            api_key_id=None,
            from_="",
            to="",
        )
    )
    assert out["count"] == 0
    tool_calls_scoped = [item for item in client.logs if item[0] == "tool_calls"]
    api_keys_scoped = [item for item in client.logs if item[0] == "api_keys"]
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in tool_calls_scoped)
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in api_keys_scoped)


def test_list_audit_events_enforces_user_scope(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.selected = ""
            self.ops: list[tuple[str, str, object]] = []

        def select(self, fields: str, **_kwargs):
            self.selected = fields
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def gte(self, field: str, value):
            self.ops.append(("gte", field, value))
            return self

        def lte(self, field: str, value):
            self.ops.append(("lte", field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            self.client.logs.append((self.table_name, self.selected, list(self.ops)))
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.logs: list[tuple[str, str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-a"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_audit_events(
            _request("/api/audit/events"),
            limit=20,
            status="all",
            tool_name="",
            api_key_id=None,
            error_code="",
            from_="",
            to="",
        )
    )
    assert out["count"] == 0
    tool_calls_scoped = [item for item in client.logs if item[0] == "tool_calls"]
    api_keys_scoped = [item for item in client.logs if item[0] == "api_keys"]
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in tool_calls_scoped)
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in api_keys_scoped)


def test_export_audit_events_enforces_user_scope(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.selected = ""
            self.ops: list[tuple[str, str, object]] = []

        def select(self, fields: str, **_kwargs):
            self.selected = fields
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def gte(self, field: str, value):
            self.ops.append(("gte", field, value))
            return self

        def lte(self, field: str, value):
            self.ops.append(("lte", field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            self.client.logs.append((self.table_name, self.selected, list(self.ops)))
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.logs: list[tuple[str, str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-a"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    response = asyncio.run(
        export_audit_events(
            _request("/api/audit/export"),
            format="jsonl",
            limit=20,
            status="all",
            tool_name="",
            api_key_id=None,
            error_code="",
            from_="",
            to="",
        )
    )
    assert response.media_type == "application/x-ndjson"
    tool_calls_scoped = [item for item in client.logs if item[0] == "tool_calls"]
    api_keys_scoped = [item for item in client.logs if item[0] == "api_keys"]
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in tool_calls_scoped)
    assert any(("eq", "user_id", "user-a") in ops for _, _, ops in api_keys_scoped)
