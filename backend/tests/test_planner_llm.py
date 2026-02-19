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
