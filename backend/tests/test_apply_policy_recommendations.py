import json

from scripts.apply_agent_policy_recommendations import _apply_recommendations_to_lines, _load_policy_recommendations_from_paths


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


def test_apply_recommendations_accepts_hybrid_allowlisted_keys():
    lines = ["LLM_HYBRID_EXECUTOR_FIRST=false"]
    recs = [
        {"env_key": "LLM_HYBRID_EXECUTOR_FIRST", "suggested_value": "true", "reason": "stability"},
        {"env_key": "LLM_AUTONOMOUS_STRICT_TOOL_SCOPE", "suggested_value": "true", "reason": "scope"},
    ]
    result = _apply_recommendations_to_lines(lines, recs)

    assert "LLM_HYBRID_EXECUTOR_FIRST" in result.updated
    assert any(line == "LLM_HYBRID_EXECUTOR_FIRST=true" for line in lines)
    assert any(line == "LLM_AUTONOMOUS_STRICT_TOOL_SCOPE=true" for line in lines)


def test_apply_recommendations_no_change_when_same_value():
    lines = ["LLM_AUTONOMOUS_MAX_TURNS=8"]
    recs = [{"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "same"}]
    result = _apply_recommendations_to_lines(lines, recs)

    assert result.updated == {}
    assert result.untouched == 1


def test_load_policy_recommendations_from_paths_merges_and_dedupes(tmp_path):
    p1 = tmp_path / "r1.json"
    p2 = tmp_path / "r2.json"
    p1.write_text(
        json.dumps(
            {
                "policy_recommendations": [
                    {"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "a"},
                    {"env_key": "LLM_HYBRID_EXECUTOR_FIRST", "suggested_value": "true", "reason": "b"},
                ]
            }
        ),
        encoding="utf-8",
    )
    p2.write_text(
        json.dumps(
            {
                "policy_recommendations": [
                    {"env_key": "LLM_AUTONOMOUS_MAX_TURNS", "suggested_value": "8", "reason": "dup"},
                    {"env_key": "TOOL_SPECS_VALIDATE_ON_STARTUP", "suggested_value": "true", "reason": "c"},
                ]
            }
        ),
        encoding="utf-8",
    )
    recs = _load_policy_recommendations_from_paths([p1, p2])
    assert len(recs) == 3
    keys = {(item["env_key"], item["suggested_value"]) for item in recs}
    assert ("LLM_AUTONOMOUS_MAX_TURNS", "8") in keys
    assert ("LLM_HYBRID_EXECUTOR_FIRST", "true") in keys
    assert ("TOOL_SPECS_VALIDATE_ON_STARTUP", "true") in keys
