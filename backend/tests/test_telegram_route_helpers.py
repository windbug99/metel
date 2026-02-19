from app.routes.telegram import _agent_error_guide


def test_agent_error_guide_auth_error():
    guide = _agent_error_guide("auth_error")
    assert "오류 가이드" in guide
    assert "권한" in guide


def test_agent_error_guide_unknown():
    guide = _agent_error_guide("something_else")
    assert guide == ""
