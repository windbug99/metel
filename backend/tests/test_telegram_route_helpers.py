from types import SimpleNamespace

from app.routes.telegram import (
    _agent_error_guide,
    _autonomous_fallback_hint,
    _build_structured_pipeline_log,
    _compose_telegram_response_text,
    _build_user_preface_template,
    _build_user_facing_message,
    _build_capabilities_message,
    _build_status_message,
    _build_service_help_message,
    _is_capabilities_query,
    _map_natural_text_to_command,
    _normalize_help_target,
    _should_use_preface_llm,
    _truncate_telegram_message,
    _record_pipeline_step_logs,
)


def test_agent_error_guide_auth_error():
    guide = _agent_error_guide("auth_error")
    assert "오류 가이드" in guide
    assert "권한" in guide


def test_agent_error_guide_unknown():
    guide = _agent_error_guide("something_else")
    assert guide == ""


def test_agent_error_guide_risk_gate_blocked():
    guide = _agent_error_guide("risk_gate_blocked")
    assert "오류 가이드" in guide
    assert "승인" in guide


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


def test_map_natural_text_to_command_help_with_target():
    command, rest = _map_natural_text_to_command("/help linear")
    assert command == "/help"
    assert rest == "linear"


def test_normalize_help_target_with_korean_alias(monkeypatch):
    monkeypatch.setattr("app.routes.telegram.load_registry", lambda: SimpleNamespace(list_services=lambda: ["linear", "notion"]))
    target = _normalize_help_target("리니어", ["linear", "notion"])
    assert target == "linear"


def test_build_service_help_message_filters_unavailable_features():
    msg = _build_service_help_message("linear", {"linear_list_issues", "linear_search_issues"})
    assert "최근 이슈 조회" in msg
    assert "이슈 검색" in msg
    assert "이슈 생성" not in msg


def test_build_status_message_includes_connected_and_disconnected_services(monkeypatch):
    monkeypatch.setattr("app.routes.telegram.load_registry", lambda: SimpleNamespace(list_services=lambda: ["google", "linear", "notion", "spotify", "web"]))
    msg = _build_status_message(["linear", "notion"])
    assert "- Telegram: 연결됨" in msg
    assert "- linear: 연결됨" in msg
    assert "- notion: 연결됨" in msg
    assert "- google: 미연결" in msg
    assert "- spotify: 미연결" in msg


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
    assert ("팀" in text) or ("team_id" in text)
    assert "예:" in text
    assert "취소" in text


def test_build_user_facing_message_clarification_keeps_original_message():
    text = _build_user_facing_message(
        ok=False,
        execution_message="파괴적 작업입니다. 진행하려면 `yes` 또는 `승인`이라고 입력해주세요.",
        error_code="risk_gate_blocked",
        slot_action=None,
        missing_slot="approval_confirmed",
    )
    assert "yes" in text
    assert "승인" in text


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


def test_record_pipeline_step_logs_from_stepwise_results(monkeypatch):
    inserted_rows: list[dict] = []

    class _FakeTable:
        def insert(self, payload):
            if isinstance(payload, list):
                inserted_rows.extend(payload)
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name: str):
            assert name == "pipeline_step_logs"
            return _FakeTable()

    class _Settings:
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "service-role"

    monkeypatch.setattr("app.routes.telegram.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.routes.telegram.create_client", lambda *_args, **_kwargs: _FakeSupabase())

    execution = SimpleNamespace(
        artifacts={
            "router_mode": "STEPWISE_PIPELINE",
            "pipeline_run_id": "prun_stepwise_1",
            "catalog_id": "catalog_abc",
            "stepwise_results_json": '[{"task_id":"step_1","tool_name":"notion_search","result":{"ok":true}}]',
        }
    )
    _record_pipeline_step_logs(user_id="u1", request_id="req_1", execution=execution)
    assert len(inserted_rows) == 1
    assert inserted_rows[0].get("run_id") == "prun_stepwise_1"
    assert inserted_rows[0].get("task_id") == "step_1"
    assert inserted_rows[0].get("service") == "notion"
    assert inserted_rows[0].get("api") == "notion_search"
    assert inserted_rows[0].get("catalog_id") == "catalog_abc"


def test_record_pipeline_step_logs_from_stepwise_failure(monkeypatch):
    inserted_rows: list[dict] = []

    class _FakeTable:
        def insert(self, payload):
            if isinstance(payload, list):
                inserted_rows.extend(payload)
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name: str):
            assert name == "pipeline_step_logs"
            return _FakeTable()

    class _Settings:
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "service-role"

    monkeypatch.setattr("app.routes.telegram.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.routes.telegram.create_client", lambda *_args, **_kwargs: _FakeSupabase())

    execution = SimpleNamespace(
        artifacts={
            "router_mode": "STEPWISE_PIPELINE",
            "error_code": "missing_required_fields",
            "failed_task_id": "step_2",
            "failure_reason": "missing_required_fields:title",
            "missing_required_fields": "[\"title\"]",
            "failed_service": "linear",
            "failed_api": "linear_create_issue",
        }
    )
    _record_pipeline_step_logs(user_id="u1", request_id="req_fail", execution=execution)
    assert len(inserted_rows) == 1
    assert inserted_rows[0].get("task_id") == "step_2"
    assert inserted_rows[0].get("call_status") == "skipped"
    assert inserted_rows[0].get("service") == "linear"
    assert inserted_rows[0].get("api") == "linear_create_issue"
    assert inserted_rows[0].get("missing_required_fields") == ["title"]


def test_record_pipeline_step_logs_atomic_fallback_rows(monkeypatch):
    inserted_rows: list[dict] = []

    class _FakeTable:
        def insert(self, payload):
            if isinstance(payload, list):
                inserted_rows.extend(payload)
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _FakeSupabase:
        def table(self, name: str):
            assert name == "pipeline_step_logs"
            return _FakeTable()

    class _Settings:
        supabase_url = "https://example.supabase.co"
        supabase_service_role_key = "service-role"

    monkeypatch.setattr("app.routes.telegram.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.routes.telegram.create_client", lambda *_args, **_kwargs: _FakeSupabase())

    execution = SimpleNamespace(
        artifacts={
            "tool_name": "linear_list_issues",
            "verified": "1",
            "verification_reason": "list_verified",
            "verification_checks": '{"count_match": true, "format_match": true}',
        }
    )
    _record_pipeline_step_logs(user_id="u_atomic", request_id="req_atomic", execution=execution)
    assert len(inserted_rows) == 2
    assert inserted_rows[0].get("task_id") == "tool:linear_list_issues"
    assert inserted_rows[0].get("service") == "linear"
    assert inserted_rows[0].get("api") == "linear_list_issues"
    assert inserted_rows[1].get("task_id") == "expectation_verification"
    assert inserted_rows[1].get("call_status") == "succeeded"


def test_build_structured_pipeline_log_stepwise_metrics_success():
    execution = SimpleNamespace(
        steps=[
            SimpleNamespace(name="step_1", status="success"),
            SimpleNamespace(name="step_2", status="success"),
        ],
        artifacts={
            "router_mode": "STEPWISE_PIPELINE",
            "stepwise_results_json": (
                '[{"task_id":"step_1","tool_name":"google_calendar_list_events","attempts":1,"result":{"events":[]}},'
                '{"task_id":"step_2","tool_name":"linear_create_issue","attempts":2,"result":{"issue":{"id":"I-1"}}}]'
            ),
        },
    )
    payload = _build_structured_pipeline_log(execution=execution, dag_pipeline=False)
    assert payload.get("router_mode") == "STEPWISE_PIPELINE"
    assert payload.get("stepwise_step_count") == 2
    assert payload.get("stepwise_success_step_count") == 2
    assert payload.get("stepwise_failed_step_count") == 0
    assert payload.get("stepwise_retry_step_count") == 1
    assert payload.get("stepwise_retry_total") == 1
    assert payload.get("stepwise_validation_fail_count") == 0


def test_build_structured_pipeline_log_stepwise_metrics_failure():
    execution = SimpleNamespace(
        steps=[SimpleNamespace(name="step_1", status="error")],
        artifacts={
            "router_mode": "STEPWISE_PIPELINE",
            "error_code": "missing_required_fields",
            "failed_task_id": "step_1",
        },
    )
    payload = _build_structured_pipeline_log(execution=execution, dag_pipeline=False)
    assert payload.get("stepwise_step_count") == 0
    assert payload.get("stepwise_success_step_count") == 0
    assert payload.get("stepwise_failed_step_count") == 1
    assert payload.get("stepwise_validation_fail_count") == 1
    assert payload.get("stepwise_failed_task_id") == "step_1"
