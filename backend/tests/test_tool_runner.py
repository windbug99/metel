from fastapi import HTTPException

from agent.registry import ToolDefinition
from agent.tool_runner import _build_path, _extract_path_params, _strip_path_params, execute_tool
from agent.tool_runner import _linear_query_and_variables
from agent.tool_runner import _GOOGLE_QUERY_KEY_MAP
from agent.tool_runner import _validate_payload_by_schema
import asyncio
from types import SimpleNamespace


def test_extract_path_params():
    params = _extract_path_params("/v1/blocks/{block_id}/children")
    assert params == ["block_id"]


def test_build_path():
    path = _build_path("/v1/pages/{page_id}/properties/{property_id}", {"page_id": "p1", "property_id": "title"})
    assert path == "/v1/pages/p1/properties/title"


def test_strip_path_params():
    payload = {"block_id": "b1", "page_size": 20}
    stripped = _strip_path_params("/v1/blocks/{block_id}/children", payload)
    assert stripped == {"page_size": 20}


def _dummy_tool() -> ToolDefinition:
    return ToolDefinition(
        service="notion",
        base_url="https://api.notion.com",
        tool_name="dummy_tool",
        description="dummy",
        method="POST",
        path="/v1/dummy/{id}",
        adapter_function="dummy",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["id"],
        },
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )


def test_validate_payload_by_schema_ok():
    _validate_payload_by_schema(_dummy_tool(), {"id": "abc", "page_size": 5})


def test_validate_payload_by_schema_error():
    try:
        _validate_payload_by_schema(_dummy_tool(), {"id": "abc", "page_size": 999})
    except HTTPException as exc:
        assert "VALIDATION_MAX:page_size" in str(exc.detail)
    else:
        assert False, "expected HTTPException"


def test_execute_tool_generic_adapter_adds_bearer_when_scope_required(monkeypatch):
    tool = ToolDefinition(
        service="mocksecure",
        base_url="https://api.mocksecure.local",
        tool_name="mocksecure_list_items",
        description="list items",
        method="GET",
        path="/v1/items",
        adapter_function="mocksecure_list_items",
        input_schema={"type": "object", "properties": {}, "required": []},
        required_scopes=("items:read",),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_ERROR"},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "mocksecure_list_items"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"ok":true}'

        def json(self):
            return {"ok": True}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            assert headers.get("Authorization") == "Bearer test-token"
            return _FakeResponse()

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("unexpected request call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "test-token")
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    result = asyncio.run(execute_tool("user-1", "mocksecure_list_items", {}))
    assert result["ok"] is True


def test_execute_tool_generic_adapter_maps_http_error(monkeypatch):
    tool = ToolDefinition(
        service="mockdocs",
        base_url="https://api.mockdocs.local",
        tool_name="mockdocs_list_items",
        description="list items",
        method="GET",
        path="/v1/items",
        adapter_function="mockdocs_list_items",
        input_schema={"type": "object", "properties": {}, "required": []},
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_ERROR"},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "mockdocs_list_items"
            return tool

    class _FakeResponse:
        status_code = 401
        text = '{"error":"unauthorized"}'

        def json(self):
            return {"error": "unauthorized"}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            return _FakeResponse()

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("unexpected request call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    try:
        asyncio.run(execute_tool("user-1", "mockdocs_list_items", {}))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "mockdocs_list_items:AUTH_ERROR"
    else:
        assert False, "expected HTTPException"


def test_execute_tool_google_maps_snake_case_query_params(monkeypatch):
    tool = ToolDefinition(
        service="google",
        base_url="https://www.googleapis.com/calendar/v3",
        tool_name="google_calendar_list_events",
        description="list events",
        method="GET",
        path="/calendars/{calendar_id}/events",
        adapter_function="google_calendar_list_events",
        input_schema={
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string"},
                "time_min": {"type": "string"},
                "time_max": {"type": "string"},
                "single_events": {"type": "boolean"},
                "order_by": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["calendar_id"],
        },
        required_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        idempotency_key_policy="none",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "google_calendar_list_events"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"items":[{"summary":"x"}]}'

        def json(self):
            return {"items": [{"summary": "x", "start": {"dateTime": "2026-02-24T10:00:00Z"}}]}

    captured = {"url": "", "params": None}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            captured["url"] = url
            captured["params"] = params
            assert headers.get("Authorization") == "Bearer google-token"
            return _FakeResponse()

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("unexpected request call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "google-token")
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    payload = {
        "calendar_id": "primary",
        "time_min": "2026-02-24T00:00:00Z",
        "time_max": "2026-02-25T00:00:00Z",
        "single_events": True,
        "order_by": "startTime",
        "max_results": 100,
    }
    result = asyncio.run(execute_tool("user-1", "google_calendar_list_events", payload))

    assert result["ok"] is True
    assert captured["url"].endswith("/calendars/primary/events")
    assert captured["params"]["timeMin"] == payload["time_min"]
    assert captured["params"]["timeMax"] == payload["time_max"]
    assert captured["params"]["singleEvents"] is True
    assert captured["params"]["orderBy"] == "startTime"
    assert captured["params"]["maxResults"] == 100
    for snake in ("time_min", "time_max", "single_events", "order_by", "max_results"):
        assert snake not in captured["params"]
    assert _GOOGLE_QUERY_KEY_MAP["time_min"] == "timeMin"


def test_execute_tool_google_filters_items_outside_time_range(monkeypatch):
    tool = ToolDefinition(
        service="google",
        base_url="https://www.googleapis.com/calendar/v3",
        tool_name="google_calendar_list_events",
        description="list events",
        method="GET",
        path="/calendars/{calendar_id}/events",
        adapter_function="google_calendar_list_events",
        input_schema={
            "type": "object",
            "properties": {"calendar_id": {"type": "string"}},
            "required": ["calendar_id"],
        },
        required_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        idempotency_key_policy="none",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "google_calendar_list_events"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"items":[]}'

        def json(self):
            return {
                "items": [
                    {"summary": "old", "start": {"dateTime": "2023-10-05T18:30:00+09:00"}},
                    {"summary": "today", "start": {"dateTime": "2026-02-25T18:30:00+09:00"}},
                ]
            }

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            _ = (url, headers, params)
            return _FakeResponse()

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("unexpected request call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "google-token")
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    payload = {
        "calendar_id": "primary",
        "time_min": "2026-02-24T15:00:00Z",
        "time_max": "2026-02-25T15:00:00Z",
        "time_zone": "Asia/Seoul",
    }
    result = asyncio.run(execute_tool("user-1", "google_calendar_list_events", payload))
    items = (result.get("data") or {}).get("items") or []
    assert len(items) == 1
    assert items[0]["summary"] == "today"


def test_execute_tool_google_primary_fallback_reads_selected_secondary_calendar(monkeypatch):
    tool = ToolDefinition(
        service="google",
        base_url="https://www.googleapis.com/calendar/v3",
        tool_name="google_calendar_list_events",
        description="list events",
        method="GET",
        path="/calendars/{calendar_id}/events",
        adapter_function="google_calendar_list_events",
        input_schema={
            "type": "object",
            "properties": {"calendar_id": {"type": "string"}},
            "required": ["calendar_id"],
        },
        required_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        idempotency_key_policy="none",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "google_calendar_list_events"
            return tool

    calls: list[str] = []

    class _Response:
        def __init__(self, code: int, payload: dict):
            self.status_code = code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            _ = (headers, params)
            calls.append(url)
            if url.endswith("/calendars/primary/events"):
                return _Response(200, {"items": []})
            if url.endswith("/users/me/calendarList"):
                return _Response(200, {"items": [{"id": "my-calendar-id", "selected": True}]})
            if url.endswith("/calendars/my-calendar-id/events"):
                return _Response(
                    200,
                    {"items": [{"summary": "secondary", "start": {"dateTime": "2026-02-25T20:30:00+09:00"}}]},
                )
            return _Response(404, {})

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("unexpected request call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "google-token")
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    payload = {
        "calendar_id": "primary",
        "time_min": "2026-02-24T15:00:00Z",
        "time_max": "2026-02-25T15:00:00Z",
        "time_zone": "Asia/Seoul",
    }
    result = asyncio.run(execute_tool("user-1", "google_calendar_list_events", payload))
    items = (result.get("data") or {}).get("items") or []
    assert len(items) == 1
    assert items[0]["summary"] == "secondary"
    assert any(url.endswith("/users/me/calendarList") for url in calls)
    assert any(url.endswith("/calendars/my-calendar-id/events") for url in calls)


def test_linear_query_and_variables_list_teams():
    query, variables = _linear_query_and_variables("linear_list_teams", {"first": 7})
    assert "query Teams" in query
    assert variables == {"first": 7}


def test_linear_query_and_variables_update_issue():
    query, variables = _linear_query_and_variables(
        "linear_update_issue",
        {"issue_id": "issue-1", "title": "Updated", "state_id": "state-1", "priority": 2},
    )
    assert "mutation UpdateIssue" in query
    assert variables["id"] == "issue-1"
    assert variables["input"]["title"] == "Updated"
    assert variables["input"]["stateId"] == "state-1"
    assert variables["input"]["priority"] == 2
    assert "id" not in variables["input"]


def test_linear_query_and_variables_archive_issue():
    query, variables = _linear_query_and_variables(
        "linear_update_issue",
        {"issue_id": "issue-1", "archived": True},
    )
    assert "mutation ArchiveIssue" in query
    assert "issueArchive" in query
    assert "issue {" not in query
    assert variables == {"id": "issue-1"}


def test_linear_query_and_variables_create_issue_with_priority():
    query, variables = _linear_query_and_variables(
        "linear_create_issue",
        {"team_id": "team-1", "title": "New issue", "description": "desc", "priority": 1},
    )
    assert "mutation CreateIssue" in query
    assert variables["input"]["teamId"] == "team-1"
    assert variables["input"]["title"] == "New issue"
    assert variables["input"]["description"] == "desc"
    assert variables["input"]["priority"] == 1


def test_linear_query_and_variables_create_comment():
    query, variables = _linear_query_and_variables(
        "linear_create_comment",
        {"issue_id": "issue-1", "body": "Need review"},
    )
    assert "mutation CreateComment" in query
    assert variables["input"]["issueId"] == "issue-1"
    assert variables["input"]["body"] == "Need review"


def test_linear_query_and_variables_search_issues_uses_title_filter():
    query, variables = _linear_query_and_variables("linear_search_issues", {"query": "OPT-35", "first": 7})
    assert "query SearchIssues" in query
    assert "title: { containsIgnoreCase: $query }" in query
    assert variables["query"] == "OPT-35"
    assert variables["first"] == 7


def test_linear_query_and_variables_list_issues_with_due_date_filter():
    query, variables = _linear_query_and_variables("linear_list_issues", {"first": 10, "due_date": "2026-02-27"})
    assert "query Issues" in query
    assert "filter: $filter" in query
    assert variables["first"] == 10
    assert variables["filter"] == {"dueDate": {"eq": "2026-02-27"}}


def test_execute_tool_web_fetch_url_text_extracts_plain_text(monkeypatch):
    tool = ToolDefinition(
        service="web",
        base_url="",
        tool_name="http_fetch_url_text",
        description="fetch url text",
        method="GET",
        path="",
        adapter_function="http_fetch_url_text",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
            },
            "required": ["url"],
        },
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "http_fetch_url_text"
            return tool

    class _FakeResponse:
        status_code = 200
        text = "<html><head><title>Hello</title></head><body><h1>Hi</h1><p>World</p></body></html>"
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://example.com/article"

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            assert url == "https://example.com/article"
            return _FakeResponse()

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    result = asyncio.run(execute_tool("user-1", "http_fetch_url_text", {"url": "https://example.com/article"}))
    assert result["ok"] is True
    assert result["data"]["title"] == "Hello"
    assert "Hi World" in result["data"]["text"]


def test_execute_tool_linear_graphql_error_contains_message_and_code(monkeypatch):
    tool = ToolDefinition(
        service="linear",
        base_url="https://api.linear.app",
        tool_name="linear_update_issue",
        description="update issue",
        method="POST",
        path="/graphql",
        adapter_function="linear_update_issue",
        input_schema={"type": "object", "properties": {"issue_id": {"type": "string"}}, "required": ["issue_id"]},
        required_scopes=("write",),
        idempotency_key_policy="optional",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "linear_update_issue"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"errors":[{"message":"Invalid issue id","extensions":{"code":"BAD_USER_INPUT"}}]}'

        def json(self):
            return {"errors": [{"message": "Invalid issue id", "extensions": {"code": "BAD_USER_INPUT"}}]}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse()

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "linear-token")
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    try:
        asyncio.run(execute_tool("user-1", "linear_update_issue", {"issue_id": "issue-1"}))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "TOOL_FAILED" in str(exc.detail)
        assert "Invalid issue id" in str(exc.detail)
        assert "BAD_USER_INPUT" in str(exc.detail)
    else:
        assert False, "expected HTTPException"


def test_execute_tool_notion_oauth_token_introspect_uses_basic_auth(monkeypatch):
    tool = ToolDefinition(
        service="notion",
        base_url="https://api.notion.com",
        tool_name="notion_oauth_token_introspect",
        description="introspect token",
        method="POST",
        path="/v1/oauth/token/introspect",
        adapter_function="notion_oauth_token_introspect",
        input_schema={"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_REQUIRED"},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "notion_oauth_token_introspect"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"active":true}'

        def json(self):
            return {"active": True}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert headers.get("Authorization", "").startswith("Basic ")
            assert json == {"token": "abc"}
            return _FakeResponse()

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr(
        "agent.tool_runner.get_settings",
        lambda: SimpleNamespace(
            notion_client_id="cid",
            notion_client_secret="csecret",
            notion_api_version="2025-09-03",
        ),
    )
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    result = asyncio.run(execute_tool("user-1", "notion_oauth_token_introspect", {"token": "abc"}))
    assert result["ok"] is True
    assert result["data"]["active"] is True


def test_execute_tool_notion_oauth_token_exchange_requires_oauth_config(monkeypatch):
    tool = ToolDefinition(
        service="notion",
        base_url="https://api.notion.com",
        tool_name="notion_oauth_token_exchange",
        description="exchange token",
        method="POST",
        path="/v1/oauth/token",
        adapter_function="notion_oauth_token_exchange",
        input_schema={"type": "object", "properties": {"grant_type": {"type": "string"}}, "required": ["grant_type"]},
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_REQUIRED"},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "notion_oauth_token_exchange"
            return tool

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr(
        "agent.tool_runner.get_settings",
        lambda: SimpleNamespace(
            notion_client_id="",
            notion_client_secret="",
            notion_api_version="2025-09-03",
        ),
    )

    try:
        asyncio.run(execute_tool("user-1", "notion_oauth_token_exchange", {"grant_type": "authorization_code"}))
    except HTTPException as exc:
        assert exc.status_code == 500
        assert exc.detail == "notion_oauth_config_missing"
    else:
        assert False, "expected HTTPException"


def test_execute_tool_notion_query_data_source_normalizes_sort_alias_and_cursor(monkeypatch):
    tool = ToolDefinition(
        service="notion",
        base_url="https://api.notion.com",
        tool_name="notion_query_data_source",
        description="query data source",
        method="POST",
        path="/v1/data_sources/{data_source_id}/query",
        adapter_function="notion_query_data_source",
        input_schema={
            "type": "object",
            "properties": {
                "data_source_id": {"type": "string"},
                "sorts": {"type": "array"},
                "start_cursor": {"type": "string"},
            },
            "required": ["data_source_id"],
        },
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )

    class _Registry:
        def get_tool(self, tool_name: str):
            assert tool_name == "notion_query_data_source"
            return tool

    class _FakeResponse:
        status_code = 200
        text = '{"results":[]}'

        def json(self):
            return {"results": []}

    captured = {"json": None}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            assert method == "POST"
            captured["json"] = json
            return _FakeResponse()

        async def get(self, url, headers=None, params=None):
            raise AssertionError("unexpected get call")

        async def delete(self, url, headers=None):
            raise AssertionError("unexpected delete call")

    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "notion-token")
    monkeypatch.setattr(
        "agent.tool_runner.get_settings",
        lambda: SimpleNamespace(
            notion_api_version="2025-09-03",
            notion_client_id="cid",
            notion_client_secret="sec",
            notion_default_parent_page_id=None,
        ),
    )
    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", lambda *args, **kwargs: _FakeClient())

    result = asyncio.run(
        execute_tool(
            "user-1",
            "notion_query_data_source",
            {
                "data_source_id": "ds-1",
                "sort": {"timestamp": "last_edited_time", "direction": "descending"},
                "start_cursor": {"bad": "cursor"},
            },
        )
    )

    assert result["ok"] is True
    assert isinstance(captured["json"].get("sorts"), list)
    assert captured["json"]["sorts"][0]["timestamp"] == "last_edited_time"
    assert "sort" not in captured["json"]
    assert "start_cursor" not in captured["json"]
