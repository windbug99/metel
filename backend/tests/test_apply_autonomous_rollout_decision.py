from scripts.apply_autonomous_rollout_decision import _apply_to_lines


def test_apply_autonomous_rollout_decision_updates_and_appends():
    lines = [
        "LLM_AUTONOMOUS_ENABLED=false",
        "OTHER_KEY=value",
    ]
    suggested = {
        "LLM_AUTONOMOUS_ENABLED": "true",
        "LLM_AUTONOMOUS_TRAFFIC_PERCENT": "30",
        "LLM_AUTONOMOUS_SHADOW_MODE": "false",
        "LLM_HYBRID_EXECUTOR_FIRST": "false",
    }
    result = _apply_to_lines(lines, suggested)
    assert lines[0] == "LLM_AUTONOMOUS_ENABLED=true"
    assert any(line == "LLM_AUTONOMOUS_TRAFFIC_PERCENT=30" for line in lines)
    assert any(line == "LLM_AUTONOMOUS_SHADOW_MODE=false" for line in lines)
    assert any(line == "LLM_HYBRID_EXECUTOR_FIRST=false" for line in lines)
    assert "LLM_AUTONOMOUS_ENABLED" in result.updated


def test_apply_autonomous_rollout_decision_skips_unknown_keys():
    lines = ["LLM_AUTONOMOUS_ENABLED=false"]
    suggested = {
        "UNSAFE_KEY": "1",
        "LLM_AUTONOMOUS_ENABLED": "true",
    }
    result = _apply_to_lines(lines, suggested)
    assert "UNSAFE_KEY" in result.skipped
    assert lines[0] == "LLM_AUTONOMOUS_ENABLED=true"
