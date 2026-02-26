from types import SimpleNamespace

from app.routes.telegram import (
    _agent_error_guide,
    _autonomous_fallback_hint,
    _compose_telegram_response_text,
    _build_user_preface_template,
    _build_user_facing_message,
    _build_capabilities_message,
    _is_capabilities_query,
    _should_use_preface_llm,
    _truncate_telegram_message,
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
    assert not _should_use_preface_llm(ok=True, error_code="validation_error", execution_message="short")
    assert _should_use_preface_llm(ok=True, error_code=None, execution_message="x" * 120)
    assert not _should_use_preface_llm(ok=True, error_code=None, execution_message="짧은 결과")


def test_build_user_facing_message_validation_error_slot_prompt():
    text = _build_user_facing_message(
        ok=False,
        execution_message="입력이 필요합니다.",
        error_code="validation_error",
        slot_action="linear_create_issue",
        missing_slot="team_id",
    )
    assert "팀" in text
    assert "예:" in text
    assert "취소" in text


def test_build_user_facing_message_success_keeps_link():
    text = _build_user_facing_message(
        ok=True,
        execution_message="요청하신 작업을 완료했습니다.\n- 이슈 링크: https://linear.app/issue/OPT-1",
        error_code=None,
        slot_action=None,
        missing_slot=None,
    )
    assert "https://linear.app/issue/OPT-1" in text


def test_build_user_facing_message_success_keeps_multiline_body():
    text = _build_user_facing_message(
        ok=True,
        execution_message="### 사실\n- OPT-43: 로그인 버튼 클릭 시 404\n### 해결 방향\n- 라우팅 경로 확인",
        error_code=None,
        slot_action=None,
        missing_slot=None,
    )
    assert "### 사실" in text
    assert "### 해결 방향" in text


def test_build_user_facing_message_success_empty_body_uses_explicit_warning():
    text = _build_user_facing_message(
        ok=True,
        execution_message="",
        error_code=None,
        slot_action=None,
        missing_slot=None,
    )
    assert "결과 본문이 비어 있습니다" in text
    assert text != "요청하신 작업을 완료했습니다."


def test_truncate_telegram_message():
    source = "a" * 500
    out = _truncate_telegram_message(source, max_chars=140)
    assert len(out) <= 140
    assert "일부만 표시" in out


def test_compose_telegram_response_text_conversation_only():
    out = _compose_telegram_response_text(
        debug_report_enabled=False,
        user_message="대화형 응답",
        report_text="에이전트 실행 결과",
    )
    assert out == "대화형 응답"


def test_compose_telegram_response_text_conversation_with_debug():
    out = _compose_telegram_response_text(
        debug_report_enabled=True,
        user_message="대화형 응답",
        report_text="에이전트 실행 결과",
    )
    assert out.startswith("대화형 응답")
    assert "에이전트 실행 결과" in out


def test_compose_telegram_response_text_no_debug_hides_report():
    out = _compose_telegram_response_text(
        debug_report_enabled=False,
        user_message="대화형 응답",
        report_text="에이전트 실행 결과",
    )
    assert out == "대화형 응답"
