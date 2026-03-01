from agent.loop import _should_run_atomic_overhaul


def test_atomic_overhaul_rollout_disabled():
    class _Settings:
        atomic_overhaul_enabled = False
        atomic_overhaul_shadow_mode = False
        atomic_overhaul_allowlist = None
        atomic_overhaul_traffic_percent = 100
        atomic_overhaul_legacy_fallback_enabled = True

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u1")
    assert serve is False
    assert shadow is False
    assert reason == "disabled"


def test_atomic_overhaul_rollout_allowlist_hit():
    class _Settings:
        atomic_overhaul_enabled = True
        atomic_overhaul_shadow_mode = False
        atomic_overhaul_allowlist = "u1,u2"
        atomic_overhaul_traffic_percent = 0
        atomic_overhaul_legacy_fallback_enabled = True

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u2")
    assert serve is True
    assert shadow is False
    assert reason == "allowlist"


def test_atomic_overhaul_rollout_allowlist_shadow_for_excluded_user():
    class _Settings:
        atomic_overhaul_enabled = True
        atomic_overhaul_shadow_mode = True
        atomic_overhaul_allowlist = "u1"
        atomic_overhaul_traffic_percent = 100
        atomic_overhaul_legacy_fallback_enabled = True

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u9")
    assert serve is False
    assert shadow is True
    assert reason == "allowlist_excluded_shadow"


def test_atomic_overhaul_rollout_percent_hit_or_shadow():
    class _Settings:
        atomic_overhaul_enabled = True
        atomic_overhaul_shadow_mode = True
        atomic_overhaul_allowlist = None
        atomic_overhaul_traffic_percent = 0
        atomic_overhaul_legacy_fallback_enabled = True

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u3")
    assert serve is False
    assert shadow is True
    assert reason == "rollout_0_shadow"


def test_atomic_overhaul_rollout_forced_when_legacy_disabled():
    class _Settings:
        atomic_overhaul_enabled = True
        atomic_overhaul_shadow_mode = False
        atomic_overhaul_allowlist = None
        atomic_overhaul_traffic_percent = 0
        atomic_overhaul_legacy_fallback_enabled = False

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u10")
    assert serve is True
    assert shadow is False
    assert reason == "forced_no_legacy_rollout_0_miss"


def test_atomic_overhaul_rollout_zero_percent_immediate_legacy_miss():
    class _Settings:
        atomic_overhaul_enabled = True
        atomic_overhaul_shadow_mode = False
        atomic_overhaul_allowlist = None
        atomic_overhaul_traffic_percent = 0
        atomic_overhaul_legacy_fallback_enabled = True

    serve, shadow, reason = _should_run_atomic_overhaul(settings=_Settings(), user_id="u_rollback")
    assert serve is False
    assert shadow is False
    assert reason == "rollout_0_miss"
