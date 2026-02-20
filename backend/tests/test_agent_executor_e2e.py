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


def test_execute_spotify_recent_tracks_to_notion(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "spotify_get_recently_played":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {
                            "track": {
                                "name": "Song A",
                                "artists": [{"name": "Artist A"}],
                                "external_urls": {"spotify": "https://open.spotify.com/track/a"},
                            }
                        },
                        {
                            "track": {
                                "name": "Song B",
                                "artists": [{"name": "Artist B"}],
                                "external_urls": {"spotify": "https://open.spotify.com/track/b"},
                            }
                        }
                    ]
                },
            }
        if tool_name == "notion_create_page":
            return {"ok": True, "data": {"id": "page-lyrics", "url": "https://notion.so/page-lyrics"}}
        if tool_name == "notion_append_block_children":
            return {"ok": True, "data": {"results": []}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = AgentPlan(
        user_text="스포티파이에서 최근 들었던 10곡을 노션에 spotify10 새로운 페이지에 작성하세요",
        requirements=[AgentRequirement(summary="최근 재생곡 목록 페이지 생성")],
        target_services=["spotify", "notion"],
        selected_tools=["spotify_get_recently_played", "notion_create_page", "notion_append_block_children"],
        workflow_steps=[],
        notes=[],
    )

    result = asyncio.run(execute_agent_plan("user-1", plan))
    assert result.success is True
    assert "목록" in result.summary
    assert result.artifacts["created_page_title"] == "spotify10"
    assert result.artifacts["track_count"] == "2"
    assert [name for name, _ in calls] == [
        "spotify_get_recently_played",
        "notion_create_page",
        "notion_append_block_children",
    ]


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


def test_execute_notion_archive_flow_retries_with_delete_block(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30c50e84a3bf814d99f8d59defec4286",
                            "url": "https://notion.so/page-2",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "일일 회의록 테스트 2"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            raise HTTPException(status_code=400, detail="notion_update_page:BAD_REQUEST")
        if tool_name == "notion_delete_block":
            assert payload.get("block_id") == "30c50e84a3bf814d99f8d59defec4286"
            return {"ok": True, "data": {"id": payload["block_id"], "archived": True}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan("일일 회의록 테스트 2 페이지 삭제해줘", ["notion_delete_block"])
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "아카이브" in result.summary
    assert [item[0] for item in calls] == [
        "notion_search",
        "notion_delete_block",
    ]


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


def test_execute_notion_summary_create_with_delete_word_in_title(monkeypatch):
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
        '노션에서 "더 코어 3", "사이먼 블로그" 페이지를 요약해서 "삭제 테스트 페이지 1" 페이지로 만들어줘',
        ["notion_search", "notion_retrieve_block_children", "notion_create_page", "notion_append_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "요약/생성" in result.summary
    assert "삭제 테스트 페이지 1" in result.user_message
    assert any(name == "notion_create_page" for name, _ in calls)


def test_execute_notion_create_child_page_under_parent(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            assert payload.get("query") == "일일 회의록"
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30c50e84a3bf814d99f8d59defec4286",
                            "url": "https://notion.so/parent",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "일일 회의록"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_create_page":
            assert payload.get("parent", {}).get("page_id") == "30c50e84a3bf814d99f8d59defec4286"
            assert payload.get("properties", {}).get("title", {}).get("title", [])[0].get("text", {}).get("content") == "나의 일기"
            return {"ok": True, "data": {"id": "child-1", "url": "https://notion.so/child"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "일일 회의록 페이지 아래 나의 일기 페이지를 새로 생성하세요",
        ["notion_search", "notion_create_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "페이지 생성" in result.summary
    assert "나의 일기" in result.user_message
    assert [item[0] for item in calls] == ["notion_search", "notion_create_page"]


def test_execute_notion_move_page_under_parent(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            if payload.get("query") == "0219":
                return {
                    "ok": True,
                    "data": {
                        "results": [
                            {
                                "id": "30c50e84a3bf81d695aac8c93e049f66",
                                "url": "https://notion.so/0219",
                                "properties": {"title": {"type": "title", "title": [{"plain_text": "0219"}]}},
                            }
                        ]
                    },
                }
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30b50e84a3bf80b383f2df0f6ed47067",
                            "url": "https://notion.so/metel-test-page",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "Metel test page"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_update_page":
            assert payload.get("page_id") == "30c50e84a3bf81d695aac8c93e049f66"
            assert payload.get("parent", {}).get("page_id") == "30b50e84a3bf80b383f2df0f6ed47067"
            return {"ok": True, "data": {"id": payload["page_id"]}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "0219 페이지를 Metel test page 페이지 하위로 이동시키세요",
        ["notion_search", "notion_update_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "페이지 이동" in result.summary
    assert [item[0] for item in calls] == ["notion_search", "notion_search", "notion_update_page"]


def test_execute_notion_move_page_under_parent_with_possessive_phrase(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            if payload.get("query") == "일일 회의록":
                return {
                    "ok": True,
                    "data": {
                        "results": [
                            {
                                "id": "src-1",
                                "url": "https://notion.so/src-1",
                                "properties": {"title": {"type": "title", "title": [{"plain_text": "일일 회의록"}]}},
                            }
                        ]
                    },
                }
            if payload.get("query") == "Metel test page":
                return {
                    "ok": True,
                    "data": {
                        "results": [
                            {
                                "id": "parent-1",
                                "url": "https://notion.so/parent-1",
                                "properties": {
                                    "title": {"type": "title", "title": [{"plain_text": "Metel test page"}]}
                                },
                            }
                        ]
                    },
                }
        if tool_name == "notion_update_page":
            assert payload.get("page_id") == "src-1"
            assert payload.get("parent", {}).get("page_id") == "parent-1"
            return {"ok": True, "data": {"id": "src-1"}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)

    plan = _plan(
        "노션에서 일일 회의록 페이지를 Metel test page의 하위 페이지로 이동시키세요",
        ["notion_search", "notion_update_page"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "페이지 이동" in result.summary
    assert [item[0] for item in calls] == ["notion_search", "notion_search", "notion_update_page"]


def test_execute_notion_append_with_url_summary(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "notion_search":
            return {
                "ok": True,
                "data": {
                    "results": [
                        {
                            "id": "30c50e84a3bf81d695aac8c93e049f66",
                            "url": "https://notion.so/0219",
                            "properties": {"title": {"type": "title", "title": [{"plain_text": "0219"}]}},
                        }
                    ]
                },
            }
        if tool_name == "notion_retrieve_page":
            return {"ok": True, "data": {"id": "30c50e84a3bf81d695aac8c93e049f66"}}
        if tool_name == "notion_append_block_children":
            children = payload.get("children") or []
            assert children
            text = (
                children[0]
                .get("paragraph", {})
                .get("rich_text", [{}])[0]
                .get("text", {})
                .get("content", "")
            )
            assert text.startswith("요약문")
            assert len(text) <= 180
            return {"ok": True, "data": {"results": []}}
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_fetch_url_text(url: str):
        return "기사 원문입니다. " * 100

    async def _fake_summarize_text_with_llm(text: str, user_text: str):
        return ("요약문 " + ("A" * 400), "llm:openai:gpt-4o-mini")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    monkeypatch.setattr("agent.executor._fetch_url_plain_text", _fake_fetch_url_text)
    monkeypatch.setattr("agent.executor._summarize_text_with_llm", _fake_summarize_text_with_llm)

    plan = _plan(
        "다음 기사 내용을 180자로 요약해서 0219 페이지에 추가해줘 https://example.com/news",
        ["notion_search", "notion_retrieve_page", "notion_append_block_children"],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "내용을 추가" in result.summary


def test_execute_linear_list_teams(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "linear_list_teams":
            assert payload.get("first") == 20
            return {
                "ok": True,
                "data": {
                    "teams": {
                        "nodes": [
                            {"id": "team-1", "key": "MET", "name": "Metel Team"},
                            {"id": "team-2", "key": "OPS", "name": "Ops Team"},
                        ]
                    }
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    plan = AgentPlan(
        user_text="Linear 팀 목록 조회해줘",
        requirements=[AgentRequirement(summary="대상 데이터 조회")],
        target_services=["linear"],
        selected_tools=["linear_list_teams"],
        workflow_steps=[],
        notes=[],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "팀 목록" in result.summary
    assert calls[0][0] == "linear_list_teams"


def test_execute_linear_create_comment(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "linear_create_comment":
            return {
                "ok": True,
                "data": {
                    "commentCreate": {
                        "comment": {
                            "id": "comment-1",
                            "url": "https://linear.app/comment/1",
                        }
                    }
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    plan = AgentPlan(
        user_text="Linear 이슈 댓글 생성 issue_id 12345678-1234-1234-1234-1234567890ab 댓글: 확인 부탁드립니다",
        requirements=[AgentRequirement(summary="결과물 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_comment"],
        workflow_steps=[],
        notes=[],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "댓글" in result.summary
    assert calls[0][0] == "linear_create_comment"
    assert calls[0][1]["issue_id"] == "12345678-1234-1234-1234-1234567890ab"


def test_execute_linear_update_issue(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "linear_update_issue":
            return {
                "ok": True,
                "data": {
                    "issueUpdate": {
                        "issue": {
                            "id": "issue-1",
                            "identifier": "MET-201",
                            "title": "새 제목",
                            "url": "https://linear.app/issue/MET-201",
                        }
                    }
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    plan = AgentPlan(
        user_text="Linear 이슈 수정 issue_id 12345678-1234-1234-1234-1234567890ab 제목: 새 제목",
        requirements=[AgentRequirement(summary="기존 결과물 수정/추가")],
        target_services=["linear"],
        selected_tools=["linear_update_issue"],
        workflow_steps=[],
        notes=[],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "수정" in result.summary
    assert calls[0][0] == "linear_update_issue"
    assert calls[0][1]["title"] == "새 제목"


def test_execute_linear_create_issue_with_team_key(monkeypatch):
    calls = []

    async def _fake_execute_tool(user_id: str, tool_name: str, payload: dict):
        calls.append((tool_name, payload))
        if tool_name == "linear_list_teams":
            return {
                "ok": True,
                "data": {
                    "teams": {
                        "nodes": [
                            {"id": "team-operate-id", "key": "OPERATE", "name": "Operate Team"},
                            {"id": "team-other-id", "key": "OTHER", "name": "Other Team"},
                        ]
                    }
                },
            }
        if tool_name == "linear_create_issue":
            assert payload["team_id"] == "team-operate-id"
            assert payload["title"] == "구글로그인 구현"
            return {
                "ok": True,
                "data": {
                    "issueCreate": {
                        "issue": {
                            "id": "issue-1",
                            "identifier": "OPS-10",
                            "title": "구글로그인 구현",
                            "url": "https://linear.app/issue/OPS-10",
                        }
                    }
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    monkeypatch.setattr("agent.executor.execute_tool", _fake_execute_tool)
    plan = AgentPlan(
        user_text="노션의 구글로그인 구현 페이지를 linear의 새로운 이슈로 등록하세요. Linear team_id operate 제목: 구글로그인 구현",
        requirements=[AgentRequirement(summary="결과물 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue", "linear_list_teams"],
        workflow_steps=[],
        notes=[],
    )
    result = asyncio.run(execute_agent_plan("user-1", plan))

    assert result.success is True
    assert "생성" in result.summary
    assert calls[0][0] == "linear_list_teams"
    assert calls[1][0] == "linear_create_issue"
