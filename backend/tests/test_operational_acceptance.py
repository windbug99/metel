import asyncio
from types import SimpleNamespace

from agent.loop import run_agent_analysis
from agent.planner import build_agent_plan
from agent.registry import ToolDefinition, ToolRegistry
from agent.tool_runner import execute_tool
from agent.types import AgentExecutionResult, AgentExecutionStep


def _mockdocs_registry() -> ToolRegistry:
    tool = ToolDefinition(
        service="mockdocs",
        base_url="https://api.mockdocs.local",
        tool_name="mockdocs_list_items",
        description="List mockdocs items",
        method="GET",
        path="/v1/items",
        adapter_function="mockdocs_list_items",
        input_schema={"type": "object", "properties": {}, "required": []},
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )
    return ToolRegistry([tool])


def test_build_agent_plan_accepts_new_service_with_spec_only(monkeypatch):
    registry = _mockdocs_registry()
    monkeypatch.setattr("agent.service_resolver.load_registry", lambda: registry)
    monkeypatch.setattr("agent.planner.load_registry", lambda: registry)

    plan = build_agent_plan("mockdocs items list 보여줘", connected_services=["mockdocs"])
    assert plan.target_services == ["mockdocs"]
    assert "mockdocs_list_items" in plan.selected_tools


def test_run_agent_analysis_autonomous_accepts_new_service_with_spec_only(monkeypatch):
    registry = _mockdocs_registry()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = False

    async def _fake_try_build(**kwargs):
        # Force rule planner path to validate "spec-only service onboarding" behavior.
        return None, "llm_planner_disabled"

    async def _fake_autonomous_loop(user_id, plan, **kwargs):
        assert plan.target_services == ["mockdocs"]
        assert "mockdocs_list_items" in plan.selected_tools
        return AgentExecutionResult(
            success=True,
            user_message="mockdocs 조회 완료",
            summary="mockdocs 실행 성공",
            artifacts={"autonomous": "true"},
            steps=[AgentExecutionStep(name="autonomous_init", status="success", detail="tools=1")],
        )

    async def _fake_execute_agent_plan(user_id, plan):
        raise AssertionError("executor should not be called when autonomous succeeds")

    monkeypatch.setattr("agent.service_resolver.load_registry", lambda: registry)
    monkeypatch.setattr("agent.planner.load_registry", lambda: registry)
    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("mockdocs items list 보여줘", ["mockdocs"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(note.startswith("llm_planner_fallback:") for note in result.plan.notes)


def test_execute_tool_supports_spec_only_service_http_adapter(monkeypatch):
    registry = _mockdocs_registry()
    monkeypatch.setattr("agent.tool_runner.load_registry", lambda: registry)

    class _FakeResponse:
        status_code = 200
        text = '{"items":[{"id":"m1"}]}'

        def json(self):
            return {"items": [{"id": "m1"}]}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            assert url == "https://api.mockdocs.local/v1/items"
            assert params == {}
            return _FakeResponse()

        async def request(self, method, url, headers=None, json=None):
            raise AssertionError("request should not be called for GET")

        async def delete(self, url, headers=None):
            raise AssertionError("delete should not be called for GET")

    monkeypatch.setattr("agent.tool_runner.httpx.AsyncClient", _FakeClient)

    result = asyncio.run(execute_tool(user_id="user-1", tool_name="mockdocs_list_items", payload={}))
    assert result["ok"] is True
    assert result["data"]["items"][0]["id"] == "m1"
