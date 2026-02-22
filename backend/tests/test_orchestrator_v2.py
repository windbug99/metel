import asyncio

from agent.orchestrator_v2 import (
    MODE_LLM_ONLY,
    MODE_LLM_THEN_SKILL,
    MODE_SKILL_THEN_LLM,
    _parse_router_payload,
    route_request_v2,
    try_run_v2_orchestration,
)


def test_route_request_v2_defaults_to_llm_only():
    decision = route_request_v2("오늘 서울 날씨 알려줘", ["notion", "linear"])
    assert decision.mode == MODE_LLM_ONLY


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


def test_route_request_v2_skill_then_llm_for_linear_analysis():
    decision = route_request_v2("linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘", ["linear"])
    assert decision.mode == MODE_SKILL_THEN_LLM
    assert decision.arguments.get("linear_query") == "OPT-35"


def test_route_request_v2_skill_then_llm_for_notion_analysis():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 내용을 정리해줘', ["notion"])
    assert decision.mode == MODE_SKILL_THEN_LLM
    assert decision.selected_tools == ["notion_search"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


def test_route_request_v2_llm_then_skill_for_notion_update():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 업데이트해줘', ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.selected_tools == ["notion_append_block_children"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


def test_route_request_v2_llm_then_skill_for_linear_update():
    decision = route_request_v2("linear의 OPT-35 이슈 업데이트해줘", ["linear"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert "linear_update_issue" in decision.selected_tools
    assert "linear_search_issues" in decision.selected_tools
    assert decision.arguments.get("linear_issue_ref") == "OPT-35"


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


def test_route_request_v2_llm_then_skill_for_notion_delete():
    decision = route_request_v2('노션에서 "스프린트 회고" 페이지 삭제해줘', ["notion"])
    assert decision.mode == MODE_LLM_THEN_SKILL
    assert decision.selected_tools == ["notion_update_page"]
    assert decision.arguments.get("notion_page_title") == "스프린트 회고"


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


def test_try_run_v2_orchestration_skill_then_llm_linear_returns_needs_input_when_not_found(monkeypatch):
    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert tool_name == "linear_search_issues"
        return {"data": {"issues": {"nodes": []}}}

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
    assert result.execution.artifacts.get("needs_input") == "true"
    assert result.execution.artifacts.get("error_code") == "validation_error"


def test_try_run_v2_orchestration_llm_then_notion_update(monkeypatch):
    calls = {"search": 0, "append": 0}

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
            return {"data": {"ok": True}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "업데이트할 요약 내용", "openai", "gpt-4o-mini"

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
    assert result.execution.artifacts.get("router_mode") == MODE_LLM_THEN_SKILL
    assert result.execution.artifacts.get("updated_page_id") == "page-1"


def test_try_run_v2_orchestration_llm_then_linear_update(monkeypatch):
    calls = {"search": 0, "update": 0}

    async def _fake_tool(*, user_id: str, tool_name: str, payload: dict):
        assert user_id == "user-1"
        if tool_name == "linear_search_issues":
            calls["search"] += 1
            assert payload.get("query") == "OPT-35"
            return {
                "data": {
                    "issues": {
                        "nodes": [
                            {"id": "issue-internal-35", "identifier": "OPT-35", "title": "로그인 오류"}
                        ]
                    }
                }
            }
        if tool_name == "linear_update_issue":
            calls["update"] += 1
            assert payload.get("issue_id") == "issue-internal-35"
            assert payload.get("description") == "수정 설명 요약"
            return {"data": {"issueUpdate": {"success": True}}}
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
    assert result.execution.artifacts.get("router_mode") == MODE_LLM_THEN_SKILL
    assert result.execution.artifacts.get("updated_issue_id") == "issue-internal-35"


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
            return {"data": {"issueUpdate": {"success": True}}}
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "삭제 처리", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text="linear의 OPT-35 이슈 삭제해줘",
            connected_services=["linear"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["delete"] == 1
    assert result.execution.artifacts.get("deleted_issue_id") == "issue-delete-35"


def test_try_run_v2_orchestration_llm_then_notion_delete(monkeypatch):
    calls = {"search": 0, "delete": 0}

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

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "스프린트 회고" 페이지 삭제해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is True
    assert result.execution is not None
    assert calls["search"] == 1
    assert calls["delete"] == 1
    assert result.execution.artifacts.get("deleted_page_id") == "page-del-1"


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
        raise AssertionError(f"unexpected tool call: {tool_name}")

    async def _fake_llm(*, prompt: str):
        return "업데이트 본문", "openai", "gpt-4o-mini"

    monkeypatch.setattr("agent.orchestrator_v2.execute_tool", _fake_tool)
    monkeypatch.setattr("agent.orchestrator_v2._request_llm_text", _fake_llm)

    result = asyncio.run(
        try_run_v2_orchestration(
            user_text='노션에서 "로그인 버그" 페이지 업데이트해줘',
            connected_services=["notion"],
            user_id="user-1",
        )
    )

    assert result is not None
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("needs_input") == "true"
    assert result.execution.artifacts.get("error_code") == "validation_error"
    assert "선택 가능한 항목" in result.execution.user_message
