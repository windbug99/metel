from fastapi import HTTPException

from agent.registry import ToolDefinition
from agent.tool_runner import _build_path, _extract_path_params, _strip_path_params, execute_tool
from agent.tool_runner import _validate_payload_by_schema
import asyncio


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
