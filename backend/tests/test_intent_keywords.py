from agent.intent_keywords import (
    is_append_intent,
    is_create_intent,
    is_data_source_intent,
    is_delete_intent,
    is_linear_issue_create_intent,
    is_read_intent,
    is_summary_intent,
    is_update_intent,
)


def test_create_intent_matches_register_and_publish_variants():
    assert is_create_intent("linear 이슈로 등록해줘")
    assert is_create_intent("이 내용을 티켓으로 올려줘")
    assert is_create_intent("새 문서로 발행해줘")


def test_read_intent_matches_check_and_fetch_variants():
    assert is_read_intent("최근 이슈 확인해줘")
    assert is_read_intent("페이지 내용 가져와줘")
    assert is_read_intent("문서 읽어줘")


def test_other_intents_extended_keywords():
    assert is_summary_intent("핵심 정리해줘")
    assert is_update_intent("제목 반영해줘")
    assert is_delete_intent("이 페이지 제거해줘")
    assert is_append_intent("본문에 붙여줘")
    assert is_data_source_intent("notion database 최근 5개 조회")


def test_linear_issue_create_intent_matches_register_and_issue_create():
    assert is_linear_issue_create_intent("linear의 새로운 이슈로 등록하세요")
    assert is_linear_issue_create_intent("linear 이슈 생성해줘")
    assert is_linear_issue_create_intent("issue create 해줘")


def test_linear_issue_create_intent_does_not_match_issue_search_summary_case():
    text = "Linear의 기획관련 이슈를 찾아서 3문장으로 요약해 Notion의 새로운 페이지에 생성해서 저장하세요"
    assert is_linear_issue_create_intent(text) is False

