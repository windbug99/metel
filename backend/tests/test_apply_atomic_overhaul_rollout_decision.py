from scripts.apply_atomic_overhaul_rollout_decision import _apply_to_lines


def test_apply_to_lines_updates_existing_and_appends_missing():
    lines = [
        "ATOMIC_OVERHAUL_ENABLED=false",
        "OTHER_KEY=keep",
    ]
    suggested = {
        "ATOMIC_OVERHAUL_ENABLED": "true",
        "ATOMIC_OVERHAUL_SHADOW_MODE": "false",
        "ATOMIC_OVERHAUL_TRAFFIC_PERCENT": "30",
        "ATOMIC_OVERHAUL_LEGACY_FALLBACK_ENABLED": "true",
    }
    result = _apply_to_lines(lines, suggested)

    assert any(line == "ATOMIC_OVERHAUL_ENABLED=true" for line in lines)
    assert any(line == "ATOMIC_OVERHAUL_SHADOW_MODE=false" for line in lines)
    assert any(line == "ATOMIC_OVERHAUL_TRAFFIC_PERCENT=30" for line in lines)
    assert any(line == "ATOMIC_OVERHAUL_LEGACY_FALLBACK_ENABLED=true" for line in lines)
    assert any(line == "OTHER_KEY=keep" for line in lines)
    assert "ATOMIC_OVERHAUL_ENABLED" in result.updated
    assert "ATOMIC_OVERHAUL_SHADOW_MODE" in result.updated


def test_apply_to_lines_skips_non_allowlisted_keys():
    lines = []
    suggested = {
        "ATOMIC_OVERHAUL_TRAFFIC_PERCENT": "10",
        "UNSAFE_KEY": "1",
    }
    result = _apply_to_lines(lines, suggested)

    assert any(line == "ATOMIC_OVERHAUL_TRAFFIC_PERCENT=10" for line in lines)
    assert all("UNSAFE_KEY=" not in line for line in lines)
    assert "UNSAFE_KEY" in result.skipped
