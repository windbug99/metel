from scripts.apply_skill_v2_rollout_decision import _apply_to_lines


def test_apply_to_lines_updates_existing_and_appends_missing():
    lines = [
        "SKILL_ROUTER_V2_ENABLED=false",
        "OTHER_KEY=keep",
    ]
    suggested = {
        "SKILL_ROUTER_V2_ENABLED": "true",
        "SKILL_RUNNER_V2_ENABLED": "true",
        "SKILL_V2_TRAFFIC_PERCENT": "30",
    }
    result = _apply_to_lines(lines, suggested)

    assert any(line == "SKILL_ROUTER_V2_ENABLED=true" for line in lines)
    assert any(line == "SKILL_RUNNER_V2_ENABLED=true" for line in lines)
    assert any(line == "SKILL_V2_TRAFFIC_PERCENT=30" for line in lines)
    assert any(line == "OTHER_KEY=keep" for line in lines)
    assert "SKILL_ROUTER_V2_ENABLED" in result.updated
    assert "SKILL_RUNNER_V2_ENABLED" in result.updated


def test_apply_to_lines_skips_non_allowlisted_keys():
    lines = []
    suggested = {
        "SKILL_V2_TRAFFIC_PERCENT": "10",
        "UNSAFE_KEY": "1",
    }
    result = _apply_to_lines(lines, suggested)

    assert any(line == "SKILL_V2_TRAFFIC_PERCENT=10" for line in lines)
    assert all("UNSAFE_KEY=" not in line for line in lines)
    assert "UNSAFE_KEY" in result.skipped
