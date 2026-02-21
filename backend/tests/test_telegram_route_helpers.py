from types import SimpleNamespace

from app.routes.telegram import (
    _agent_error_guide,
    _autonomous_fallback_hint,
    _build_user_preface_template,
    _build_capabilities_message,
    _is_capabilities_query,
    _should_use_preface_llm,
)


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


def test_agent_error_guide_verification_failed_multiple_targets():
    guide = _agent_error_guide("verification_failed", "append_requires_multiple_targets")
    assert "오류 가이드" in guide
    assert "여러 페이지 각각" in guide


def test_autonomous_fallback_hint_multiple_targets():
    hint = _autonomous_fallback_hint("append_requires_multiple_targets")
    assert "일부 페이지만" in hint


def test_autonomous_fallback_hint_unknown_reason():
    hint = _autonomous_fallback_hint("unknown_reason")
    assert hint == ""


def test_is_capabilities_query_matches_korean_and_english():
    assert _is_capabilities_query("Notion으로 할 수 있는 작업이 뭐야?")
    assert _is_capabilities_query("linear capabilities")
    assert _is_capabilities_query("지원 기능 알려줘")


def test_build_capabilities_message_single_target(monkeypatch):
    registry = SimpleNamespace(
        list_tools=lambda service: [
            SimpleNamespace(tool_name="notion_search", description="Search pages"),
            SimpleNamespace(tool_name="notion_create_page", description="Create page"),
        ]
        if service == "notion"
        else [],
        list_services=lambda: ["notion", "linear"],
    )
    monkeypatch.setattr("app.routes.telegram.load_registry", lambda: registry)
    monkeypatch.setattr("app.routes.telegram.resolve_primary_service", lambda text, connected_services: "notion")

    msg, target = _build_capabilities_message("Notion으로 할 수 있는 작업이 뭐야?", ["notion", "linear"])
    assert target == "notion"
    assert "[notion] 지원 API/기능" in msg
    assert "notion_search" in msg
    assert "notion_create_page" in msg


def test_build_capabilities_message_all_connected_services(monkeypatch):
    def _list_tools(service):
        if service == "notion":
            return [SimpleNamespace(tool_name="notion_search", description="Search pages")]
        if service == "linear":
            return [SimpleNamespace(tool_name="linear_create_issue", description="Create issue")]
        return []

    registry = SimpleNamespace(
        list_tools=_list_tools,
        list_services=lambda: ["notion", "linear", "spotify"],
    )
    monkeypatch.setattr("app.routes.telegram.load_registry", lambda: registry)
    monkeypatch.setattr("app.routes.telegram.resolve_primary_service", lambda text, connected_services: None)

    msg, target = _build_capabilities_message("할 수 있는 작업 알려줘", ["notion", "linear"])
    assert target is None
    assert "[notion] 지원 API/기능" in msg
    assert "[linear] 지원 API/기능" in msg
    assert "linear_create_issue" in msg


def test_build_user_preface_template_success():
    text = _build_user_preface_template(ok=True, error_code=None, execution_message="요청하신 작업을 완료했습니다.")
    assert "완료" in text


def test_build_user_preface_template_validation_error():
    text = _build_user_preface_template(ok=False, error_code="validation_error", execution_message="입력이 필요합니다.")
    assert "입력값" in text
    assert "보완" in text


def test_should_use_preface_llm():
    assert _should_use_preface_llm(ok=False, error_code=None, execution_message="short")
    assert _should_use_preface_llm(ok=True, error_code="validation_error", execution_message="short")
    assert _should_use_preface_llm(ok=True, error_code=None, execution_message="x" * 120)
    assert not _should_use_preface_llm(ok=True, error_code=None, execution_message="짧은 결과")
