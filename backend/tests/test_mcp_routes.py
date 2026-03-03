import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from app.routes import mcp


class _Request:
    def __init__(self, body: dict):
        self._body = body
        self.state = SimpleNamespace(request_id="req-1")

    async def json(self):
        return self._body


class _Query:
    def __init__(self, rows: list[dict], count: int | None = None):
        self._rows = rows
        self.count = count

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows, count=self.count)


class _Supabase:
    def __init__(self, oauth_rows: list[dict] | None = None):
        self._oauth_rows = oauth_rows or []

    def table(self, name: str):
        if name == "oauth_tokens":
            return _Query(self._oauth_rows)
        return _Query([])


def test_mcp_list_tools_invalid_method():
    req = _Request({"jsonrpc": "2.0", "id": "1", "method": "nope"})
    response = asyncio.run(mcp.mcp_list_tools(req, authorization="Bearer metel_xxx"))
    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert "invalid_method" in payload


def test_mcp_list_tools_success_filters_phase1(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 1, "user_id": "user-1", "is_active": True}

    class _Tool:
        def __init__(self, service: str, name: str):
            self.service = service
            self._name = name

        def to_llm_tool(self):
            return {"name": self._name, "description": "", "input_schema": {"type": "object"}}

    class _Registry:
        def list_available_tools(self, **_kwargs):
            return [
                _Tool("notion", "notion_search"),
                _Tool("linear", "linear_list_issues"),
                _Tool("google", "google_calendar_list_events"),
            ]

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr(
        "app.routes.mcp.create_client",
        lambda *_args, **_kwargs: _Supabase(
            oauth_rows=[
                {"provider": "notion", "granted_scopes": ["insert_content"]},
                {"provider": "linear", "granted_scopes": ["read", "write"]},
            ]
        ),
    )

    req = _Request({"jsonrpc": "2.0", "id": "1", "method": "list_tools"})
    response = asyncio.run(mcp.mcp_list_tools(req, authorization="Bearer metel_xxx"))
    assert isinstance(response, dict)
    tools = response["result"]["tools"]
    names = [tool["name"] for tool in tools]
    assert "notion_search" in names
    assert "linear_list_issues" in names
    assert "google_calendar_list_events" not in names


def test_mcp_call_tool_rate_limited(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 1, "user_id": "user-1", "is_active": True}

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: True)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {"first": 5}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert "rate_limit_exceeded" in payload


def test_mcp_call_tool_success(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 11, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "linear"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"logged": False}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        assert tool_name == "linear_list_issues"
        assert payload == {"first": 3}
        return {"ok": True, "data": {"items": []}}

    def _fake_log_tool_call(**_kwargs):
        captured["logged"] = True

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {"first": 3}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    assert isinstance(response, dict)
    assert response["result"]["ok"] is True
    assert captured["logged"] is True


def test_mcp_call_tool_not_available_in_phase1(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 12, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "google"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "google_calendar_list_events", "arguments": {}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "tool_not_available_in_phase1" in payload


def test_mcp_call_tool_denied_by_api_key_allowed_tools(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 14, "user_id": "user-1", "is_active": True, "allowed_tools": ["notion_search"]}

    class _Tool:
        service = "linear"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "tool_not_allowed_for_api_key" in payload


def test_mcp_call_tool_maps_validation_error(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 13, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    async def _fake_execute_tool(**_kwargs):
        raise HTTPException(status_code=400, detail="notion_search:VALIDATION_REQUIRED:query")

    captured = {"error_code": None}

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "notion_search", "arguments": {}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "missing_required_field" in payload
    assert captured["error_code"] == "missing_required_field"


def test_mcp_call_tool_policy_blocked_high_risk_tool(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 21, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"error_code": None}

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "notion_delete_block", "arguments": {"block_id": "abc"}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "policy_blocked" in payload
    assert "high_risk_tool_blocked_by_default" in payload
    assert captured["error_code"] == "policy_blocked"


def test_mcp_call_tool_policy_blocked_archive_payload(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 22, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"error_code": None}

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "call_tool",
            "params": {"name": "notion_update_page", "arguments": {"page_id": "p1", "archived": True}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "policy_blocked" in payload
    assert "archive_or_trash_blocked_by_default" in payload
    assert captured["error_code"] == "policy_blocked"


def test_mcp_call_tool_resolves_notion_page_title(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 23, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"logged": False}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "object": "page",
                            "id": "pg-1",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "Roadmap"}],
                                }
                            },
                        }
                    ]
                },
            }
        assert tool_name == "notion_update_page"
        assert payload.get("page_id") == "pg-1"
        return {"ok": True, "data": {"updated": True}}

    def _fake_log_tool_call(**_kwargs):
        captured["logged"] = True

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "3",
            "method": "call_tool",
            "params": {"name": "notion_update_page", "arguments": {"page_title": "Roadmap", "properties": {}}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    assert isinstance(response, dict)
    assert response["result"]["ok"] is True
    assert captured["logged"] is True


def test_mcp_call_tool_resolver_ambiguous(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 24, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"error_code": None}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        assert tool_name == "notion_search"
        assert payload.get("query") == "Roadmap"
        return {
            "ok": True,
            "data": {
                "results": [
                    {"object": "page", "id": "pg-1", "properties": {}},
                    {"object": "page", "id": "pg-2", "properties": {}},
                ]
            },
        }

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "4",
            "method": "call_tool",
            "params": {"name": "notion_update_page", "arguments": {"page_title": "Roadmap", "properties": {}}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "resolve_ambiguous" in payload
    assert captured["error_code"] == "resolve_ambiguous"


def test_mcp_call_tool_retries_temporary_failure_then_success(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 31, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "linear"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    attempts = {"count": 0}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        attempts["count"] += 1
        assert user_id == "user-1"
        assert tool_name == "linear_list_issues"
        if attempts["count"] == 1:
            raise HTTPException(status_code=400, detail="linear_list_issues:RATE_LIMITED|status=429|message=retry")
        return {"ok": True, "data": {"items": []}}

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr(
        "app.routes.mcp.get_settings",
        lambda: SimpleNamespace(
            supabase_url="x",
            supabase_service_role_key="y",
            mcp_retry_max_retries=1,
            mcp_retry_backoff_ms=0,
        ),
    )
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", lambda **_kwargs: None)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "5",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {"first": 3}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    assert isinstance(response, dict)
    assert response["result"]["ok"] is True
    assert attempts["count"] == 2


def test_mcp_call_tool_does_not_retry_validation_error(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 32, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "notion"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    attempts = {"count": 0}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        attempts["count"] += 1
        assert user_id == "user-1"
        assert tool_name == "notion_search"
        raise HTTPException(status_code=400, detail="notion_search:VALIDATION_REQUIRED:query")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr(
        "app.routes.mcp.get_settings",
        lambda: SimpleNamespace(
            supabase_url="x",
            supabase_service_role_key="y",
            mcp_retry_max_retries=3,
            mcp_retry_backoff_ms=0,
        ),
    )
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", lambda **_kwargs: None)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "6",
            "method": "call_tool",
            "params": {"name": "notion_search", "arguments": {}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "missing_required_field" in payload
    assert attempts["count"] == 1


def test_mcp_call_tool_quota_exceeded(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 41, "user_id": "user-1", "is_active": True}

    captured = {"error_code": None}

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr(
        "app.routes.mcp.evaluate_daily_quota",
        lambda **_kwargs: SimpleNamespace(exceeded=True, scope="api_key", limit=100, used=100),
    )
    monkeypatch.setattr("app.routes.mcp.get_settings", lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"))
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "7",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {"first": 3}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "quota_exceeded" in payload
    assert "\"scope\":\"api_key\"" in payload
    assert captured["error_code"] == "quota_exceeded"


def test_mcp_call_tool_maps_upstream_temporary_failure(monkeypatch):
    async def _fake_auth(_authorization: str | None):
        return {"id": 42, "user_id": "user-1", "is_active": True}

    class _Tool:
        service = "linear"

    class _Registry:
        def get_tool(self, _name: str):
            return _Tool()

    captured = {"error_code": None}

    async def _fake_execute_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        assert tool_name == "linear_list_issues"
        raise HTTPException(status_code=400, detail="linear_list_issues:TOOL_FAILED|status=503|message=temporary")

    def _fake_log_tool_call(**kwargs):
        captured["error_code"] = kwargs.get("error_code")

    monkeypatch.setattr("app.routes.mcp._authenticate_api_key", _fake_auth)
    monkeypatch.setattr("app.routes.mcp._is_rate_limited", lambda **_kwargs: False)
    monkeypatch.setattr(
        "app.routes.mcp.get_settings",
        lambda: SimpleNamespace(
            supabase_url="x",
            supabase_service_role_key="y",
            mcp_retry_max_retries=0,
            mcp_retry_backoff_ms=0,
        ),
    )
    monkeypatch.setattr("app.routes.mcp.create_client", lambda *_args, **_kwargs: _Supabase())
    monkeypatch.setattr("app.routes.mcp.load_registry", lambda: _Registry())
    monkeypatch.setattr("app.routes.mcp.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("app.routes.mcp._log_tool_call", _fake_log_tool_call)

    req = _Request(
        {
            "jsonrpc": "2.0",
            "id": "8",
            "method": "call_tool",
            "params": {"name": "linear_list_issues", "arguments": {"first": 3}},
        }
    )
    response = asyncio.run(mcp.mcp_call_tool(req, authorization="Bearer metel_xxx"))
    payload = response.body.decode("utf-8")
    assert "upstream_temporary_failure" in payload
    assert "\"status\":503" in payload
    assert captured["error_code"] == "upstream_temporary_failure"
