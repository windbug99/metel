from fastapi import HTTPException

from agent.registry import ToolDefinition
from agent.tool_runner import _build_path, _extract_path_params, _strip_path_params, execute_tool
from agent.tool_runner import _linear_query_and_variables
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


def test_linear_query_and_variables_list_teams():
    query, variables = _linear_query_and_variables("linear_list_teams", {"first": 7})
    assert "query Teams" in query
    assert variables == {"first": 7}


def test_linear_query_and_variables_update_issue():
    query, variables = _linear_query_and_variables(
        "linear_update_issue",
        {"issue_id": "issue-1", "title": "Updated", "state_id": "state-1"},
    )
    assert "mutation UpdateIssue" in query
    assert variables["input"]["id"] == "issue-1"
    assert variables["input"]["title"] == "Updated"
    assert variables["input"]["stateId"] == "state-1"


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
