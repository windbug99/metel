import asyncio

from fastapi import HTTPException

from agent.intent_contract import IntentPayload
from agent.orchestrator_v2 import (
    MODE_LLM_ONLY,
    MODE_LLM_THEN_SKILL,
    MODE_SKILL_THEN_LLM,
    _build_calendar_pipeline_plan,
    _extract_linear_update_description_text,
    _parse_router_payload,
    build_intent_json,
    execute_from_intent,
    route_request_v2,
    try_run_v2_orchestration,
)


def test_route_request_v2_defaults_to_llm_only():
    decision = route_request_v2("오늘 서울 날씨 알려줘", ["notion", "linear"])
    assert decision.mode == MODE_LLM_ONLY


def test_build_calendar_pipeline_plan_contains_pipeline_dag_task():
    plan = _build_calendar_pipeline_plan("구글캘린더 회의를 notion과 linear에 등록")
    assert plan.tasks
    assert plan.tasks[0].task_type == "PIPELINE_DAG"
    payload = plan.tasks[0].payload
    assert isinstance(payload.get("pipeline"), dict)
    assert payload["pipeline"]["pipeline_id"] == "google_calendar_to_notion_linear_v1"


def test_try_run_v2_orchestration_uses_pipeline_dag_path_when_enabled(monkeypatch):
    class _Settings:
        skill_runner_v2_enabled = True

    async def _fake_execute_agent_plan(user_id: str, plan):
        _ = user_id
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        return type(
            "_Exec",
            (),
            {
                "success": True,
                "summary": "DAG 파이프라인 실행 완료",
                "user_message": "ok",
                "artifacts": {"router_mode": "PIPELINE_DAG"},
                "steps": [],
            },
        )()

    async def _forbidden_build_intent_json(**kwargs):
        _ = kwargs
        raise AssertionError("build_intent_json should not run on DAG fast-path")

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2.validate_all_contracts", lambda: (9, {}))
    monkeypatch.setattr("agent.orchestrator_v2.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.orchestrator_v2.build_intent_json", _forbidden_build_intent_json)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="구글캘린더 오늘 회의를 notion 페이지로 만들고 linear 이슈로 등록해줘",
            connected_services=["google", "notion", "linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_parse_router_payload_accepts_valid_skill_mode():
    payload = {
        "mode": "LLM_THEN_SKILL",
        "reason": "write_to_notion",
        "selected_tools": ["notion_create_page"],
        "arguments": {},
    }
    decision = _parse_router_payload(payload, ["notion"])
    assert decision is not None
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert decision.selected_tools == ["notion_create_page"]


def test_parse_router_payload_accepts_skill_name_without_selected_tools():
    payload = {
        "mode": "LLM_THEN_SKILL",
        "reason": "write_to_notion",
        "skill_name": "notion.page_create",
        "selected_tools": [],
        "arguments": {},
    }
    decision = _parse_router_payload(payload, ["notion"])
    assert decision is not None
    assert decision.skill_name == "notion.page_create"
    assert "notion_create_page" in decision.selected_tools


def test_parse_router_payload_rejects_extra_keys():
    payload = {
        "mode": "LLM_ONLY",
        "reason": "x",
        "selected_tools": [],
        "arguments": {},
        "unexpected": "value",
    }
    decision = _parse_router_payload(payload, ["notion"])
    assert decision is None


def test_parse_router_payload_derives_target_service_from_skill_name():
    payload = {
        "mode": "LLM_THEN_SKILL",
        "reason": "update_linear",
        "skill_name": "linear.issue_update",
        "selected_tools": [],
        "arguments": {"linear_issue_ref": "OPT-35"},
    }
    decision = _parse_router_payload(payload, ["linear"])
    assert decision is not None
    assert decision.target_services == ["linear"]


def test_parse_router_payload_rejects_unallowed_tool():
    payload = {
        "mode": "LLM_THEN_SKILL",
        "reason": "bad_tool",
        "selected_tools": ["notion_create_page"],
        "arguments": {},
    }
    decision = _parse_router_payload(payload, ["linear"])
    assert decision is None


def test_route_request_v2_llm_then_skill_for_notion_write():
    decision = route_request_v2("오늘 서울 날씨를 notion에 페이지로 생성해줘", ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert decision.selected_tools == ["notion_create_page"]


def test_route_request_v2_llm_then_skill_for_notion_write_with_labeled_title():
    decision = route_request_v2("notion 페이지 생성 제목: 구글로그인 구현방법 내용: 자세히 작성", ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert decision.arguments.get("notion_page_title") == "구글로그인 구현방법"


def test_route_request_v2_llm_then_skill_for_notion_write_with_prefix_object_title():
    decision = route_request_v2("오늘 서울 날씨를 notion에 페이지로 생성해줘", ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert decision.arguments.get("notion_page_title") == "오늘 서울 날씨"


def test_route_request_v2_skill_then_llm_for_linear_analysis():
    decision = route_request_v2("linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘", ["linear"])
    assert decision.mode == MODE_SKILL_THEN_LLM
    assert decision.arguments.get("linear_query") == "OPT-35"


def test_route_request_v2_skill_then_llm_for_linear_recent_list():
    decision = route_request_v2("linear 최근 이슈 10개 검색해줘", ["linear"])
    assert decision.mode == MODE_SKILL_THEN_LLM
    assert decision.skill_name == "linear.issue_search"
    assert decision.arguments.get("linear_first") == 10


def test_route_request_v2_skill_then_llm_for_notion_analysis():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 내용을 정리해줘', ["notion"])
    assert decision.mode == MODE_SKILL_THEN_LLM
    assert decision.selected_tools == ["notion_search"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


def test_route_request_v2_llm_then_skill_for_notion_update():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 업데이트해줘', ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.selected_tools == ["notion_search", "notion_append_block_children"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


def test_route_request_v2_llm_then_skill_for_notion_update_without_title():
    decision = route_request_v2("notion 페이지 업데이트", ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_update"


def test_route_request_v2_llm_then_skill_for_linear_update():
    decision = route_request_v2("linear의 OPT-35 이슈 업데이트해줘", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert "linear_update_issue" in decision.selected_tools
    assert "linear_search_issues" in decision.selected_tools
    assert decision.arguments.get("linear_issue_ref") == "OPT-35"


def test_route_request_v2_llm_then_skill_for_linear_description_append_intent():
    decision = route_request_v2("openweather API 사용방법을 정리해서 linear opt-46 설명에 추가하세요", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "linear.issue_update"
    assert decision.arguments.get("linear_issue_ref") == "opt-46"


def test_route_request_v2_llm_then_skill_for_linear_update_without_ref():
    decision = route_request_v2("linear 이슈 업데이트", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "linear.issue_update"


def test_route_request_v2_llm_then_skill_for_linear_delete():
    decision = route_request_v2("linear의 OPT-35 이슈 삭제해줘", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "linear.issue_delete"
    assert "linear_update_issue" in decision.selected_tools
    assert "linear_search_issues" in decision.selected_tools
    assert decision.arguments.get("linear_issue_ref") == "OPT-35"


def test_route_request_v2_llm_then_skill_for_linear_create():
    decision = route_request_v2('linear에서 팀: OPS, "로그인 실패 대응" 이슈 생성해줘', ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert "linear_create_issue" in decision.selected_tools
    assert "linear_list_teams" in decision.selected_tools
    assert decision.arguments.get("linear_team_ref") == "OPS"
    assert decision.arguments.get("linear_issue_title") == "로그인 실패 대응"


def test_route_request_v2_llm_then_skill_for_linear_create_with_labeled_title():
    decision = route_request_v2("linear 이슈 생성 팀: operate 제목: 비밀번호 찾기 오류", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "linear.issue_create"
    assert decision.arguments.get("linear_team_ref") == "operate"
    assert decision.arguments.get("linear_issue_title") == "비밀번호 찾기 오류"


def test_route_request_v2_llm_then_skill_for_linear_create_service_first_title():
    decision = route_request_v2("linear에서 비밀번호 찾기 오류 이슈 생성해줘", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "linear.issue_create"
    assert decision.arguments.get("linear_issue_title") == "비밀번호 찾기 오류"


def test_route_request_v2_linear_issue_to_notion_page_create():
    decision = route_request_v2("linear opt-47 이슈로 notion에 페이지 생성하세요", ["linear", "notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert decision.arguments.get("linear_issue_ref") == "opt-47"


def test_route_request_v2_llm_then_skill_for_notion_delete():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 삭제해줘', ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.selected_tools == ["notion_search", "notion_update_page"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


def test_route_request_v2_prefers_notion_create_over_analysis_keywords():
    decision = route_request_v2(
        'Notion에 새 페이지를 생성해줘. 제목은 "구글로그인 구현방법"이고, 내용은 구글 로그인 구현 방법을 자세히 작성해줘.',
        ["notion"],
    )
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.skill_name == "notion.page_create"
    assert "notion_create_page" in decision.selected_tools


def test_try_run_v2_orchestration_llm_only(monkeypatch):
    async def _fake_llm(*, prompt: str):
        assert "날씨" in prompt
        return "맑음", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="오늘 서울 날씨 알려줘",
            connected_services=["notion", "linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == MODE_LLM_ONLY
    assert "맑음" in result.execution.user_message


def test_try_run_v2_orchestration_uses_llm_router_when_enabled(monkeypatch):
    class _Settings:
        skill_router_v2_llm_enabled = True

    async def _fake_router(**kwargs):
        return (
            type(
                "_Decision",
                (),
                {
                    "mode": MODE_LLM_ONLY,
                    "reason": "from_llm_router",
                    "target_services": [],
                    "selected_tools": [],
                    "arguments": {},
                },
            )(),
            "openai",
            "gpt-4o-mini",
        )

    async def _fake_llm(*, prompt: str):
        return "LLM 결과", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2._request_router_decision_with_llm", _fake_router)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="오늘 서울 날씨 알려줘",
            connected_services=["notion", "linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert any(note == "router_source=llm" for note in result.plan.notes)


def test_try_run_v2_orchestration_rejects_invalid_intent_mode_skill_combo(monkeypatch):
    async def _fake_intent(**kwargs):
        return (
            IntentPayload(
                mode=MODE_LLM_THEN_SKILL,
                skill_name="linear.issue_search",
                arguments={},
                missing_fields=[],
                confidence=1.0,
                decision_reason="bad_combo",
            ),
            {"router_source": "test"},
        )

    monkeypatch.setattr("agent.orchestrator_v2.build_intent_json", _fake_intent)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 최근 이슈 검색",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "invalid_intent_mode_skill_combo"


def test_build_intent_json_snapshot_linear_recent_list():
    intent, meta = asyncio.run(
        build_intent_json(
            user_text="linear 최근 이슈 10개 검색해줘",
            connected_services=["linear"],
        )
    )

    assert intent.mode == MODE_SKILL_THEN_LLM
    assert intent.skill_name == "linear.issue_search"
    assert intent.arguments.get("linear_first") == 10
    assert intent.arguments.get("linear_query") == ""
    assert meta.get("router_source") in {"rule", "llm_fallback_rule"}


def test_execute_from_intent_blocks_llm_only_with_skill():
    decision = type(
        "_Decision",
        (),
        {
            "mode": MODE_LLM_ONLY,
            "skill_name": "linear.issue_search",
            "arguments": {},
        },
    )()
    plan = type("_Plan", (), {"notes": []})()

    try:
        asyncio.run(
            execute_from_intent(
                user_text="linear 최근 이슈 검색",
                user_id="user-1",
                decision=decision,  # type: ignore[arg-type]
                plan=plan,  # type: ignore[arg-type]
            )
        )
    except HTTPException as exc:
        assert str(exc.detail) == "invalid_intent_mode_skill_combo"
    else:
        raise AssertionError("expected HTTPException")


def test_execute_from_intent_blocks_llm_then_skill_with_read_skill():
    decision = type(
        "_Decision",
        (),
        {
            "mode": MODE_LLM_THEN_SKILL,
            "skill_name": "notion.page_search",
            "arguments": {},
        },
    )()
    plan = type("_Plan", (), {"notes": []})()

    try:
        asyncio.run(
            execute_from_intent(
                user_text="notion 최근 페이지 3개 검색",
                user_id="user-1",
                decision=decision,  # type: ignore[arg-type]
                plan=plan,  # type: ignore[arg-type]
            )
        )
    except HTTPException as exc:
        assert str(exc.detail) == "invalid_intent_mode_skill_combo"
    else:
        raise AssertionError("expected HTTPException")


def test_execute_from_intent_handles_llm_only(monkeypatch):
    async def _fake_llm(*, prompt: str):
        return "일반 답변", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    decision = type(
        "_Decision",
        (),
        {
            "mode": MODE_LLM_ONLY,
            "skill_name": None,
            "arguments": {},
        },
    )()

    plan = type(
        "_Plan",
        (),
        {
            "notes": [],
        },
    )()

    result = asyncio.run(
        execute_from_intent(
            user_text="한국의 수도는?",
            user_id="user-1",
            decision=decision,  # type: ignore[arg-type]
            plan=plan,  # type: ignore[arg-type]
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert "일반 답변" in result.execution.user_message


def test_execute_from_intent_handles_skill_then_llm_linear_recent_list(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_issues":
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "i1",
                                "identifier": "OPT-1",
                                "title": "첫 이슈",
                                "url": "https://linear.app/issue/OPT-1",
                            }
                        ]
                    }
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)

    decision = type(
        "_Decision",
        (),
        {
            "mode": MODE_SKILL_THEN_LLM,
            "skill_name": "linear.issue_search",
            "arguments": {"linear_query": "", "linear_first": 1},
            "selected_tools": ["linear_search_issues"],
            "target_services": ["linear"],
        },
    )()

    plan = type("_Plan", (), {"notes": []})()

    result = asyncio.run(
        execute_from_intent(
            user_text="linear 최근 이슈 1개 검색해줘",
            user_id="user-1",
            decision=decision,  # type: ignore[arg-type]
            plan=plan,  # type: ignore[arg-type]
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert "Linear 최근 이슈" in result.execution.user_message


def test_try_run_v2_orchestration_overrides_llm_mode_for_linear_recent_list(monkeypatch):
    class _Settings:
        skill_router_v2_llm_enabled = True

    async def _fake_router(**kwargs):
        # Deliberately wrong mode from LLM router.
        return (
            type(
                "_Decision",
                (),
                {
                    "mode": MODE_LLM_THEN_SKILL,
                    "reason": "llm_wrong_mode",
                    "skill_name": "linear.issue_search",
                    "target_services": ["linear"],
                    "selected_tools": ["linear_search_issues"],
                    "arguments": {"linear_query": "", "linear_first": 3},
                },
            )(),
            "openai",
            "gpt-4o-mini",
        )

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_issues":
            return {"data": {"issues": {"nodes": [{"id": "i1", "identifier": "OPT-1", "title": "첫 이슈"}]}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2._request_router_decision_with_llm", _fake_router)
    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 최근 이슈 3개 검색해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert "Linear 최근 이슈" in result.execution.user_message
    assert any(note.startswith("router_decision_override=") for note in result.plan.notes)


def test_try_run_v2_orchestration_forces_rule_when_llm_mode_skill_combo_invalid(monkeypatch):
    class _Settings:
        skill_router_v2_llm_enabled = True

    async def _fake_router(**kwargs):
        return (
            type(
                "_Decision",
                (),
                {
                    "mode": MODE_SKILL_THEN_LLM,
                    "reason": "bad_combo",
                    "skill_name": "linear.issue_create",
                    "target_services": ["linear"],
                    "selected_tools": ["linear_create_issue", "linear_list_teams"],
                    "arguments": {},
                },
            )(),
            "openai",
            "gpt-4o-mini",
        )

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_teams":
            return {"data": {"teams": {"nodes": [{"id": "t1", "key": "OPS", "name": "Operations"}]}}}
        if tool_name == "linear_create_issue":
            return {"data": {"issueCreate": {"issue": {"url": "https://linear.app/issue/OPS-1"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "이슈 본문", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2._request_router_decision_with_llm", _fake_router)
    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 이슈 생성",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") != "unsupported_service"
    assert result.plan is not None
    assert any(note == "router_decision_override=force_rule_unsupported_mode_skill_combo" for note in result.plan.notes)


def test_try_run_v2_orchestration_blocks_when_contracts_invalid(monkeypatch):
    monkeypatch.setattr("agent.orchestrator_v2.validate_all_contracts", lambda: (1, {"bad.json": ["x"]}))

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="오늘 서울 날씨 알려줘",
            connected_services=["notion", "linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "skill_contracts_invalid"
    assert any(note == "router_source=contracts_invalid" for note in result.plan.notes)


def test_try_run_v2_orchestration_skill_then_llm(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        assert tool_name == "linear_search_issues"
        assert payload.get("query") == "OPT-35"
        return {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-id-1",
                            "identifier": "OPT-35",
                            "title": "로그인 오류",
                            "description": "로그인 시 500 에러가 발생합니다.",
                        }
                    ]
                }
            }
        }

    async def _fake_llm(*, prompt: str):
        assert "OPT-35" in prompt
        assert "로그인 시 500" in prompt
        return "해결 방법: 1) 에러 로그 확인 2) 재현 경로 점검", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == MODE_SKILL_THEN_LLM
    assert "해결 방법" in result.execution.user_message


def test_try_run_v2_orchestration_skill_then_llm_linear_recent_list(monkeypatch):
    calls = {"list": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_list_issues":
            calls["list"] += 1
            assert payload.get("first") == 10
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "i1",
                                "identifier": "OPT-1",
                                "title": "첫 이슈",
                                "description": "desc1",
                                "url": "https://linear.app/issue/OPT-1",
                            },
                            {
                                "id": "i2",
                                "identifier": "OPT-2",
                                "title": "둘째 이슈",
                                "description": "desc2",
                                "url": "https://linear.app/issue/OPT-2",
                            },
                        ]
                    }
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not be called for recent issue list intent")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 최근 이슈 10개 검색해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["list"] == 1
    assert "Linear 최근 이슈" in result.execution.user_message
    assert "[OPT-1]" in result.execution.user_message
    assert "https://linear.app/issue/OPT-1" in result.execution.user_message


def test_try_run_v2_orchestration_skill_then_llm_linear_recent_list_handles_non_numeric_first(monkeypatch):
    class _Settings:
        skill_router_v2_llm_enabled = True

    async def _fake_router(**kwargs):
        return (
            type(
                "_Decision",
                (),
                {
                    "mode": MODE_SKILL_THEN_LLM,
                    "reason": "linear_recent",
                    "skill_name": "linear.issue_search",
                    "target_services": ["linear"],
                    "selected_tools": ["linear_search_issues"],
                    "arguments": {"linear_query": "", "linear_first": "10개"},
                },
            )(),
            "openai",
            "gpt-4o-mini",
        )

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_issues":
            assert payload.get("first") == 10
            return {"data": {"issues": {"nodes": [{"id": "i1", "identifier": "OPT-1", "title": "첫 이슈"}]}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2._request_router_decision_with_llm", _fake_router)
    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 최근 이슈 10개 검색해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert "Linear 최근 이슈" in result.execution.user_message


def test_try_run_v2_orchestration_skill_then_llm_notion_recent_pages_list(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "notion_search":
            assert payload.get("page_size") == 3
            return {
                "data": {
                    "results": [
                        {
                            "id": "p1",
                            "url": "https://notion.so/p1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "회고"}]}},
                        },
                        {
                            "id": "p2",
                            "url": "https://notion.so/p2",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "회의록"}]}},
                        },
                    ]
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="notion 최근 페이지 3개 검색해줘",
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert "Notion 최근 페이지" in result.execution.user_message
    assert "https://notion.so/p1" in result.execution.user_message


def test_try_run_v2_orchestration_skill_then_llm_linear_returns_needs_input_when_not_found(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            return {"data": {"issues": {"nodes": []}}}
        if tool_name == "linear_list_issues":
            return {"data": {"issues": {"nodes": []}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not be called when linear issue search is empty")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "not_found"


def test_try_run_v2_orchestration_skill_then_llm_linear_falls_back_to_list_issues(monkeypatch):
    calls = {"search": 0, "list": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            if payload.get("query") == "OPT-43":
                return {"data": {"issues": {"nodes": []}}}
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-43",
                                "identifier": "OPT-43",
                                "title": "로그인 버튼 클릭 오류",
                                "description": "구글 로그인 클릭 시 404 오류",
                            }
                        ]
                    }
                }
            }
        if tool_name == "linear_list_issues":
            calls["list"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-43",
                                "identifier": "OPT-43",
                                "title": "로그인 버튼 클릭 오류",
                            }
                        ]
                    }
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        assert "OPT-43" in prompt
        return "해결 가이드", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-43 이슈 설명을 해결하는 방법을 정리해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] >= 1
    assert calls["list"] == 1
    assert "해결 가이드" in result.execution.user_message


def test_try_run_v2_orchestration_llm_then_notion_update(monkeypatch):
    calls = {"search": 0, "append": 0}
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            assert payload.get("query") == "스프린트 회고"
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "스프린트 회고"}],
                                }
                            },
                        }
                    ]
                }
            }
        if tool_name == "notion_append_block_children":
            calls["append"] += 1
            assert payload.get("block_id") == "page-1"
            assert payload.get("children")
            children = payload.get("children") or []
            captured["content"] = (
                ((((children[0] or {}).get("paragraph") or {}).get("rich_text") or [{}])[0]
                .get("text", {})
                .get("content", ""))
            )
            return {"data": {"ok": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit body update text")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 본문 업데이트: 배포 회고 요약 추가',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["append"] == 1
    assert captured.get("content") == "배포 회고 요약 추가"
    assert result.execution.artifacts.get("router_mode") == MODE_LLM_THEN_SKILL
    assert result.execution.artifacts.get("updated_page_id") == "page-1"


def test_try_run_v2_orchestration_llm_then_notion_update_requires_patch_detail(monkeypatch):
    calls = {"search": 0, "append": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "스프린트 회고"}]}},
                        }
                    ]
                }
            }
        if tool_name == "notion_append_block_children":
            calls["append"] += 1
            assert payload.get("block_id") == "page-1"
            return {"data": {"results": []}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "업데이트 안내", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 업데이트해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["append"] == 1


def test_try_run_v2_orchestration_llm_then_notion_update_title_change(monkeypatch):
    calls = {"search": 0, "update": 0, "append": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {
                                "제목": {
                                    "type": "title",
                                    "title": [{"plain_text": "스프린트 회고"}],
                                }
                            },
                        }
                    ]
                }
            }
        if tool_name == "notion_update_page":
            calls["update"] += 1
            assert payload.get("page_id") == "page-1"
            props = payload.get("properties") or {}
            assert "제목" in props
            title_nodes = ((props.get("제목") or {}).get("title") or [])
            assert (((title_nodes[0] or {}).get("text") or {}).get("content") or "") == "스프린트 보고서"
            return {"data": {"id": "page-1", "url": "https://notion.so/page-1"}}
        if tool_name == "notion_append_block_children":
            calls["append"] += 1
            return {"data": {"ok": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for pure title update")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 제목을 "스프린트 보고서"로 업데이트해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1
    assert calls["append"] == 0
    assert "스프린트 보고서" in result.execution.user_message


def test_try_run_v2_orchestration_llm_then_notion_update_body_does_not_append_confirmation(monkeypatch):
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {
                                "제목": {
                                    "type": "title",
                                    "title": [{"plain_text": "스프린트 보고서"}],
                                }
                            },
                        }
                    ]
                }
            }
        if tool_name == "notion_append_block_children":
            children = payload.get("children") or []
            captured["content"] = (
                ((((children[0] or {}).get("paragraph") or {}).get("rich_text") or [{}])[0]
                .get("text", {})
                .get("content", ""))
            )
            return {"data": {"ok": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit body update text")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 보고서" 페이지 본문 업데이트: 내가 돌아왔다',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert captured.get("content") == "내가 돌아왔다"
    assert "본문이" not in captured.get("content", "")


def test_try_run_v2_orchestration_llm_then_notion_create_skips_on_realtime_unavailable(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        raise AssertionError("skill should not run when realtime data is unavailable")

    async def _fake_llm(*, prompt: str):
        return "실시간 조회 불가.", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="오늘 서울 날씨를 notion에 페이지로 생성해줘",
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "realtime_data_unavailable"


def test_try_run_v2_orchestration_llm_then_notion_create_translates_url_then_creates_page(monkeypatch):
    calls = {"fetch": 0, "create": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "http_fetch_url_text":
            calls["fetch"] += 1
            assert payload.get("url") == "https://example.com/article"
            return {
                "data": {
                    "url": "https://example.com/article",
                    "final_url": "https://example.com/article",
                    "title": "Example Article",
                    "text": "Hello world. This is an English article.",
                }
            }
        if tool_name == "notion_create_page":
            calls["create"] += 1
            children = payload.get("children") or []
            text = (
                (((children[0] or {}).get("paragraph") or {}).get("rich_text") or [{}])[0]
                .get("text", {})
                .get("content", "")
            )
            assert "안녕하세요" in text
            return {"data": {"url": "https://notion.so/new-page"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        assert "원문 URL" in prompt
        assert "번역문만 출력" in prompt
        return "안녕하세요. 이것은 번역된 기사입니다.", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="기사(https://example.com/article)를 한국어로 번역해서 notion에 페이지로 생성해줘",
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["fetch"] == 1
    assert calls["create"] == 1
    assert result.execution.artifacts.get("source_url") == "https://example.com/article"


def test_try_run_v2_orchestration_llm_then_linear_update_requires_patch_detail(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-35", "identifier": "OPT-35", "description": "기존 설명"}]}}}
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-35"
            assert payload.get("description")
            return {"data": {"issueUpdate": {"success": True, "issue": {"url": "https://linear.app/issue/OPT-35"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "수정 설명 요약", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 업데이트해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1


def test_try_run_v2_orchestration_linear_description_update_without_content_requires_patch(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-46", "identifier": "OPT-46", "description": "기존 설명"}]}}}
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-46"
            assert payload.get("description")
            return {"data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "설명 보강안", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear opt-46 이슈 설명 업데이트",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1


def test_try_run_v2_orchestration_llm_then_linear_update_returns_needs_input_when_issue_ref_missing(monkeypatch):
    calls = {"list": 0, "search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_issues":
            calls["list"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-1", "identifier": "OPT-1", "description": "기존 설명"}]}}}
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-1", "identifier": "OPT-1", "description": "기존 설명"}]}}}
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-1"
            return {"data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "수정 설명 요약", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 이슈 업데이트해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["list"] == 1
    assert calls["search"] >= 1
    assert calls["update"] == 1


def test_try_run_v2_orchestration_llm_then_linear_update_title_change_without_llm(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-internal-35",
                                "identifier": "OPT-35",
                                "title": "이전 제목",
                                "url": "https://linear.app/pouder/issue/OPT-35",
                            }
                        ]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-35"
            assert payload.get("title") == "새로운 제목"
            assert "description" not in payload
            return {"data": {"issueUpdate": {"success": True, "issue": {}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit linear title update")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='linear의 OPT-35 이슈 제목을 "새로운 제목"으로 업데이트해줘',
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1
    assert "새로운 제목" in result.execution.user_message
    assert "https://linear.app/pouder/issue/OPT-35" in result.execution.user_message


def test_try_run_v2_orchestration_llm_then_linear_update_description_without_llm(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [{"id": "issue-internal-35", "identifier": "OPT-35", "title": "로그인 오류"}]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-35"
            assert payload.get("description") == "재현 경로와 콘솔 로그를 추가해줘"
            assert "title" not in payload
            return {"data": {"issueUpdate": {"success": True, "issue": {"url": "https://linear.app/pouder/issue/OPT-35"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit linear description update")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 설명 업데이트: 재현 경로와 콘솔 로그를 추가해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1
    assert "https://linear.app/pouder/issue/OPT-35" in result.execution.user_message
    assert result.execution.artifacts.get("updated_issue_url") == "https://linear.app/pouder/issue/OPT-35"


def test_extract_linear_update_description_text_from_object_to_modify_phrase():
    text = "linear opt-46 이슈의 본문을 패시브 서비스 추가, https://openweathermap.org/api#one_call_3 문서 참조 로 수정하세요"
    extracted = _extract_linear_update_description_text(text)
    assert extracted is not None
    assert "패시브 서비스 추가" in extracted
    assert "https://openweathermap.org/api#one_call_3" in extracted


def test_try_run_v2_orchestration_llm_then_linear_update_description_modify_phrase_without_llm(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-internal-46",
                                "identifier": "OPT-46",
                                "title": "기존 설명",
                                "url": "https://linear.app/pouder/issue/OPT-46",
                            }
                        ]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-46"
            assert payload.get("description") == "패시브 서비스 추가, https://openweathermap.org/api#one_call_3 문서 참조"
            return {"data": {"issueUpdate": {"success": True, "issue": {"url": "https://linear.app/pouder/issue/OPT-46"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit linear description modify phrase")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear opt-46 이슈의 본문을 패시브 서비스 추가, https://openweathermap.org/api#one_call_3 문서 참조 로 수정하세요",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1
    assert "https://linear.app/pouder/issue/OPT-46" in result.execution.user_message


def test_try_run_v2_orchestration_llm_then_linear_update_description_append_with_generated_content(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-internal-46",
                                "identifier": "OPT-46",
                                "title": "add openweather",
                                "url": "https://linear.app/pouder/issue/OPT-46/add-openweather",
                                "description": "기존 설명",
                            }
                        ]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-46"
            description = str(payload.get("description") or "")
            assert "기존 설명" in description
            assert "OpenWeather API 사용 방법 요약" in description
            return {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {"url": "https://linear.app/pouder/issue/OPT-46/add-openweather"},
                    }
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        assert "openweather" in prompt.lower()
        return "OpenWeather API 사용 방법 요약", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="openweather API 사용방법을 정리해서 linear opt-46 설명에 추가하세요",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1
    assert "Linear 이슈 설명이 업데이트" in result.execution.user_message
    assert "https://linear.app/pouder/issue/OPT-46/add-openweather" in result.execution.user_message


def test_try_run_v2_orchestration_llm_then_linear_update_state_priority_without_llm(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {
                "data": {
                    "issues": {
                        "nodes": [{"id": "issue-internal-35", "identifier": "OPT-35", "title": "로그인 오류"}]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-35"
            assert payload.get("state_id") == "state-123"
            assert payload.get("priority") == 2
            return {"data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not run for explicit linear state/priority update")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 업데이트 state_id: state-123 priority: 2",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["update"] == 1


def test_try_run_v2_orchestration_llm_then_linear_update_falls_back_to_list_issues(monkeypatch):
    calls = {"search": 0, "list": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            if payload.get("query") == "OPT-35":
                return {"data": {"issues": {"nodes": []}}}
            return {"data": {"issues": {"nodes": [{"id": "issue-internal-35", "identifier": "OPT-35", "title": "로그인 오류"}]}}}
        if tool_name == "linear_list_issues":
            calls["list"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-internal-35", "identifier": "OPT-35", "title": "로그인 오류"}]}}}
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-35"
            return {"data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "수정 설명 요약", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 설명 업데이트: 수정 설명 요약",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] >= 1
    assert calls["list"] == 1
    assert calls["update"] == 1


def test_try_run_v2_orchestration_llm_then_linear_create(monkeypatch):
    calls = {"teams": 0, "create": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_list_teams":
            calls["teams"] += 1
            return {"data": {"teams": {"nodes": [{"id": "team-ops-id", "key": "OPS", "name": "Operations"}]}}}
        if tool_name == "linear_create_issue":
            calls["create"] += 1
            assert payload.get("team_id") == "team-ops-id"
            assert payload.get("title") == "로그인 실패 대응"
            assert payload.get("description") == "이슈 본문"
            return {"data": {"issueCreate": {"issue": {"url": "https://linear.app/issue/OPS-123"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "이슈 본문", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='linear에서 팀: OPS, "로그인 실패 대응" 이슈 생성해줘',
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["teams"] == 1
    assert calls["create"] == 1
    assert result.execution.artifacts.get("created_issue_url") == "https://linear.app/issue/OPS-123"


def test_try_run_v2_orchestration_llm_then_linear_delete(monkeypatch):
    calls = {"search": 0, "delete": 0}

    class _Settings:
        delete_operations_enabled = False

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            assert payload.get("query") == "OPT-35"
            return {"data": {"issues": {"nodes": [{"id": "issue-delete-35", "identifier": "OPT-35"}]}}}
        if tool_name == "linear_update_issue":
            calls["delete"] += 1
            assert payload.get("issue_id") == "issue-delete-35"
            assert payload.get("archived") is True
            return {"data": {"issueArchive": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "삭제 처리", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)
    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 삭제해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "delete_disabled"
    assert calls["search"] == 0
    assert calls["delete"] == 0


def test_try_run_v2_orchestration_llm_then_linear_delete_fails_when_archive_unsuccessful(monkeypatch):
    calls = {"search": 0, "delete": 0}

    class _Settings:
        delete_operations_enabled = False

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {"data": {"issues": {"nodes": [{"id": "issue-delete-45", "identifier": "OPT-45"}]}}}
        if tool_name == "linear_update_issue":
            calls["delete"] += 1
            return {"data": {"issueArchive": {"success": False}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "삭제 처리", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)
    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-45 이슈 삭제해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "delete_disabled"
    assert calls["search"] == 0
    assert calls["delete"] == 0


def test_try_run_v2_orchestration_llm_then_notion_delete(monkeypatch):
    calls = {"search": 0, "delete": 0}

    class _Settings:
        delete_operations_enabled = False

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-del-1",
                            "url": "https://notion.so/page-del-1",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "스프린트 회고"}],
                                }
                            },
                        }
                    ]
                }
            }
        if tool_name == "notion_update_page":
            calls["delete"] += 1
            assert payload.get("page_id") == "page-del-1"
            assert payload.get("in_trash") is True
            return {"data": {"id": "page-del-1"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "삭제 요청 처리", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)
    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 삭제해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "delete_disabled"
    assert calls["search"] == 0
    assert calls["delete"] == 0


def test_try_run_v2_orchestration_skill_then_llm_for_notion(monkeypatch):
    calls = {"search": 0, "blocks": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-101",
                            "url": "https://notion.so/page-101",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "스프린트 회고"}],
                                }
                            },
                        }
                    ]
                }
            }
        if tool_name == "notion_retrieve_block_children":
            calls["blocks"] += 1
            assert payload.get("block_id") == "page-101"
            return {
                "data": {
                    "results": [
                        {
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {"plain_text": "이번 스프린트에서 배포 지연이 있었습니다."},
                                    {"plain_text": "원인은 CI 대기열 병목이었습니다."},
                                ]
                            },
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        assert "배포 지연" in prompt
        return "회고 정리: CI 병목 개선이 핵심입니다.", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 내용을 정리해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["blocks"] == 1
    assert result.execution.artifacts.get("router_mode") == MODE_SKILL_THEN_LLM
    assert result.execution.artifacts.get("source_page_id") == "page-101"
    assert "회고 정리" in result.execution.user_message


def test_try_run_v2_orchestration_returns_needs_input_for_ambiguous_notion_update(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "로그인 버그"}],
                                }
                            },
                        },
                        {
                            "id": "page-2",
                            "url": "https://notion.so/page-2",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "로그인 버그"}],
                                }
                            },
                        },
                    ]
                }
            }
        if tool_name == "notion_append_block_children":
            assert payload.get("block_id") == "page-1"
            return {"data": {"results": []}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "업데이트 본문", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "로그인 버그" 페이지 본문 업데이트: 재현 경로를 추가해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.artifacts.get("updated_page_id") == "page-1"


def test_try_run_v2_orchestration_linear_create_uses_default_title_when_missing(monkeypatch):
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "linear_list_teams":
            return {"data": {"teams": {"nodes": [{"id": "team-1", "key": "operate", "name": "Operate"}]}}}
        if tool_name == "linear_create_issue":
            captured["title"] = payload.get("title")
            return {"data": {"issueCreate": {"issue": {"url": "https://linear.app/issue/OPS-1"}}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "이슈 설명", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear 이슈 생성 팀: operate",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert captured.get("title") == "new issue"


def test_try_run_v2_orchestration_notion_create_uses_default_title_when_missing(monkeypatch):
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        if tool_name == "notion_create_page":
            title_nodes = (((payload.get("properties") or {}).get("title") or {}).get("title") or [])
            captured["title"] = (((title_nodes[0] or {}).get("text") or {}).get("content") if title_nodes else "")
            return {"data": {"url": "https://notion.so/new-page"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "생성 본문", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="notion에 페이지 생성해줘",
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert captured.get("title") == "new page"


def test_try_run_v2_orchestration_notion_create_from_linear_issue(monkeypatch):
    calls = {"search": 0, "create": 0}
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            assert payload.get("query") == "opt-47"
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-47",
                                "identifier": "OPT-47",
                                "title": "로그인 오류",
                                "description": "재현 경로: 앱 실행 후 로그인 버튼 클릭 시 500",
                                "url": "https://linear.app/issue/OPT-47",
                            }
                        ]
                    }
                }
            }
        if tool_name == "notion_create_page":
            calls["create"] += 1
            title_nodes = (((payload.get("properties") or {}).get("title") or {}).get("title") or [])
            captured["title"] = (((title_nodes[0] or {}).get("text") or {}).get("content") if title_nodes else "")
            children = payload.get("children") or []
            captured["content"] = (
                (((children[0] or {}).get("paragraph") or {}).get("rich_text") or [{}])[0]
                .get("text", {})
                .get("content", "")
            )
            return {"data": {"url": "https://notion.so/new-page"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not be called for linear->notion copy create intent")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear opt-47 이슈로 notion에 페이지 생성하세요",
            connected_services=["linear", "notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["create"] == 1
    assert captured.get("title") == "로그인 오류"
    assert "Linear 이슈: OPT-47" in captured.get("content", "")
    assert "재현 경로" in captured.get("content", "")


def test_try_run_v2_orchestration_notion_create_from_linear_issue_falls_back_when_not_found(monkeypatch):
    calls = {"search": 0, "create": 0}
    captured: dict = {}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            return {"data": {"issues": {"nodes": []}}}
        if tool_name == "linear_list_issues":
            return {"data": {"issues": {"nodes": []}}}
        if tool_name == "notion_create_page":
            calls["create"] += 1
            title_nodes = (((payload.get("properties") or {}).get("title") or {}).get("title") or [])
            captured["title"] = (((title_nodes[0] or {}).get("text") or {}).get("content") if title_nodes else "")
            children = payload.get("children") or []
            captured["content"] = (
                (((children[0] or {}).get("paragraph") or {}).get("rich_text") or [{}])[0]
                .get("text", {})
                .get("content", "")
            )
            return {"data": {"url": "https://notion.so/new-page"}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        raise AssertionError("llm should not be called for linear->notion copy create intent")

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear OPT-47 이슈로 notion에 페이지 생성하세요",
            connected_services=["linear", "notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] >= 1
    assert calls["create"] == 1
    assert captured.get("title") == "Linear OPT-47"
    assert "Linear 이슈 참조: OPT-47" in captured.get("content", "")


def test_try_run_v2_orchestration_forces_rule_on_explicit_notion_mutation_intent(monkeypatch):
    class _Settings:
        skill_router_v2_llm_enabled = True

    calls = {"search": 0, "append": 0}

    async def _fake_router(**kwargs):
        # Deliberately wrong: read flow for explicit update intent.
        return (
            type(
                "_Decision",
                (),
                {
                    "mode": MODE_SKILL_THEN_LLM,
                    "reason": "bad_router_pick",
                    "skill_name": "notion.page_search",
                    "target_services": ["notion"],
                    "selected_tools": ["notion_search"],
                    "arguments": {},
                },
            )(),
            "openai",
            "gpt-4o-mini",
        )

    async def _fake_llm(*, prompt: str):
        return "업데이트 본문", "openai", "gpt-4o-mini"

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "notion_search":
            calls["search"] += 1
            return {
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "자동 선택 페이지"}]}},
                        }
                    ]
                }
            }
        if tool_name == "notion_append_block_children":
            calls["append"] += 1
            assert payload.get("block_id") == "page-1"
            return {"data": {"results": []}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    monkeypatch.setattr("agent.orchestrator_v2.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.orchestrator_v2._request_router_decision_with_llm", _fake_router)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)
    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="notion 페이지 업데이트",
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["append"] == 1
    assert any(note == "router_decision_override=force_rule_explicit_mutation_intent" for note in result.plan.notes)


def test_try_run_v2_orchestration_maps_auth_required_error(monkeypatch):
    async def _fake_execute_from_intent(*, user_text: str, user_id: str, decision, plan):
        raise HTTPException(
            status_code=400,
            detail=(
                "linear_search_issues:AUTH_REQUIRED|status=401|"
                "message={\"errors\":[{\"message\":\"Authentication required, not authenticated\"}]}"
            ),
        )

    monkeypatch.setattr("agent.orchestrator_v2.execute_from_intent", _fake_execute_from_intent)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear opt-46 업데이트",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "auth_error"
    assert "권한이 부족하거나 만료되었습니다" in result.execution.user_message
