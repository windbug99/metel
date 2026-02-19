import asyncio
import json

import httpx
from fastapi import HTTPException

from agent.registry import ToolDefinition, ToolRegistry
from agent.tool_runner import execute_tool


def _mockdocs_registry() -> ToolRegistry:
    list_tool = ToolDefinition(
        service="mockdocs",
        base_url="https://api.mockdocs.local",
        tool_name="mockdocs_list_items",
        description="List mockdocs items",
        method="GET",
        path="/v1/items",
        adapter_function="mockdocs_list_items",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []},
        required_scopes=("items:read",),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_ERROR"},
    )
    create_tool = ToolDefinition(
        service="mockdocs",
        base_url="https://api.mockdocs.local",
        tool_name="mockdocs_create_note",
        description="Create note in mockdocs",
        method="POST",
        path="/v1/notes",
        adapter_function="mockdocs_create_note",
        input_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
            "required": ["title"],
        },
        required_scopes=("items:write",),
        idempotency_key_policy="none",
        error_map={"401": "AUTH_ERROR"},
    )
    return ToolRegistry([list_tool, create_tool])


def test_spec_only_service_generic_adapter_with_mock_transport(monkeypatch):
    registry = _mockdocs_registry()
    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: registry)
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "mock-token")

    captured: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        body_text = request.content.decode("utf-8") if request.content else ""
        captured.append(
            {
                "method": request.method,
                "url": str(request.url),
                "auth": request.headers.get("Authorization", ""),
                "body": body_text,
                "query": dict(request.url.params),
            }
        )
        if request.url.path == "/v1/items":
            return httpx.Response(200, json={"items": [{"id": "i1"}]})
        if request.url.path == "/v1/notes":
            payload = json.loads(body_text or "{}")
            if not payload.get("title"):
                return httpx.Response(400, json={"error": "missing_title"})
            return httpx.Response(200, json={"id": "n1", "title": payload["title"]})
        return httpx.Response(404, json={"error": "not_found"})

    transport = httpx.MockTransport(_handler)
    original_async_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", _client_factory)

    list_result = asyncio.run(execute_tool("user-1", "mockdocs_list_items", {"limit": 3}))
    create_result = asyncio.run(
        execute_tool("user-1", "mockdocs_create_note", {"title": "hello", "content": "world"})
    )

    assert list_result["ok"] is True
    assert create_result["ok"] is True
    assert create_result["data"]["id"] == "n1"
    assert len(captured) == 2
    assert captured[0]["method"] == "GET"
    assert captured[0]["url"] == "https://api.mockdocs.local/v1/items?limit=3"
    assert captured[0]["auth"] == "Bearer mock-token"
    assert captured[1]["method"] == "POST"
    assert captured[1]["url"] == "https://api.mockdocs.local/v1/notes"
    assert captured[1]["auth"] == "Bearer mock-token"
    assert json.loads(captured[1]["body"])["title"] == "hello"


def test_spec_only_service_generic_adapter_maps_auth_error(monkeypatch):
    registry = _mockdocs_registry()
    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: registry)
    monkeypatch.setattr("agent.tool_runner._load_oauth_access_token", lambda user_id, provider: "bad-token")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = httpx.MockTransport(_handler)
    original_async_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", _client_factory)

    try:
        asyncio.run(execute_tool("user-1", "mockdocs_list_items", {}))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "mockdocs_list_items:AUTH_ERROR"
    else:
        assert False, "expected HTTPException"
