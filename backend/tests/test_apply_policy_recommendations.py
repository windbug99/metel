from scripts.apply_agent_policy_recommendations import _apply_recommendations_to_lines


def test_apply_recommendations_updates_existing_and_appends_missing():
    lines = [
        "LLM_AUTONOMOUS_MAX_TURNS=6",
        "OTHER_KEY=value",
    ]
    recs = [
        {"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "r1"},
        {"env_key": "LLM_AUTONOMOUS_TIMEOUT_SEC", "suggested_value": "60", "reason": "r2"},
    ]
    result = _apply_recommendations_to_lines(lines, recs)

    assert lines[0] == "LLM_AUTONOMOUS_MAX_TURNS=8"
    assert any(line == "LLM_AUTONOMOUS_TIMEOUT_SEC=60" for line in lines)
    assert result.updated["LLM_AUTONOMOUS_MAX_TURNS"] == ("6", "8")
    assert result.updated["LLM_AUTONOMOUS_TIMEOUT_SEC"] == (None, "60")


def test_apply_recommendations_skips_non_allowlisted_keys():
    lines = ["LLM_AUTONOMOUS_MAX_TURNS=6"]
    recs = [
        {"env_key": "UNSAFE_KEY", "suggested_value": "1", "reason": "skip"},
        {"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "ok"},
    ]
    result = _apply_recommendations_to_lines(lines, recs)

    assert "UNSAFE_KEY" in result.skipped
    assert lines[0] == "LLM_AUTONOMOUS_MAX_TURNS=8"


def test_apply_recommendations_no_change_when_same_value():
    lines = ["LLM_AUTONOMOUS_MAX_TURNS=8"]
    recs = [{"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "same"}]
    result = _apply_recommendations_to_lines(lines, recs)

    assert result.updated == {}
    assert result.untouched == 1
