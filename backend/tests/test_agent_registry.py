from agent.registry import load_registry


def test_registry_loads_services_and_tools():
    registry = load_registry()
    services = registry.list_services()
    assert "notion" in services
    assert "spotify" in services

    tool = registry.get_tool("notion_search")
    assert tool.service == "notion"
    assert tool.method == "POST"


def test_registry_filters_by_connected_services():
    registry = load_registry()
    notion_tools = registry.list_available_tools(connected_services=["notion"])
    assert notion_tools
    assert all(tool.service == "notion" for tool in notion_tools)
