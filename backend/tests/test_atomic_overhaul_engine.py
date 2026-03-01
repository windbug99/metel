import asyncio

from agent.atomic_engine.engine import (
    _detect_service,
    _extract_linear_update_description,
    _extract_slot_value,
    _map_tool_error_code,
    _notion_first_result_id,
    _retrieve_tools_top_k,
    run_atomic_overhaul_analysis,
)
from agent.pending_action import PendingAction
from agent.types import AgentPlan, AgentRequirement, AgentTask


def test_atomic_overhaul_unsupported_request_returns_validation_error(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)

    result = asyncio.run(run_atomic_overhaul_analysis("오늘 날씨 어때?", ["notion"], "user-1"))
    assert result.ok is False
    assert result.stage == "validation"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "unsupported_request"


def test_atomic_overhaul_google_requires_calendar_id_clarification(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    calls = {"saved": False}

    def _fake_set_pending_action(**kwargs):
        _ = kwargs
        calls["saved"] = True
        return None

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.set_pending_action", _fake_set_pending_action)

    result = asyncio.run(run_atomic_overhaul_analysis("오늘 구글 캘린더 일정 조회해줘", ["google"], "user-2"))
    assert result.ok is False
    assert result.stage == "clarification"
    assert result.execution is not None
    assert result.execution.artifacts.get("missing_slot") == "calendar_id"
    assert "캘린더" in result.execution.user_message
    assert calls["saved"] is True


def test_atomic_overhaul_resumes_pending_and_executes_tool(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    plan = AgentPlan(
        user_text="오늘 일정 조회",
        requirements=[AgentRequirement(summary="google:list_events")],
        target_services=["google"],
        selected_tools=["google_calendar_list_events"],
        workflow_steps=["1", "2"],
        tasks=[
            AgentTask(
                id="task_google",
                title="google list",
                task_type="TOOL",
                service="google",
                tool_name="google_calendar_list_events",
                payload={"time_min": "2026-03-01T00:00:00+09:00", "time_max": "2026-03-01T23:59:59+09:00"},
            )
        ],
        notes=[],
    )
    pending = PendingAction(
        user_id="user-3",
        intent="list_events",
        action="google_calendar_list_events",
        task_id="task_google",
        plan=plan,
        plan_source="atomic_overhaul_v1_clarification2",
        collected_slots={},
        missing_slots=["calendar_id"],
        expires_at=9999999999.0,
    )

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-3"
        assert tool_name == "google_calendar_list_events"
        assert payload.get("calendar_id") == "primary"
        return {"ok": True, "data": {"items": [{"title": "팀 미팅"}]}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: pending)
    monkeypatch.setattr("agent.atomic_engine.engine.clear_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("primary", ["google"], "user-3"))
    assert result.ok is True
    assert result.stage == "execution"
    assert result.execution is not None
    assert result.execution.artifacts.get("verified") == "1"
    assert "요청 결과 1건" in result.execution.user_message


def test_atomic_overhaul_pending_cancel_clears_action(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    plan = AgentPlan(
        user_text="노션 페이지 수정",
        requirements=[AgentRequirement(summary="notion:update_page")],
        target_services=["notion"],
        selected_tools=["notion_update_page"],
        workflow_steps=["1", "2"],
        tasks=[],
        notes=[],
    )
    pending = PendingAction(
        user_id="user-cancel",
        intent="update_page",
        action="notion_update_page",
        task_id="task_notion",
        plan=plan,
        plan_source="atomic_overhaul_v1_clarification2",
        collected_slots={},
        missing_slots=["page_id"],
        expires_at=9999999999.0,
    )
    calls = {"cleared": False}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: pending)
    monkeypatch.setattr("agent.atomic_engine.engine.clear_pending_action", lambda _user_id: calls.__setitem__("cleared", True))

    result = asyncio.run(run_atomic_overhaul_analysis("취소", ["notion"], "user-cancel"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "pending_action_cancelled"
    assert calls["cleared"] is True


def test_atomic_overhaul_pending_expired_returns_error(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    plan = AgentPlan(
        user_text="linear 이슈 생성",
        requirements=[AgentRequirement(summary="linear:create_issue")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1", "2"],
        tasks=[],
        notes=[],
    )
    pending = PendingAction(
        user_id="user-expired",
        intent="create_issue",
        action="linear_create_issue",
        task_id="task_linear",
        plan=plan,
        plan_source="atomic_overhaul_v1_clarification2",
        collected_slots={},
        missing_slots=["team_id"],
        expires_at=0.0,
    )
    calls = {"cleared": False}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: pending)
    monkeypatch.setattr("agent.atomic_engine.engine.clear_pending_action", lambda _user_id: calls.__setitem__("cleared", True))

    result = asyncio.run(run_atomic_overhaul_analysis("팀: operate", ["linear"], "user-expired"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "pending_action_expired"
    assert calls["cleared"] is True


def test_atomic_overhaul_linear_list_runs_without_clarification(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-4"
        assert tool_name == "linear_list_issues"
        assert payload.get("first") == 3
        return {
            "ok": True,
            "data": {"nodes": [{"identifier": "OPS-1"}, {"identifier": "OPS-2"}, {"identifier": "OPS-3"}]},
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("linear 최근 이슈 3개 조회", ["linear"], "user-4"))
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("tool_name") == "linear_list_issues"
    assert result.execution.artifacts.get("verification_reason") == "list_verified"


def test_atomic_overhaul_understanding_uses_llm_payload(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "list_issues",
            "service": "linear",
            "slots": {"limit": 2},
            "missing_slots": [],
            "confidence": 0.91,
        }

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-5"
        assert tool_name == "linear_list_issues"
        assert payload.get("first") == 2
        return {"ok": True, "data": {"nodes": [{"identifier": "OPS-1"}, {"identifier": "OPS-2"}]}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("리니어 최근 이슈 2개 보여줘", ["linear"], "user-5"))
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("tool_name") == "linear_list_issues"


def test_atomic_overhaul_falls_back_to_rule_when_llm_low_confidence(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "list_issues",
            "service": "linear",
            "slots": {"limit": 3},
            "missing_slots": [],
            "confidence": 0.2,
        }

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-low-confidence"
        assert tool_name == "linear_list_issues"
        assert payload.get("first") == 3
        return {
            "ok": True,
            "data": {"nodes": [{"identifier": "OPS-1"}, {"identifier": "OPS-2"}, {"identifier": "OPS-3"}]},
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis("linear 최근 이슈 3개 검색해줘", ["linear"], "user-low-confidence")
    )
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("tool_name") == "linear_list_issues"


def test_map_tool_error_code_auth_required():
    assert _map_tool_error_code("linear_list_issues:AUTH_REQUIRED|status=401") == "auth_error"


def test_map_tool_error_code_validation():
    assert _map_tool_error_code("notion_update_page:BAD_REQUEST|status=400") == "validation_error"


def test_map_tool_error_code_default():
    assert _map_tool_error_code("timeout") == "tool_failed"


def test_atomic_overhaul_falls_back_to_rule_when_llm_intent_unmapped(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "rename_page_title",
            "service": "notion",
            "slots": {"page_title": "스프린트 보고서", "new_title": "스프린트 보고서 v2"},
            "missing_slots": [],
            "confidence": 0.92,
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr(
        "agent.atomic_engine.engine.execute_tool",
        lambda **kwargs: asyncio.sleep(0, result={"ok": True, "data": {"results": []}}),
    )

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            '노션에서 "스프린트 보고서" 페이지 제목을 "스프린트 보고서 v2"로 업데이트',
            ["notion"],
            "user-intent-fallback",
        )
    )
    assert result.ok is False
    assert result.stage == "clarification"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "clarification_needed"
    assert result.execution.artifacts.get("missing_slot") == "page_id"
    assert result.plan.tasks
    assert result.plan.tasks[0].tool_name == "notion_update_page"


def test_atomic_overhaul_resolves_notion_page_title_before_update(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "update_page",
            "service": "notion",
            "slots": {"page_title": "스프린트 보고서", "new_title": "스프린트 보고서 v2"},
            "missing_slots": [],
            "confidence": 0.95,
        }

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-notion-update"
        calls.append((tool_name, dict(payload)))
        if tool_name == "notion_search":
            assert payload.get("query") == "스프린트 보고서"
            return {"ok": True, "data": {"results": [{"object": "page", "id": "page-123"}]}}
        assert tool_name == "notion_update_page"
        assert payload.get("page_id") == "page-123"
        assert "page_title" not in payload
        assert "new_title" not in payload
        return {"ok": True, "data": {"id": "page-123"}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            '노션에서 "스프린트 보고서" 페이지 제목을 "스프린트 보고서 v2"로 업데이트',
            ["notion"],
            "user-notion-update",
        )
    )
    assert result.ok is True
    assert [name for name, _ in calls][:2] == ["notion_search", "notion_update_page"]


def test_atomic_overhaul_routes_notion_body_update_to_append_and_prefetches_block(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-notion-append"
        calls.append((tool_name, dict(payload)))
        if tool_name == "notion_search":
            assert payload.get("query") == "스프린트 보고서 v2"
            return {"ok": True, "data": {"results": [{"object": "page", "id": "page-456"}]}}
        assert tool_name == "notion_append_block_children"
        assert payload.get("block_id") == "page-456"
        assert isinstance(payload.get("children"), list)
        assert "page_title" not in payload
        assert "content" not in payload
        return {"ok": True, "data": {"id": "page-456"}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            '노션에서 "스프린트 보고서 v2" 페이지 본문 업데이트: 이번 주 배포 리스크와 대응 현황을 3줄로 추가',
            ["notion"],
            "user-notion-append",
        )
    )
    assert result.ok is True
    assert [name for name, _ in calls][:2] == ["notion_search", "notion_append_block_children"]


def test_atomic_overhaul_linear_issue_key_update_without_issue_keyword(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-linear-key"
        calls.append((tool_name, dict(payload)))
        if tool_name == "linear_search_issues":
            return {
                "ok": True,
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-46",
                                "identifier": "OPT-46",
                                "title": "테스트 이슈",
                                "description": "기존 설명",
                                "url": "https://linear.app/issue/OPT-46",
                                "state": {"id": "state-backlog", "name": "Backlog"},
                            }
                        ]
                    }
                },
            }
        assert tool_name == "linear_update_issue"
        assert payload.get("issue_id") == "issue-46"
        assert isinstance(payload.get("description"), str)
        return {
            "ok": True,
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {"identifier": "OPT-46", "url": "https://linear.app/issue/OPT-46"},
                }
            },
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            "openweather API 사용방법을 정리해서 linear OPT-46 설명에 추가해줘",
            ["linear"],
            "user-linear-key",
        )
    )
    assert result.ok is True
    assert [name for name, _ in calls][:2] == ["linear_search_issues", "linear_update_issue"]


def test_atomic_overhaul_linear_state_change_resolves_state_name(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-linear-state"
        calls.append((tool_name, dict(payload)))
        if tool_name == "linear_search_issues":
            return {
                "ok": True,
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-283",
                                "identifier": "OPT-283",
                                "title": "상태 변경 테스트",
                                "description": "기존 설명",
                                "url": "https://linear.app/issue/OPT-283",
                                "team": {"id": "team-opt"},
                                "state": {"id": "state-backlog", "name": "Backlog"},
                            }
                        ]
                    }
                },
            }
        if tool_name == "linear_list_workflow_states":
            return {
                "ok": True,
                "data": {
                    "workflowStates": {
                        "nodes": [
                            {"id": "state-backlog", "name": "Backlog", "team": {"id": "team-opt"}},
                            {"id": "state-todo", "name": "Todo", "team": {"id": "team-opt"}},
                        ]
                    }
                },
            }
        assert tool_name == "linear_update_issue"
        assert payload.get("issue_id") == "issue-283"
        assert payload.get("state_id") == "state-todo"
        assert "description" not in payload
        return {
            "ok": True,
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {"identifier": "OPT-283", "url": "https://linear.app/issue/OPT-283"},
                }
            },
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            "linear에서 OPT-283 이슈의 상태를 Todo로 변경",
            ["linear"],
            "user-linear-state",
        )
    )
    assert result.ok is True
    assert result.execution is not None
    assert "작업결과" in result.execution.user_message
    assert "링크" in result.execution.user_message
    assert "https://linear.app/issue/OPT-283" in result.execution.user_message


def test_extract_linear_update_description_prefers_append_tail_multiline():
    text = 'linear에서 OPT-283 이슈의 설명에 다음 메모를 추가해줘.\n메모 내용 첨부'
    out = _extract_linear_update_description(text)
    assert out == "메모 내용 첨부"


def test_extract_linear_update_description_preserves_newlines_after_period():
    text = "linear에서 OPT-283 이슈의 설명에 다음 메모를 추가해줘.\n서비스: 온라인 쇼핑 큐레이션 앱\n\n## 여정 단계"
    out = _extract_linear_update_description(text)
    assert out == "서비스: 온라인 쇼핑 큐레이션 앱\n\n## 여정 단계"


def test_extract_linear_update_description_prefers_replace_tail_multiline():
    text = 'linear에서 OPT-283 이슈의 설명에 다음 메모를 수정해줘.\n메모 내용 첨부'
    out = _extract_linear_update_description(text)
    assert out == "메모 내용 첨부"


def test_extract_linear_update_description_prefers_replace_tail_with_ro_particle():
    text = "linear에서 OPT-283 이슈의 설명에 다음 메모로 수정해줘.\n프로젝트: 스마트 업무 관리 플랫폼"
    out = _extract_linear_update_description(text)
    assert out == "프로젝트: 스마트 업무 관리 플랫폼"


def test_extract_linear_update_description_preserves_markdown_blocks():
    text = (
        "linear에서 OPT-283 이슈의 설명에 다음 메모로 수정해줘.\n"
        "> 프로젝트: 스마트 업무 관리 플랫폼\n"
        "> 작성일: 2026-02-26\n\n"
        "## 기능 요구사항\n"
        "| 항목 | 요구사항 |\n"
        "| --- | --- |\n"
        "| 성능 | 페이지 로딩 2초 이내 |"
    )
    out = _extract_linear_update_description(text)
    assert out is not None
    assert out.startswith("> 프로젝트: 스마트 업무 관리 플랫폼")
    assert "\n## 기능 요구사항\n" in out
    assert "| 항목 | 요구사항 |" in out


def test_detect_service_prefers_linear_when_issue_key_and_google_word_coexist():
    text = "linear에서 OPT-283 이슈 설명을 수정해줘. Google, Kakao 소셜 로그인 지원 항목 포함"
    out = _detect_service(text, ["linear", "google", "notion"])
    assert out == "linear"


def test_atomic_overhaul_linear_issue_key_append_without_linear_keyword(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    calls: list[tuple[str, dict]] = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-linear-append-no-service-token"
        calls.append((tool_name, dict(payload)))
        if tool_name == "linear_search_issues":
            return {
                "ok": True,
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-283",
                                "identifier": "OPT-283",
                                "title": "수정 테스트",
                                "description": "기존 설명",
                                "url": "https://linear.app/issue/OPT-283",
                                "state": {"id": "state-backlog", "name": "Backlog"},
                            }
                        ]
                    }
                },
            }
        assert tool_name == "linear_update_issue"
        assert payload.get("issue_id") == "issue-283"
        assert isinstance(payload.get("description"), str)
        assert "추가 테스트 문장" in str(payload.get("description"))
        return {
            "ok": True,
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {"identifier": "OPT-283", "url": "https://linear.app/issue/OPT-283"},
                }
            },
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis(
            'OPT-283 설명 끝에 "추가 테스트 문장"을 append 해줘',
            ["linear", "notion"],
            "user-linear-append-no-service-token",
        )
    )
    assert result.ok is True
    assert [name for name, _ in calls][:2] == ["linear_search_issues", "linear_update_issue"]


def test_atomic_overhaul_notion_create_page_without_database_clarification(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-notion-create"
        assert tool_name == "notion_create_page"
        assert payload.get("parent") == {"workspace": True}
        properties = payload.get("properties") or {}
        assert isinstance(properties, dict)
        return {"ok": True, "data": {"id": "page-new", "url": "https://notion.so/page-new"}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(
        run_atomic_overhaul_analysis("노션에 페이지 생성 제목: stage6 테스트", ["notion"], "user-notion-create")
    )
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("tool_name") == "notion_create_page"


def test_atomic_overhaul_slot_policy_hard_ask_requires_calendar_id(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.set_pending_action", lambda **kwargs: None)

    result = asyncio.run(run_atomic_overhaul_analysis("오늘 구글 캘린더 일정 조회해줘", ["google"], "user-hard-ask"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "clarification_needed"
    assert result.execution.artifacts.get("missing_slot") == "calendar_id"


def test_atomic_overhaul_slot_policy_safe_default_autofills_notion_parent(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-safe-default"
        assert tool_name == "notion_create_page"
        assert payload.get("parent") == {"workspace": True}
        return {"ok": True, "data": {"id": "page-safe", "url": "https://notion.so/page-safe"}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("노션 페이지 생성", ["notion"], "user-safe-default"))
    assert result.ok is True
    assert result.execution is not None
    assert "가정값" in result.execution.user_message


def test_atomic_overhaul_slot_policy_soft_confirm_blocks_destructive_without_approval(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "delete_issue",
            "service": "linear",
            "slots": {"issue_id": "OPT-45"},
            "missing_slots": [],
            "confidence": 0.95,
        }

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.set_pending_action", lambda **kwargs: None)

    result = asyncio.run(run_atomic_overhaul_analysis("linear OPT-45 삭제", ["linear"], "user-soft-confirm"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "risk_gate_blocked"
    assert result.execution.artifacts.get("missing_slot") == "approval_confirmed"


def test_extract_slot_value_parses_prefixed_team_and_title():
    assert _extract_slot_value("팀: operate", "team_id") == "operate"
    assert _extract_slot_value("제목: stage6 자동화 테스트 이슈", "title") == "stage6 자동화 테스트 이슈"


def test_notion_first_result_id_picks_page_object():
    payload = {
        "data": {
            "results": [
                {"object": "database", "id": "db-1"},
                {"object": "page", "id": "page-1"},
            ]
        }
    }
    assert _notion_first_result_id(payload) == "page-1"


def test_atomic_overhaul_tool_retrieval_top_k_from_specs():
    tools = _retrieve_tools_top_k(service="linear", intent="list_issues", top_k=3)
    assert len(tools) == 3
    assert tools[0] == "linear_list_issues"


def test_atomic_overhaul_plan_contains_top_k_selected_tools(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "list_issues",
            "service": "linear",
            "slots": {"limit": 2},
            "missing_slots": [],
            "confidence": 0.91,
        }

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        _ = user_id
        _ = payload
        return {"ok": True, "data": {"nodes": [{"identifier": "OPS-1"}, {"identifier": "OPS-2"}]}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("리니어 최근 이슈 2개 보여줘", ["linear"], "user-6"))
    assert result.ok is True
    assert result.plan.selected_tools
    assert len(result.plan.selected_tools) == 3
    assert result.plan.selected_tools[0] == "linear_list_issues"


def test_atomic_overhaul_verification_retry_once(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "list_issues",
            "service": "linear",
            "slots": {"limit": 2},
            "missing_slots": [],
            "confidence": 0.91,
        }

    calls = {"count": 0}

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        _ = (user_id, tool_name, payload)
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": True, "data": {"nodes": [{"identifier": "OPS-1"}]}}
        return {"ok": True, "data": {"nodes": [{"identifier": "OPS-1"}, {"identifier": "OPS-2"}]}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("리니어 최근 이슈 2개 보여줘", ["linear"], "user-7"))
    assert result.ok is True
    assert calls["count"] == 2
    assert result.execution is not None
    assert result.execution.artifacts.get("verification_retry_attempted") == "1"
    assert result.execution.artifacts.get("verification_reason") == "list_verified"


def test_atomic_overhaul_risk_gate_blocks_without_approval(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    calls = {"saved": False}

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "delete_page",
            "service": "notion",
            "slots": {"page_id": "page-123"},
            "missing_slots": [],
            "confidence": 0.95,
        }

    def _fake_set_pending_action(**kwargs):
        _ = kwargs
        calls["saved"] = True
        return None

    async def _forbidden_execute_tool(user_id: str, tool_name: str, payload: dict):
        _ = (user_id, tool_name, payload)
        raise AssertionError("execute_tool must not run when approval is missing")

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.set_pending_action", _fake_set_pending_action)
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _forbidden_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("노션 페이지 삭제해줘", ["notion"], "user-8"))
    assert result.ok is False
    assert result.stage == "clarification"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "risk_gate_blocked"
    assert result.execution.artifacts.get("missing_slot") == "approval_confirmed"
    assert calls["saved"] is True


def test_atomic_overhaul_risk_gate_allows_with_approval(monkeypatch):
    class _Settings:
        pending_action_ttl_seconds = 900
        llm_planner_provider = "openai"
        llm_planner_model = "gpt-4o-mini"
        llm_request_timeout_sec = 20
        openai_api_key = "test-key"
        google_api_key = None

    async def _fake_request_understanding_with_provider(**kwargs):
        _ = kwargs
        return {
            "request_type": "saas_execution",
            "intent": "delete_page",
            "service": "notion",
            "slots": {"page_id": "page-123", "approval_confirmed": "yes"},
            "missing_slots": [],
            "confidence": 0.95,
        }

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-9"
        assert tool_name == "notion_update_page"
        assert payload.get("page_id") == "page-123"
        assert payload.get("in_trash") is True
        return {"ok": True, "data": {"id": "page-123", "url": "https://notion.so/page-123"}}

    monkeypatch.setattr("agent.atomic_engine.engine.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.atomic_engine.engine.get_pending_action", lambda _user_id: None)
    monkeypatch.setattr(
        "agent.atomic_engine.engine._request_understanding_with_provider",
        _fake_request_understanding_with_provider,
    )
    monkeypatch.setattr("agent.atomic_engine.engine.execute_tool", _fake_execute_tool)

    result = asyncio.run(run_atomic_overhaul_analysis("노션 페이지 삭제 승인", ["notion"], "user-9"))
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("tool_name") == "notion_update_page"
