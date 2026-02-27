import asyncio

from agent.stepwise_planner import try_build_stepwise_pipeline_plan


def test_try_build_stepwise_pipeline_plan_includes_catalog_id(monkeypatch):
    class _Settings:
        delete_operations_enabled = False
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_planner_fallback_provider = None
        llm_planner_fallback_model = None
        openai_api_key = None
        google_api_key = None

    async def _fake_request_json_with_provider(**_kwargs):
        return {
            "tasks": [
                {
                    "task_id": "step_1",
                    "sentence": "노션에서 페이지 검색",
                    "service": "notion",
                    "tool_name": "notion_search",
                }
            ]
        }

    monkeypatch.setattr("agent.stepwise_planner.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.stepwise_planner._request_json_with_provider", _fake_request_json_with_provider)
    monkeypatch.setattr(
        "agent.stepwise_planner._load_granted_scopes_map",
        lambda **_kwargs: {"notion": {"read_content", "insert_content"}},
    )

    plan = asyncio.run(
        try_build_stepwise_pipeline_plan(
            user_text="노션에서 페이지 검색해줘",
            connected_services=["notion"],
            user_id="u-stepwise-planner",
        )
    )
    assert plan is not None
    assert plan.tasks
    payload = plan.tasks[0].payload or {}
    ctx = payload.get("ctx") or {}
    assert str(ctx.get("catalog_id") or "").startswith("catalog_")


def test_try_build_stepwise_pipeline_plan_fallback_two_tasks(monkeypatch):
    class _Settings:
        delete_operations_enabled = False
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_planner_fallback_provider = None
        llm_planner_fallback_model = None
        openai_api_key = None
        google_api_key = None

    async def _fake_request_json_with_provider(**_kwargs):
        return None

    monkeypatch.setattr("agent.stepwise_planner.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.stepwise_planner._request_json_with_provider", _fake_request_json_with_provider)
    monkeypatch.setattr(
        "agent.stepwise_planner._load_granted_scopes_map",
        lambda **_kwargs: {"notion": {"read_content"}, "linear": {"read", "write"}},
    )
    monkeypatch.setattr(
        "agent.stepwise_planner.build_runtime_api_profile",
        lambda **_kwargs: {
            "enabled_api_ids": ["notion_search", "linear_create_issue"],
            "blocked_api_ids": [],
            "blocked_reason": [],
        },
    )

    plan = asyncio.run(
        try_build_stepwise_pipeline_plan(
            user_text="노션에서 페이지 검색해줘 그리고 리니어에 이슈 생성해줘",
            connected_services=["notion", "linear"],
            user_id="u-stepwise-planner-fallback",
        )
    )
    assert plan is not None
    assert plan.tasks
    payload = plan.tasks[0].payload or {}
    tasks = payload.get("tasks") or []
    assert len(tasks) == 2
    assert tasks[0]["tool_name"] == "notion_search"
    assert tasks[1]["tool_name"] == "linear_create_issue"


def test_try_build_stepwise_pipeline_plan_returns_none_for_empty_text():
    plan = asyncio.run(
        try_build_stepwise_pipeline_plan(
            user_text="   ",
            connected_services=["notion", "linear"],
            user_id="u-stepwise-planner-empty",
        )
    )
    assert plan is None


def test_try_build_stepwise_pipeline_plan_filters_oauth_tools_from_catalog(monkeypatch):
    class _Settings:
        delete_operations_enabled = False
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_planner_fallback_provider = None
        llm_planner_fallback_model = None
        openai_api_key = None
        google_api_key = None

    async def _fake_request_json_with_provider(**_kwargs):
        return {
            "tasks": [
                {
                    "task_id": "step_1",
                    "sentence": "토큰 검사",
                    "service": "notion",
                    "tool_name": "notion_oauth_token_introspect",
                }
            ]
        }

    monkeypatch.setattr("agent.stepwise_planner.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.stepwise_planner._request_json_with_provider", _fake_request_json_with_provider)
    monkeypatch.setattr(
        "agent.stepwise_planner._load_granted_scopes_map",
        lambda **_kwargs: {"notion": {"read_content"}},
    )
    monkeypatch.setattr(
        "agent.stepwise_planner.build_runtime_api_profile",
        lambda **_kwargs: {
            "enabled_api_ids": ["notion_search", "notion_oauth_token_introspect"],
            "blocked_api_ids": [],
            "blocked_reason": [],
        },
    )

    plan = asyncio.run(
        try_build_stepwise_pipeline_plan(
            user_text="노션 문서 검색해줘",
            connected_services=["notion"],
            user_id="u-stepwise-planner-oauth-filter",
        )
    )
    assert plan is not None
    payload = plan.tasks[0].payload or {}
    tasks = payload.get("tasks") or []
    assert tasks
    assert all(task["tool_name"] != "notion_oauth_token_introspect" for task in tasks)
    assert "notion_oauth_token_introspect" not in (plan.selected_tools or [])
