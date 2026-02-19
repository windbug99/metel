from agent.guide_retriever import get_planning_context, list_guide_services
from agent.registry import ToolDefinition, ToolRegistry
from agent.service_resolver import resolve_primary_service, resolve_services


def test_service_resolver_notion():
    services = resolve_services("노션에서 최근 페이지 3개 요약해줘", connected_services=["notion", "spotify"])
    assert services
    assert services[0] == "notion"


def test_service_resolver_spotify():
    service = resolve_primary_service("출근용 잔잔한 플레이리스트 만들어줘", connected_services=["spotify"])
    assert service == "spotify"


def test_guide_retriever():
    guides = list_guide_services()
    assert "notion" in guides
    assert "spotify" in guides
    context = get_planning_context("spotify", max_chars=800)
    assert "인증" in context


def test_service_resolver_dynamic_keyword_from_tool_spec(monkeypatch):
    tool = ToolDefinition(
        service="mockdocs",
        base_url="https://api.mockdocs.local",
        tool_name="mockdocs_list_items",
        description="MockDocs items list and document summary",
        method="GET",
        path="/v1/items",
        adapter_function="mockdocs_list_items",
        input_schema={"type": "object", "properties": {}, "required": []},
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )
    registry = ToolRegistry([tool])
    monkeypatch.setattr("agent.service_resolver.load_registry", lambda: registry)

    services = resolve_services("mockdocs items list 보여줘", connected_services=["mockdocs", "notion"])
    assert services
    assert services[0] == "mockdocs"
