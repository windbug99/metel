from app.routes.telegram import _map_natural_text_to_command


def test_map_recent_created_pages_to_list_command():
    command, rest = _map_natural_text_to_command("노션에서 최근 생성된 페이지 3개 출력")
    assert command == "/notion_pages"
    assert rest == "3"


def test_map_page_create_intent_to_create_command():
    command, rest = _map_natural_text_to_command("노션 페이지 생성해줘 주간 회의록")
    assert command == "/notion_create"
    assert "주간 회의록" in rest
