from agent.registry import load_registry, validate_registry_on_startup


def test_registry_loads_services_and_tools():
    registry = load_registry()
    services = registry.list_services()
    assert "notion" in services
    assert "spotify" in services
    assert "apple_music" in services

    tool = registry.get_tool("notion_search")
    assert tool.service == "notion"
    assert tool.method == "POST"
    comment_tool = registry.get_tool("notion_retrieve_comment")
    assert comment_tool.service == "notion"
    assert comment_tool.method == "GET"


def test_registry_filters_by_connected_services():
    registry = load_registry()
    notion_tools = registry.list_available_tools(connected_services=["notion"])
    assert notion_tools
    assert all(tool.service == "notion" for tool in notion_tools)


def test_registry_summary_and_startup_validation():
    registry = load_registry()
    summary = registry.summary()
    assert summary["service_count"] >= 2
    assert summary["tool_count"] >= 10

    startup_summary = validate_registry_on_startup()
    assert startup_summary["service_count"] == summary["service_count"]
    assert startup_summary["tool_count"] == summary["tool_count"]
