import json

from agent.registry import ToolRegistry


def test_registry_loads_new_service_from_specs_dir(tmp_path):
    spec = {
        "service": "mockdocs",
        "version": "1.0.0",
        "base_url": "https://api.mockdocs.local",
        "auth": {"required_scopes": []},
        "tools": [
            {
                "tool_name": "mockdocs_list_items",
                "description": "List mock items",
                "method": "GET",
                "path": "/v1/items",
                "adapter_function": "mockdocs_list_items",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "required_scopes": [],
                "idempotency_key_policy": "none",
                "error_map": {"401": "AUTH_ERROR"},
            }
        ],
    }
    (tmp_path / "mockdocs.json").write_text(json.dumps(spec), encoding="utf-8")

    registry = ToolRegistry.load_from_dir(tmp_path)
    services = registry.list_services()
    assert services == ["mockdocs"]
    tool = registry.get_tool("mockdocs_list_items")
    assert tool.service == "mockdocs"
    assert tool.method == "GET"
