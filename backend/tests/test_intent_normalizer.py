from agent import intent_normalizer


def test_extract_linear_issue_reference():
    assert intent_normalizer.extract_linear_issue_reference("linear opt-46 이슈 업데이트") == "opt-46"


def test_extract_notion_page_title_for_create_prefix_pattern():
    title = intent_normalizer.extract_notion_page_title_for_create("오늘 서울 날씨를 notion에 페이지로 생성해줘")
    assert title == "오늘 서울 날씨"


def test_extract_linear_update_description_text_modify_phrase():
    text = "linear opt-46 이슈의 본문을 패시브 서비스 추가, 링크 참조 로 수정하세요"
    extracted = intent_normalizer.extract_linear_update_description_text(text)
    assert extracted == "패시브 서비스 추가, 링크 참조"


def test_safe_int_and_count_limit():
    assert intent_normalizer.extract_count_limit("linear 최근 이슈 10개 검색") == 10
    assert intent_normalizer.safe_int("abc", default=5, minimum=1, maximum=20) == 5
