from scripts.eval_skill_v2_rollout import _as_int, _parse_detail_pairs, _percentile


def test_parse_detail_pairs_empty():
    assert _parse_detail_pairs("") == {}
    assert _parse_detail_pairs(None) == {}


def test_parse_detail_pairs_extracts_kv_tokens():
    detail = "services=notion;skill_v2_rollout=rollout_10;skill_v2_shadow_executed=1;router_source=llm"
    parsed = _parse_detail_pairs(detail)
    assert parsed["services"] == "notion"
    assert parsed["skill_v2_rollout"] == "rollout_10"
    assert parsed["skill_v2_shadow_executed"] == "1"
    assert parsed["router_source"] == "llm"


def test_as_int_and_percentile_helpers():
    assert _as_int("123") == 123
    assert _as_int("abc") is None
    assert _percentile([], 0.95) == 0
    assert _percentile([10], 0.95) == 10
    assert _percentile([10, 20, 30, 40], 0.5) == 25
