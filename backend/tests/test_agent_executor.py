from agent.executor import (
    _extract_data_source_query_request,
    _extract_append_target_and_content,
    _extract_output_title,
    _extract_page_archive_target,
    _extract_page_rename_request,
    _extract_requested_count,
    _extract_requested_line_count,
    _extract_summary_line_count,
    _extract_target_page_title,
    _requires_spotify_recent_tracks_to_notion,
)
from agent.types import AgentPlan, AgentRequirement


def _build_plan(user_text: str, quantity: int | None = None) -> AgentPlan:
    req = AgentRequirement(summary="대상 콘텐츠 요약", quantity=quantity)
    return AgentPlan(
        user_text=user_text,
        requirements=[req],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=[],
        notes=[],
    )


def test_extract_requested_count():
    plan = _build_plan("최근 5개 요약", quantity=5)
    assert _extract_requested_count(plan) == 5


def test_extract_output_title():
    title = _extract_output_title("노션에서 최근 3개 페이지를 요약해서 주간 회의록으로 생성해줘")
    assert title == "주간 회의록"


def test_extract_target_page_title():
    title = _extract_target_page_title("노션에서 Metel test page의 내용 중 상위 10줄 출력")
    assert title == "Metel test page"


def test_extract_target_page_title_summary_pattern():
    title = _extract_target_page_title("노션에서 Metel test page 요약해줘")
    assert title == "Metel test page"


def test_extract_requested_line_count():
    count = _extract_requested_line_count("노션에서 Metel test page의 내용 중 상위 10줄 출력")
    assert count == 10


def test_extract_append_target_and_content():
    title, content = _extract_append_target_and_content("노션에서 Metel test page에 액션 아이템 추가해줘")
    assert title == "Metel test page"
    assert content == "액션 아이템"


def test_extract_page_rename_request():
    title, new_title = _extract_page_rename_request("노션에서 Metel test page 페이지 제목을 주간 회의록으로 변경")
    assert title == "Metel test page"
    assert new_title == "주간 회의록"

    title2, new_title2 = _extract_page_rename_request('더 코어 페이지 제목을 "더 코어 2"로 바꾸고')
    assert title2 == "더 코어"
    assert new_title2 == "더 코어 2"


def test_extract_data_source_query_request():
    source_id, page_size, parse_error = _extract_data_source_query_request(
        "노션 데이터소스 12345678-1234-1234-1234-1234567890ab 최근 7개 조회"
    )
    assert source_id == "12345678-1234-1234-1234-1234567890ab"
    assert page_size == 7
    assert parse_error is None


def test_extract_data_source_query_request_invalid_id():
    source_id, page_size, parse_error = _extract_data_source_query_request(
        "노션 데이터소스 invalid-id 조회해줘"
    )
    assert source_id is None
    assert page_size == 5
    assert parse_error == "invalid"


def test_extract_summary_line_count():
    assert _extract_summary_line_count("노션에서 더 코어 2 페이지 내용을 1줄 요약해줘") == 1


def test_extract_page_archive_target():
    title = _extract_page_archive_target("노션에서 Metel test page 페이지 삭제해줘")
    assert title == "Metel test page"


def test_requires_spotify_recent_tracks_to_notion():
    plan = _build_plan("스포티파이에서 최근 들었던 10곡을 노션에 spotify10 새로운 페이지에 작성하세요")
    assert _requires_spotify_recent_tracks_to_notion(plan) is True
