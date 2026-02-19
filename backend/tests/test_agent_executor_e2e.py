import asyncio

from fastapi import HTTPException

from agent.executor import execute_agent_plan
from agent.types import AgentPlan, AgentRequirement


def _plan(user_text: str, selected_tools: list[str]) -> AgentPlan:
    return AgentPlan(
        user_text=user_text,
        requirements=[AgentRequirement(summary="대상 데이터 조회")],
        target_services=["notion"],
        selected_tools=selected_tools,
        workflow_steps=[],
        notes=[],
    )


def test_execute_notion_rename_flow(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "Metel test page"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            return {"ok": True, "data": {"id": "page-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션에서 Metel test page 페이지 제목을 주간 회의록으로 변경",
        ["notion_search", "notion_update_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "제목 변경" in result.summary
    assert len(calls) == 2
    assert calls[0][0] == "notion_search"
    assert calls[1][0] == "notion_update_page"


def test_execute_notion_data_source_query_flow(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_query_data_source":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "page-a",
                            "url": "https://notion.so/page-a",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "A"}]}},
                        },
                        {
                            "id": "page-b",
                            "url": "https://notion.so/page-b",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "B"}]}},
                        },
                    ]
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 2개 조회",
        ["notion_query_data_source"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "데이터소스 조회" in result.summary
    assert "1. A" in result.user_message
    assert len(calls) == 1


def test_execute_notion_archive_flow(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30c50e84a3bf8109b781ed4e0e0dacb3",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "Metel test page"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            assert payload["archived"] is True
            return {"ok": True, "data": {"id": "30c50e84a3bf8109b781ed4e0e0dacb3"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션에서 Metel test page 페이지 삭제해줘",
        ["notion_search", "notion_update_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "아카이브" in result.summary
    assert len(calls) == 2


def test_execute_notion_archive_flow_retries_with_in_trash_on_bad_request(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30c50e84a3bf8109b781ed4e0e0dacb3",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "일일 회의록 테스트"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            if payload.get("archived") is True:
                raise HTTPException(status_code=400, detail="notion_update_page:BAD_REQUEST")
            assert payload.get("in_trash") is True
            return {"ok": True, "data": {"id": "30c50e84a3bf8109b781ed4e0e0dacb3"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "일일 회의록 테스트 페이지 삭제해줘",
        ["notion_search", "notion_update_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "아카이브" in result.summary
    assert [item[0] for item in calls] == ["notion_search", "notion_update_page", "notion_update_page"]
    assert calls[1][1]["archived"] is True
    assert calls[2][1]["in_trash"] is True


def test_execute_notion_rename_then_top_lines_flow(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "더 코어"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "notion_retrieve_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "notion_retrieve_block_children":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "line 1"}]},
                        },
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "line 2"}]},
                        },
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "line 3"}]},
                        },
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "line 4"}]},
                        },
                    ]
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    plan = _plan(
        '더 코어 페이지 제목을 "더 코어 2"로 바꾸고, 바꾼 페이지 본문 상위 4줄을 출력해줘',
        ["notion_search", "notion_update_page", "notion_retrieve_page", "notion_retrieve_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert "제목 변경" in result.summary
    assert "상위 4줄" in result.user_message
    assert [item[0] for item in calls] == [
        "notion_search",
        "notion_update_page",
        "notion_retrieve_page",
        "notion_retrieve_block_children",
    ]


def test_execute_plan_error_message_standardized(monkeypatch):
    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise HTTPException(status_code=400, detail="notion_search:AUTH_REQUIRED")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션에서 Metel test page의 내용 중 상위 10줄 출력",
        ["notion_search", "notion_retrieve_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is False
    assert result.artifacts.get("error_code") == "auth_error"
    assert "권한" in result.user_message


def test_execute_notion_data_source_query_invalid_id(monkeypatch):
    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        raise AssertionError("invalid id path should not call external tool")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션 데이터소스 invalid-id 조회해줘",
        ["notion_query_data_source"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is False
    assert result.artifacts.get("error_code") == "validation_error"
    assert "형식이 올바르지" in result.user_message


def test_execute_notion_summary_one_line(monkeypatch):
    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "page-1",
                            "url": "https://notion.so/page-1",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "더 코어 2"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_retrieve_page":
            return {"ok": True, "data": {"id": "page-1"}}
        if tool_name == "notion_retrieve_block_children":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "line 1"}]}},
                        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "line 2"}]}},
                    ]
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_request_summary_with_provider(
        *,
        provider: str,
        model: str,
        text: str,
        line_count: int | None,
        openai_api_key: str | None,
        google_api_key: str | None,
    ):
        return "첫 줄 요약\n둘째 줄 요약"

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._request_summary_with_provider", _fake_request_summary_with_provider)

    plan = _plan(
        "노션에서 더 코어 2 페이지의 내용을 1줄요약해주세요",
        ["notion_search", "notion_retrieve_page", "notion_retrieve_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "페이지 요약" in result.summary
    summary_text = result.user_message.split("\n\n", 1)[1]
    assert "\n" not in summary_text


def test_execute_notion_summary_create_uses_requested_titles(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            query = payload.get("query")
            if query == "더 코어 3":
                return {
                    "ok": True,
                    "data": {
                        "results": [
                            {
                                "id": "30c50e84a3bf81c19f4ae0816b901fd4",
                                "url": "https://notion.so/core-3",
                                "properties": {"title": {"type": "title", "title": [{"plain_text": "더 코어 3"}]}},
                            }
                        ]
                    },
                }
            if query == "사이먼 블로그":
                return {
                    "ok": True,
                    "data": {
                        "results": [
                            {
                                "id": "30b50e84a3bf814889b5d55fe4667af2",
                                "url": "https://notion.so/simon",
                                "properties": {"title": {"type": "title", "title": [{"plain_text": "사이먼 블로그"}]}},
                            }
                        ]
                    },
                }
            raise AssertionError(f"unexpected query: {query}")
        if tool_name == "notion_retrieve_block_children":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "본문 1"}]}},
                        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "본문 2"}]}},
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "30c50e84a3bf814e99b7f697ce63254d", "url": "https://notion.so/new"}}
        if tool_name == "notion_append_block_children":
            return {"ok": True, "data": {"results": []}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_request_summary_with_provider(
        *,
        provider: str,
        model: str,
        text: str,
        line_count: int | None,
        openai_api_key: str | None,
        google_api_key: str | None,
    ):
        return "요약 결과"

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._request_summary_with_provider", _fake_request_summary_with_provider)

    plan = _plan(
        '노션에서 "더 코어 3", "사이먼 블로그" 페이지를 요약해서 "일일 회의록 테스트 2" 페이지로 만들어줘',
        ["notion_search", "notion_retrieve_block_children", "notion_create_page", "notion_append_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "요약/생성" in result.summary
    assert "- 기준 페이지 수: 2" in result.user_message
    assert "- 생성 페이지 제목: 일일 회의록 테스트 2" in result.user_message


def test_extract_output_title_strips_trailing_page_token():
    from agent.executor import _extract_output_title

    title = _extract_output_title('노션에서 최근 생성된 페이지 3개를 요약해서 "일일 회의록 테스트" 페이지로 만들어줘')
    assert title == "일일 회의록 테스트"
