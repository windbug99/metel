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
                "output_schema": {"type": "tool_result", "service": "notion", "tool": "notion_query_data_source"},
            },
            {
                "id": "task2",
                "title": "페이지 생성",
                "task_type": "TOOL",
                "service": "notion",
                "tool_name": "notion_create_page",
                "depends_on": ["task1"],
                "payload": {"title_hint": "요약"},
                "output_schema": {"type": "tool_result", "service": "notion", "tool": "notion_create_page"},
            },
        ],
        "workflow_steps": ["조회", "생성"],
        "notes": ["tool_only"],
    }


def _sample_payload_invalid_contract_tasks():
    return {
        "requirements": ["최근 페이지 조회"],
        "target_services": ["notion"],
        "selected_tools": ["notion_search"],
        "tasks": [
            {
                "id": "task1",
                "title": "조회",
                "task_type": "TOOL",
                "service": "notion",
                "tool_name": "notion_search",
                "depends_on": [],
                "payload": {"query": "최근"},
                # output_schema intentionally missing
            }
        ],
        "workflow_steps": ["조회"],
        "notes": ["invalid_contract"],
    }


def test_try_build_agent_plan_with_llm_primary_openai(monkeypatch):
    async def _fake_request(**kwargs):
        assert kwargs["provider"] == "openai"
        return _sample_payload(), None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request)
    async def _fake_structured(**kwargs):
        assert kwargs["provider"] == "openai"
        return {"intent": "search", "slots": {"notion_search": {"query": "최근"}}}, None
    monkeypatch.setattr(
        "agent.planner_llm._request_structured_parse_with_provider",
        _fake_structured,
    )

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
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 최근 페이지 조회",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert calls == ["openai", "gemini", "openai", "gemini"]
    assert "llm_provider=gemini" in plan.notes


def test_try_build_agent_plan_with_llm_fallback_to_google_alias(monkeypatch):
    calls = []

    async def _fake_request(**kwargs):
        calls.append(kwargs["provider"])
        if kwargs["provider"] == "openai":
            return None, "http_429"
        return _sample_payload(), None

    monkeypatch.setattr(
        "agent.planner_llm.get_settings",
        lambda: _settings(
            llm_planner_fallback_provider="google",
            llm_planner_fallback_model="gemini-2.5-flash-lite",
        ),
    )
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request)
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 최근 페이지 조회",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert calls == ["openai", "google", "openai", "google"]
    assert "llm_provider=google" in plan.notes


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


def test_try_build_agent_plan_with_llm_rejects_invalid_task_contract(monkeypatch):
    async def _fake_request(**kwargs):
        _ = kwargs
        return _sample_payload_invalid_contract_tasks(), None

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
    assert any(note.startswith("tasks_contract_rejected:") for note in plan.notes)
    assert len(plan.tasks) >= 1
    assert any(task.output_schema for task in plan.tasks)


def test_try_build_agent_plan_with_llm_applies_structured_slots(monkeypatch):
    async def _fake_request_plan(**kwargs):
        _ = kwargs
        return {
            "requirements": ["Linear 이슈 생성"],
            "target_services": ["linear"],
            "selected_tools": ["linear_create_issue"],
            "tasks": [
                {
                    "id": "task_linear_create",
                    "title": "이슈 생성",
                    "task_type": "TOOL",
                    "service": "linear",
                    "tool_name": "linear_create_issue",
                    "depends_on": [],
                    "payload": {},
                    "output_schema": {"type": "tool_result", "service": "linear", "tool": "linear_create_issue"},
                }
            ],
            "workflow_steps": ["생성"],
            "notes": ["ok"],
        }, None

    async def _fake_request_structured(**kwargs):
        _ = kwargs
        return {
            "intent": "create",
            "service": "linear",
            "tool": "linear_create_issue",
            "workflow": ["의도 파악", "이슈 생성"],
            "confidence": 0.92,
            "slots": {
                "linear_create_issue": {
                    "title": "로그인 오류 수정",
                    "team_id": "team_123",
                    "priority": 2,
                }
            },
        }, None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request_plan)
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request_structured)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="Linear 이슈 생성: 제목 로그인 오류 수정, 팀 team_123",
            connected_services=["linear"],
        )
    )
    assert err is None
    assert plan is not None
    task = plan.tasks[0]
    assert task.payload.get("title") == "로그인 오류 수정"
    assert task.payload.get("team_id") == "team_123"
    assert task.payload.get("priority") == 2
    assert any(note == "structured_parser=llm" for note in plan.notes)
    assert any(note == "semantic_parse=llm" for note in plan.notes)
    assert any(note == "execution_decision=rule" for note in plan.notes)
    assert any(note == "structured_intent=create" for note in plan.notes)
    assert any(note == "structured_service=linear" for note in plan.notes)
    assert any(note == "structured_tool=linear_create_issue" for note in plan.notes)
    assert any(note == "structured_workflow_steps=2" for note in plan.notes)
    assert any(note == "structured_confidence=0.92" for note in plan.notes)


def test_try_build_agent_plan_with_llm_structured_parser_fallback(monkeypatch):
    async def _fake_request_plan(**kwargs):
        _ = kwargs
        return _sample_payload(), None

    async def _fake_request_structured(**kwargs):
        _ = kwargs
        return {"intent": "search", "slots": {}}, None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request_plan)
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request_structured)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="노션 최근 페이지 조회",
            connected_services=["notion"],
        )
    )
    assert err is None
    assert plan is not None
    assert any(note == "structured_parser=llm" for note in plan.notes)
    assert any(note == "structured_intent=search" for note in plan.notes)


def test_try_build_agent_plan_with_llm_rewrites_update_tasks_by_intent(monkeypatch):
    async def _fake_request_plan(**kwargs):
        _ = kwargs
        return {
            "requirements": ["linear 이슈 업데이트"],
            "target_services": ["linear"],
            "selected_tools": ["linear_search_issues"],
            "tasks": [
                {
                    "id": "task_linear_issues",
                    "title": "조회",
                    "task_type": "TOOL",
                    "service": "linear",
                    "tool_name": "linear_search_issues",
                    "depends_on": [],
                    "payload": {"first": 5},
                    "output_schema": {"type": "tool_result", "service": "linear", "tool": "linear_search_issues"},
                }
            ],
            "workflow_steps": ["조회"],
            "notes": [],
        }, None

    async def _fake_request_structured(**kwargs):
        _ = kwargs
        return {"intent": "update", "slots": {}}, None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request_plan)
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request_structured)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="linear 이슈 업데이트",
            connected_services=["linear"],
        )
    )
    assert err is None
    assert plan is not None
    assert any((task.tool_name or "") == "linear_update_issue" for task in plan.tasks if task.task_type == "TOOL")
    assert any(note == "tasks_rewritten_by_structured_intent:update" for note in plan.notes)


def test_try_build_agent_plan_with_llm_applies_keyed_slot_fallback(monkeypatch):
    async def _fake_request_plan(**kwargs):
        _ = kwargs
        return {
            "requirements": ["Linear 이슈 생성"],
            "target_services": ["linear"],
            "selected_tools": ["linear_create_issue"],
            "tasks": [
                {
                    "id": "task_linear_create",
                    "title": "이슈 생성",
                    "task_type": "TOOL",
                    "service": "linear",
                    "tool_name": "linear_create_issue",
                    "depends_on": [],
                    "payload": {},
                    "output_schema": {"type": "tool_result", "service": "linear", "tool": "linear_create_issue"},
                }
            ],
            "workflow_steps": ["생성"],
            "notes": [],
        }, None

    async def _fake_request_structured(**kwargs):
        _ = kwargs
        return {"intent": "create", "slots": {}}, None

    monkeypatch.setattr("agent.planner_llm.get_settings", lambda: _settings())
    monkeypatch.setattr("agent.planner_llm._request_plan_with_provider", _fake_request_plan)
    monkeypatch.setattr("agent.planner_llm._request_structured_parse_with_provider", _fake_request_structured)

    plan, err = asyncio.run(
        try_build_agent_plan_with_llm(
            user_text="Linear 이슈 생성 제목: 대시보드 로딩 지연 팀: 플랫폼 우선순위: 2",
            connected_services=["linear"],
        )
    )
    assert err is None
    assert plan is not None
    task = plan.tasks[0]
    assert task.payload.get("title") == "대시보드 로딩 지연"
    assert task.payload.get("team_id") == "플랫폼"
    assert task.payload.get("priority") == 2
    assert any(note == "keyed_slots_fallback_applied:linear_create_issue" for note in plan.notes)
