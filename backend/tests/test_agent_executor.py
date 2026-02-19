from agent.executor import (
    _extract_output_title,
    _extract_requested_count,
    _extract_requested_line_count,
    _extract_target_page_title,
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


def test_extract_requested_line_count():
    count = _extract_requested_line_count("노션에서 Metel test page의 내용 중 상위 10줄 출력")
    assert count == 10
