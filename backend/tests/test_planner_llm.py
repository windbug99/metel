import asyncio
from types import SimpleNamespace

from agent.planner_llm import try_build_agent_plan_with_llm


def _settings(**kwargs):
    base = {
        "llm_planner_enabled": True,
        "openai_api_key": "openai-key",
        "google_api_key": "google-key",
        "llm_planner_provider": "openai",
        "llm_planner_model": "gpt-4o-mini",
        "llm_planner_fallback_provider": "gemini",
        "llm_planner_fallback_model": "gemini-2.5-flash-lite",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _sample_payload():
    return {
        "requirements": ["대상 데이터 조회"],
        "target_services": ["notion"],
        "selected_tools": ["notion_search"],
        "workflow_steps": ["요청 분석", "조회 실행"],
        "notes": ["ok"],
    }


def _sample_payload_tool_only_tasks():
    return {
        "requirements": ["데이터소스 조회", "요약 후 페이지 생성"],
        "target_services": ["notion"],
        "selected_tools": ["notion_query_data_source", "notion_create_page"],
        "tasks": [
            {
                "id": "task1",
                "title": "데이터소스 조회",
                "task_type": "TOOL",
                "service": "notion",
                "tool_name": "notion_query_data_source",
                "depends_on": [],
                "payload": {"data_source_id": "12345678-1234-1234-1234-1234567890ab"},
            },
            {
                "id": "task2",
                "title": "페이지 생성",
                "task_type": "TOOL",
                "service": "notion",
                "tool_name": "notion_create_page",
                "depends_on": ["task1"],
                "payload": {"title_hint": "요약"},
            },
        ],
        "workflow_steps": ["조회", "생성"],
        "notes": ["tool_only"],
    }


def test_try_build_agent_plan_with_llm_primary_openai(monkeypatch):
    async def _fake_request(**kwargs):
        assert kwargs["provider"] == "openai"
        return _sample_payload(), None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 최근 페이지 조회",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert "llm_provider=openai" in plan.notes


def test_try_build_agent_plan_with_llm_fallback_to_gemini(monkeypatch):
    calls = []

    async def _fake_request(**kwargs):
        calls.append(kwargs["provider"])
        if kwargs["provider"] == "openai":
            return None, "http_429"
        return _sample_payload(), None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 최근 페이지 조회",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert calls == ["openai", "gemini"]
    assert "llm_provider=gemini" in plan.notes


def test_try_build_agent_plan_with_llm_rehydrates_missing_llm_task(monkeypatch):
    async def _fake_request(**kwargs):
        _ = kwargs
        return _sample_payload_tool_only_tasks(), None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 5개를 3문장으로 요약해서 새 페이지 생성",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert any(task.task_type == "LLM" for task in plan.tasks)
    assert any(note == "tasks_rehydrated_with_rule_synthesis" for note in plan.notes)
