from agent.slot_collector import collect_slots_from_user_reply, slot_prompt_example


def test_slot_collector_parses_keyed_values():
    result = collect_slots_from_user_reply(
        action="linear_update_issue",
        user_text="이슈: OPT-36 본문: 로그인 버튼 클릭 시 오류",
        collected_slots={},
    )
    assert result.collected_slots.get("issue_id") == "OPT-36"
    assert result.collected_slots.get("description") == "로그인 버튼 클릭 시 오류"
    assert result.validation_errors == []
    assert result.missing_slots == []
    assert result.ask_next_slot is None


def test_slot_collector_uses_preferred_slot_for_plain_answer():
    result = collect_slots_from_user_reply(
        action="linear_create_issue",
        user_text="로그인 오류 수정",
        collected_slots={},
        preferred_slot="title",
    )
    assert result.collected_slots.get("title") == "로그인 오류 수정"
    assert result.ask_next_slot == "team_id"


def test_slot_prompt_example():
    assert "이슈" in slot_prompt_example("linear_update_issue", "issue_id")
