from app.routes.telegram import _map_natural_text_to_command


def test_map_recent_created_pages_to_list_command():
    command, rest = _map_natural_text_to_command("노션에서 최근 생성된 페이지 3개 출력")
    assert command == ""
    assert rest == ""


def test_map_page_create_intent_to_create_command():
    command, rest = _map_natural_text_to_command("노션 페이지 생성해줘 주간 회의록")
    assert command == ""
    assert rest == ""


def test_map_data_source_query_to_agent_path():
    command, rest = _map_natural_text_to_command("노션 데이터소스 invalid-id 조회해줘")
    assert command == ""
    assert rest == ""


def test_map_append_intent_to_agent_path():
    command, rest = _map_natural_text_to_command('일일 회의록 테스트 페이지에 "액션 아이템: API 테스트 완료" 추가해줘')
    assert command == ""
    assert rest == ""


def test_map_status_word_inside_sentence_to_agent_path():
    command, rest = _map_natural_text_to_command("linear 이슈 업데이트 이슈: OPT-39 설명: 상태 재현됨, 우선순위: 2")
    assert command == ""
    assert rest == ""


def test_map_slot_like_status_text_to_agent_path():
    command, rest = _map_natural_text_to_command("설명: 로그인 버튼 클릭 시 상태 재현됨")
    assert command == ""
    assert rest == ""
