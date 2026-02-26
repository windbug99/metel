from agent.transform_contracts import run_transform_contract


def test_filter_meeting_events_includes_meeting_only():
    payload = {
        "events": [
            {"id": "1", "summary": "주간 회의", "description": "팀 싱크"},
            {"id": "2", "summary": "점심", "description": "사내 식당"},
        ],
        "keyword_include": ["회의"],
    }
    result = run_transform_contract("filter_meeting_events", payload)
    assert result["source_count"] == 2
    assert result["meeting_count"] == 1
    assert result["meeting_events"][0]["id"] == "1"


def test_format_detailed_minutes_returns_notion_payload():
    payload = {
        "event": {
            "id": "evt-1",
            "title": "스프린트 계획 회의",
            "description": "다음 스프린트 범위 논의",
            "start": {"dateTime": "2026-02-26T10:00:00Z"},
            "end": {"dateTime": "2026-02-26T11:00:00Z"},
            "attendees": [{"email": "a@example.com"}, {"email": "b@example.com"}],
        }
    }
    result = run_transform_contract("format_detailed_minutes", payload)
    assert result["source_event_id"] == "evt-1"
    assert result["title"].startswith("회의록 초안 - ")
    assert isinstance(result["children"], list)
    assert len(result["children"]) >= 3


def test_format_detailed_minutes_enforces_title_and_body_limits():
    long_title = "회의" * 120
    long_description = "상세 설명 " * 1000
    payload = {
        "event": {
            "id": "evt-long",
            "title": long_title,
            "description": long_description,
        }
    }

    result = run_transform_contract("format_detailed_minutes", payload)
    assert len(result["title"]) <= 100
    assert len(result["children"]) <= 80
    for child in result["children"]:
        rich_text = (((child.get("paragraph") or {}).get("rich_text")) or [])
        content = str((((rich_text[0] if rich_text else {}).get("text") or {}).get("content") or ""))
        assert len(content) <= 1800


def test_format_linear_meeting_issue_returns_template_and_limits():
    payload = {
        "event": {
            "id": "evt-2",
            "title": "주간 회의",
            "description": "백로그 점검",
            "start": {"dateTime": "2026-02-26T10:00:00Z"},
            "end": {"dateTime": "2026-02-26T11:00:00Z"},
            "attendees": [{"email": "a@example.com"}],
        }
    }
    result = run_transform_contract("format_linear_meeting_issue", payload)
    assert result["source_event_id"] == "evt-2"
    assert result["title"].startswith("[회의] ")
    assert "회의 목적:" in result["description"]
    assert "논의 내용:" in result["description"]
    assert len(result["title"]) <= 200
    assert len(result["description"]) <= 7800
