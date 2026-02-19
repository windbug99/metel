from app.routes.telegram import _agent_error_guide, _autonomous_fallback_hint


def test_agent_error_guide_auth_error():
    guide = _agent_error_guide("auth_error")
    assert "오류 가이드" in guide
    assert "권한" in guide


def test_agent_error_guide_unknown():
    guide = _agent_error_guide("something_else")
    assert guide == ""


def test_agent_error_guide_verification_failed_with_reason():
    guide = _agent_error_guide("verification_failed", "append_requires_append_block_children")
    assert "오류 가이드" in guide
    assert "자율 실행 결과" in guide
    assert "본문 추가" in guide


def test_autonomous_fallback_hint_known_reason():
    hint = _autonomous_fallback_hint("turn_limit")
    assert "turn 한도" in hint


def test_autonomous_fallback_hint_unknown_reason():
    hint = _autonomous_fallback_hint("unknown_reason")
    assert hint == ""
