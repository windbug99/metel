import os
from datetime import datetime, timezone

import httpx
import pytest


RUN_LIVE = os.getenv("RUN_NOTION_LIVE_TESTS", "false").lower() == "true"
RUN_WRITE = os.getenv("RUN_NOTION_LIVE_WRITE_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(not RUN_LIVE, reason="set RUN_NOTION_LIVE_TESTS=true to run live Notion integration tests")


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"missing env: {name}")
    return value


def _headers(token: str) -> dict[str, str]:
    notion_version = os.getenv("NOTION_LIVE_API_VERSION", "2025-09-03")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }


def _assert_token_is_valid(token: str) -> None:
    response = httpx.get(
        "https://api.notion.com/v1/users/me",
        headers=_headers(token),
        timeout=20,
    )
    if response.status_code < 400:
        return
    detail = response.text
    raise AssertionError(
        "NOTION_LIVE_TOKEN이 유효하지 않습니다. "
        "Notion Integration의 API 토큰(또는 유효한 OAuth access token)으로 설정해주세요. "
        f"users/me 응답: {detail}"
    )


def test_notion_live_search_pages():
    token = _env("NOTION_LIVE_TOKEN")
    _assert_token_is_valid(token)
    query = os.getenv("NOTION_LIVE_QUERY", "Metel").strip()

    response = httpx.post(
        "https://api.notion.com/v1/search",
        headers=_headers(token),
        json={
            "query": query,
            "filter": {"property": "object", "value": "page"},
            "page_size": 3,
        },
        timeout=20,
    )
    assert response.status_code < 400, response.text
    payload = response.json()
    assert "results" in payload


def test_notion_live_retrieve_block_children():
    token = _env("NOTION_LIVE_TOKEN")
    _assert_token_is_valid(token)
    block_id = _env("NOTION_LIVE_PAGE_ID")

    response = httpx.get(
        f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=10",
        headers=_headers(token),
        timeout=20,
    )
    assert response.status_code < 400, response.text
    payload = response.json()
    assert "results" in payload


def test_notion_live_query_data_source():
    token = _env("NOTION_LIVE_TOKEN")
    _assert_token_is_valid(token)
    data_source_id = _env("NOTION_LIVE_DATA_SOURCE_ID")

    response = httpx.post(
        f"https://api.notion.com/v1/data_sources/{data_source_id}/query",
        headers=_headers(token),
        json={"page_size": 3},
        timeout=20,
    )
    assert response.status_code < 400, response.text
    payload = response.json()
    assert "results" in payload


@pytest.mark.skipif(not RUN_WRITE, reason="set RUN_NOTION_LIVE_WRITE_TESTS=true to run write tests")
def test_notion_live_update_page_title_roundtrip():
    token = _env("NOTION_LIVE_TOKEN")
    _assert_token_is_valid(token)
    page_id = _env("NOTION_LIVE_PAGE_ID")
    base_title = os.getenv("NOTION_LIVE_BASE_TITLE", "Metel Live Test").strip()
    new_title = f"{base_title} {datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    update_resp = httpx.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(token),
        json={
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": new_title},
                        }
                    ]
                }
            }
        },
        timeout=20,
    )
    assert update_resp.status_code < 400, update_resp.text

    revert_resp = httpx.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(token),
        json={
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": base_title},
                        }
                    ]
                }
            }
        },
        timeout=20,
    )
    assert revert_resp.status_code < 400, revert_resp.text


@pytest.mark.skipif(not RUN_WRITE, reason="set RUN_NOTION_LIVE_WRITE_TESTS=true to run write tests")
def test_notion_live_append_block_children():
    token = _env("NOTION_LIVE_TOKEN")
    _assert_token_is_valid(token)
    block_id = _env("NOTION_LIVE_PAGE_ID")
    marker = f"[metel-live] append test {datetime.now(timezone.utc).isoformat()}"

    response = httpx.patch(
        f"https://api.notion.com/v1/blocks/{block_id}/children",
        headers=_headers(token),
        json={
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": marker},
                            }
                        ]
                    },
                }
            ]
        },
        timeout=20,
    )
    assert response.status_code < 400, response.text
    payload = response.json()
    assert "results" in payload
