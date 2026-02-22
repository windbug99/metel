import asyncio
import httpx

from agent.loop import _plan_consistency_reason, run_agent_analysis
from agent.pending_action import PendingActionStorageError, clear_pending_action, get_pending_action
from agent.types import AgentExecutionResult, AgentExecutionStep, AgentPlan, AgentRequirement, AgentRunResult, AgentTask


def _sample_plan() -> AgentPlan:
    return AgentPlan(
        user_text="노션에서 최근 페이지 3개 조회",
        requirements=[AgentRequirement(summary="대상 데이터 조회", quantity=3)],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=["1", "2"],
        notes=[],
    )


def test_run_agent_analysis_slot_question_and_resume(monkeypatch):
    clear_pending_action("user-slot")
    llm_plan = AgentPlan(
        user_text="Linear 이슈 생성해줘",
        requirements=[AgentRequirement(summary="Linear 이슈 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1. create"],
        tasks=[
            AgentTask(
                id="task_linear_create_issue",
                title="Linear 이슈 생성",
                task_type="TOOL",
                service="linear",
                tool_name="linear_create_issue",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = True
        slot_loop_rollout_percent = 100

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls = {"count": 0}

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="title missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_create_issue",
                    "slot_task_id": "task_linear_create_issue",
                    "missing_slot": "title",
                    "missing_slots": "title",
                    "slot_payload_json": "{}",
                },
            )
        if calls["count"] == 2:
            task = plan.tasks[0]
            assert task.payload.get("title") == "로그인 오류 수정"
            return AgentExecutionResult(
                success=False,
                user_message='`team_id` 값을 먼저 알려주세요.\n예: 팀: "값"',
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_create_issue",
                    "slot_task_id": "task_linear_create_issue",
                    "missing_slot": "team_id",
                    "missing_slots": "team_id",
                    "slot_payload_json": '{"title":"로그인 오류 수정"}',
                },
            )
        task = plan.tasks[0]
        assert task.payload.get("title") == "로그인 오류 수정"
        assert task.payload.get("team_id") == "team_123"
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    first = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-slot"))
    assert first.ok is False
    assert first.execution is not None
    assert "제목" in first.execution.user_message
    assert "취소" in first.execution.user_message
    assert get_pending_action("user-slot") is not None

    second = asyncio.run(run_agent_analysis('제목: "로그인 오류 수정"', ["linear"], "user-slot"))
    assert second.ok is False
    assert second.execution is not None
    assert "팀" in second.execution.user_message
    assert get_pending_action("user-slot") is not None

    third = asyncio.run(run_agent_analysis('팀: "team_123"', ["linear"], "user-slot"))
    assert third.ok is True
    assert third.result_summary == "done"
    assert get_pending_action("user-slot") is None
    clear_pending_action("user-slot")


def test_run_agent_analysis_accepts_plain_slot_answer_without_key_prefix(monkeypatch):
    clear_pending_action("user-low-confidence")
    llm_plan = AgentPlan(
        user_text="Linear 이슈 생성해줘",
        requirements=[AgentRequirement(summary="Linear 이슈 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1. create"],
        tasks=[
            AgentTask(
                id="task_linear_create_issue",
                title="Linear 이슈 생성",
                task_type="TOOL",
                service="linear",
                tool_name="linear_create_issue",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    calls = {"count": 0}
    pending_store: dict[str, object] = {}

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="title missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_create_issue",
                    "slot_task_id": "task_linear_create_issue",
                    "missing_slot": "title",
                    "missing_slots": "title",
                    "slot_payload_json": "{}",
                },
            )
        task = plan.tasks[0]
        assert task.payload.get("title") == "로그인 오류 수정"
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.set_pending_action", lambda **kwargs: pending_store.__setitem__(kwargs["user_id"], kwargs))
    monkeypatch.setattr("agent.loop.clear_pending_action", lambda user_id: pending_store.pop(user_id, None))

    class _PendingObj:
        def __init__(self, payload):
            self.user_id = payload["user_id"]
            self.intent = payload["intent"]
            self.action = payload["action"]
            self.task_id = payload["task_id"]
            self.plan = payload["plan"]
            self.plan_source = payload["plan_source"]
            self.collected_slots = dict(payload["collected_slots"])
            self.missing_slots = list(payload["missing_slots"])

    monkeypatch.setattr("agent.loop.get_pending_action", lambda user_id: (_PendingObj(pending_store[user_id]) if user_id in pending_store else None))

    first = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-low-confidence"))
    assert first.ok is False
    assert "user-low-confidence" in pending_store

    second = asyncio.run(run_agent_analysis("로그인 오류 수정", ["linear"], "user-low-confidence"))
    assert second.ok is True
    assert second.result_summary == "done"
    assert "user-low-confidence" not in pending_store
    clear_pending_action("user-low-confidence")


def test_run_agent_analysis_accepts_plain_id_for_action_without_slot_schema(monkeypatch):
    clear_pending_action("user-notion-page-id")
    llm_plan = AgentPlan(
        user_text="notion 페이지에 블록 추가",
        requirements=[AgentRequirement(summary="Notion 페이지 블록 추가")],
        target_services=["notion"],
        selected_tools=["notion_retrieve_page", "notion_append_block_children"],
        workflow_steps=["1"],
        tasks=[
            AgentTask(
                id="task_tool_1",
                title="도구 실행: notion_retrieve_page",
                task_type="TOOL",
                service="notion",
                tool_name="notion_retrieve_page",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls = {"count": 0}

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="page_id missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "notion_retrieve_page",
                    "slot_task_id": "task_tool_1",
                    "missing_slot": "page_id",
                    "missing_slots": "page_id",
                    "slot_payload_json": "{}",
                },
            )
        task = plan.tasks[0]
        assert task.payload.get("page_id") == "30d50e84a3bf8012abfeea8321ff12ea"
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    first = asyncio.run(run_agent_analysis("notion 페이지에 블록 추가", ["notion"], "user-notion-page-id"))
    assert first.ok is False
    assert get_pending_action("user-notion-page-id") is not None

    second = asyncio.run(run_agent_analysis("30d50e84a3bf8012abfeea8321ff12ea", ["notion"], "user-notion-page-id"))
    assert second.ok is True
    assert second.result_summary == "done"
    assert get_pending_action("user-notion-page-id") is None
    clear_pending_action("user-notion-page-id")


def test_run_agent_analysis_resumes_with_focused_pending_task_only(monkeypatch):
    clear_pending_action("user-focused")
    llm_plan = AgentPlan(
        user_text="linear 이슈 업데이트",
        requirements=[AgentRequirement(summary="Linear 이슈 수정")],
        target_services=["linear", "notion"],
        selected_tools=["linear_update_issue", "notion_create_page"],
        workflow_steps=["1. update", "2. create notion"],
        tasks=[
            AgentTask(
                id="task_linear_update_issue",
                title="Linear 이슈 수정",
                task_type="TOOL",
                service="linear",
                tool_name="linear_update_issue",
                payload={},
                output_schema={"type": "tool_result"},
            ),
            AgentTask(
                id="task_notion_create_page",
                title="Notion 페이지 생성",
                task_type="TOOL",
                service="notion",
                tool_name="notion_create_page",
                payload={"title_hint": "should_not_run"},
                output_schema={"type": "tool_result"},
            ),
        ],
        notes=["planner=llm"],
    )

    class _Settings:
        llm_autonomous_enabled = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls = {"count": 0}

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="issue_id missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_update_issue",
                    "slot_task_id": "task_linear_update_issue",
                    "missing_slot": "issue_id",
                    "missing_slots": "issue_id",
                    "slot_payload_json": "{}",
                },
            )
        if calls["count"] == 2:
            return AgentExecutionResult(
                success=False,
                user_message="description missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_update_issue",
                    "slot_task_id": "task_linear_update_issue",
                    "missing_slot": "description",
                    "missing_slots": "description",
                    "slot_payload_json": '{"issue_id":"OPT-42"}',
                },
            )
        task_tools = [str(task.tool_name or "") for task in plan.tasks if task.task_type == "TOOL"]
        assert task_tools == ["linear_update_issue"]
        assert all(service != "notion" for service in plan.target_services)
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    first = asyncio.run(run_agent_analysis("linear 이슈 업데이트", ["linear", "notion"], "user-focused"))
    assert first.ok is False
    assert get_pending_action("user-focused") is not None

    second = asyncio.run(run_agent_analysis("이슈: OPT-42", ["linear", "notion"], "user-focused"))
    assert second.ok is False
    assert second.execution is not None
    assert second.execution.artifacts.get("missing_slot") == "description"

    third = asyncio.run(
        run_agent_analysis(
            "구글 계정을 통한 간편한 로그인 및 회원가입 기능이 구현되었습니다.",
            ["linear", "notion"],
            "user-focused",
        )
    )
    assert third.ok is True
    assert third.result_summary == "done"
    assert get_pending_action("user-focused") is None
    clear_pending_action("user-focused")


def test_run_agent_analysis_does_not_replace_pending_on_service_action_text(monkeypatch):
    clear_pending_action("user-pending-keep")
    llm_plan = AgentPlan(
        user_text="notion 페이지 본문 업데이트",
        requirements=[AgentRequirement(summary="Notion 페이지 본문 추가")],
        target_services=["notion"],
        selected_tools=["notion_append_block_children"],
        workflow_steps=["1. append"],
        tasks=[
            AgentTask(
                id="task_notion_append",
                title="본문 추가",
                task_type="TOOL",
                service="notion",
                tool_name="notion_append_block_children",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=["planner=llm"],
    )

    class _Settings:
        llm_autonomous_enabled = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls = {"count": 0}

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="block_id missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "notion_append_block_children",
                    "slot_task_id": "task_notion_append",
                    "missing_slot": "block_id",
                    "missing_slots": "block_id",
                    "slot_payload_json": "{}",
                },
            )
        # If pending was not replaced, next successful execution should still be focused append task.
        tool_names = [str(task.tool_name or "") for task in plan.tasks if task.task_type == "TOOL"]
        assert tool_names == ["notion_append_block_children"]
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    first = asyncio.run(run_agent_analysis("notion 페이지 본문 업데이트", ["notion"], "user-pending-keep"))
    assert first.ok is False
    assert get_pending_action("user-pending-keep") is not None

    # Previously this kind of text replaced pending as "new request".
    second = asyncio.run(run_agent_analysis("notion 내용 추가", ["notion"], "user-pending-keep"))
    assert second.ok is False
    assert second.execution is not None
    assert second.execution.artifacts.get("error_code") == "validation_error"
    assert get_pending_action("user-pending-keep") is not None

    third = asyncio.run(run_agent_analysis("30d50e84a3bf8012abfeea8321ff12ea", ["notion"], "user-pending-keep"))
    assert third.ok is True
    assert third.result_summary == "done"
    clear_pending_action("user-pending-keep")


def test_run_agent_analysis_does_not_start_slot_loop_when_disabled(monkeypatch):
    clear_pending_action("user-slot-off")
    llm_plan = AgentPlan(
        user_text="Linear 이슈 생성해줘",
        requirements=[AgentRequirement(summary="Linear 이슈 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1. create"],
        tasks=[
            AgentTask(
                id="task_linear_create_issue",
                title="Linear 이슈 생성",
                task_type="TOOL",
                service="linear",
                tool_name="linear_create_issue",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(
            success=False,
            user_message="title missing",
            summary="validation",
            artifacts={
                "error_code": "validation_error",
                "slot_action": "linear_create_issue",
                "slot_task_id": "task_linear_create_issue",
                "missing_slot": "title",
                "missing_slots": "title",
                "slot_payload_json": "{}",
            },
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-slot-off"))
    assert result.ok is False
    assert get_pending_action("user-slot-off") is None
    assert any(note == "slot_loop_enabled=0" for note in result.plan.notes)


def test_run_agent_analysis_rejects_orphan_slot_only_input(monkeypatch):
    clear_pending_action("user-orphan-slot")

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = True
        slot_loop_rollout_percent = 100

    async def _fake_try_build(**kwargs):
        raise AssertionError("planner should not run for orphan slot-only input")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not run for orphan slot-only input")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("팀: operate", ["linear"], "user-orphan-slot"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("next_action") == "start_new_request"
    assert "보류 작업이 없습니다" in result.execution.user_message


def test_run_agent_analysis_rejects_orphan_slot_only_input_when_slot_loop_disabled(monkeypatch):
    clear_pending_action("user-orphan-slot-off")

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False

    async def _fake_try_build(**kwargs):
        raise AssertionError("planner should not run for orphan slot-only input")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not run for orphan slot-only input")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("본문: 테스트 내용", ["linear", "notion"], "user-orphan-slot-off"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("next_action") == "start_new_request"
    assert "보류 작업이 없습니다" in result.execution.user_message


def test_plan_consistency_reason_requires_update_tool_for_update_intent():
    reason = _plan_consistency_reason("notion 페이지 업데이트", ["notion_search"])
    assert reason == "missing_update_tool"


def test_plan_consistency_reason_blocks_internal_oauth_tool():
    reason = _plan_consistency_reason("linear 이슈 업데이트", ["notion_oauth_token_exchange"])
    assert reason == "internal_oauth_tool_leak"


def test_run_agent_analysis_returns_persistence_error_when_pending_store_fails(monkeypatch):
    clear_pending_action("user-persist-fail")
    llm_plan = AgentPlan(
        user_text="Linear 이슈 생성해줘",
        requirements=[AgentRequirement(summary="Linear 이슈 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1. create"],
        tasks=[
            AgentTask(
                id="task_linear_create_issue",
                title="Linear 이슈 생성",
                task_type="TOOL",
                service="linear",
                tool_name="linear_create_issue",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(
            success=False,
            user_message="title missing",
            summary="validation",
            artifacts={
                "error_code": "validation_error",
                "slot_action": "linear_create_issue",
                "slot_task_id": "task_linear_create_issue",
                "missing_slot": "title",
                "missing_slots": "title",
                "slot_payload_json": "{}",
            },
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr(
        "agent.loop.set_pending_action",
        lambda **kwargs: (_ for _ in ()).throw(PendingActionStorageError("pending_action_persistence_failed")),
    )

    result = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-persist-fail"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "pending_action_persistence_error"
    assert "안전하게 저장하지 못해" in result.execution.user_message


def test_run_agent_analysis_resumes_pending_even_when_slot_loop_disabled(monkeypatch):
    clear_pending_action("user-slot-off-resume")
    llm_plan = AgentPlan(
        user_text="Linear 이슈 생성해줘",
        requirements=[AgentRequirement(summary="Linear 이슈 생성")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1. create"],
        tasks=[
            AgentTask(
                id="task_linear_create_issue",
                title="Linear 이슈 생성",
                task_type="TOOL",
                service="linear",
                tool_name="linear_create_issue",
                payload={},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    calls = {"count": 0}
    pending_store: dict[str, object] = {}

    class _SettingsOn:
        llm_autonomous_enabled = False
        slot_loop_enabled = True
        slot_loop_rollout_percent = 100

    class _SettingsOff:
        llm_autonomous_enabled = False
        slot_loop_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="title missing",
                summary="validation",
                artifacts={
                    "error_code": "validation_error",
                    "slot_action": "linear_create_issue",
                    "slot_task_id": "task_linear_create_issue",
                    "missing_slot": "title",
                    "missing_slots": "title",
                    "slot_payload_json": "{}",
                },
            )
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.set_pending_action", lambda **kwargs: pending_store.__setitem__(kwargs["user_id"], kwargs))
    monkeypatch.setattr("agent.loop.get_pending_action", lambda user_id: None)
    monkeypatch.setattr("agent.loop.clear_pending_action", lambda user_id: pending_store.pop(user_id, None))

    class _PendingObj:
        def __init__(self, payload):
            self.user_id = payload["user_id"]
            self.intent = payload["intent"]
            self.action = payload["action"]
            self.task_id = payload["task_id"]
            self.plan = payload["plan"]
            self.plan_source = payload["plan_source"]
            self.collected_slots = dict(payload["collected_slots"])
            self.missing_slots = list(payload["missing_slots"])

    monkeypatch.setattr("agent.loop.get_settings", lambda: _SettingsOn())
    monkeypatch.setattr("agent.loop.get_pending_action", lambda user_id: (_PendingObj(pending_store[user_id]) if user_id in pending_store else None))
    first = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-slot-off-resume"))
    assert first.ok is False
    assert "user-slot-off-resume" in pending_store

    monkeypatch.setattr("agent.loop.get_settings", lambda: _SettingsOff())
    second = asyncio.run(run_agent_analysis('제목: "로그인 오류"', ["linear"], "user-slot-off-resume"))
    assert second.ok is True
    assert second.result_summary == "done"
    assert "user-slot-off-resume" not in pending_store
    clear_pending_action("user-slot-off-resume")


def test_run_agent_analysis_skips_regex_prescreen_when_llm_planner_enabled(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = False
        llm_planner_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 데이터소스 invalid-id 조회해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "done"


def test_run_agent_analysis_uses_llm_plan(monkeypatch):
    llm_plan = _sample_plan()
    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "llm"


def test_run_agent_analysis_prefers_v2_router_when_enabled(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        llm_response_finalizer_enabled = False

    async def _fake_v2(**kwargs):
        plan = AgentPlan(
            user_text=kwargs["user_text"],
            requirements=[AgentRequirement(summary="v2")],
            target_services=[],
            selected_tools=[],
            workflow_steps=["1"],
            notes=[],
        )
        execution = AgentExecutionResult(success=True, user_message="v2-ok", summary="v2-done")
        return AgentRunResult(
            ok=True,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    async def _fake_try_build(**kwargs):
        raise AssertionError("legacy planner should not run when v2 router is enabled")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)

    result = asyncio.run(run_agent_analysis("오늘 서울 날씨 알려줘", ["notion"], "user-v2"))
    assert result.ok is True
    assert result.plan_source == "router_v2"
    assert result.execution is not None
    assert result.execution.user_message == "v2-ok"


def test_run_agent_analysis_runs_v2_in_shadow_mode_but_returns_legacy(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        skill_v2_shadow_mode = True
        skill_v2_traffic_percent = 100
        llm_response_finalizer_enabled = False

    v2_calls = {"count": 0}

    async def _fake_v2(**kwargs):
        v2_calls["count"] += 1
        plan = AgentPlan(
            user_text=kwargs["user_text"],
            requirements=[AgentRequirement(summary="v2")],
            target_services=[],
            selected_tools=[],
            workflow_steps=["1"],
            notes=[],
        )
        execution = AgentExecutionResult(success=True, user_message="v2-ok", summary="v2-done")
        return AgentRunResult(
            ok=True,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    llm_plan = _sample_plan()

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="legacy-ok", summary="legacy-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("오늘 서울 날씨 알려줘", ["notion"], "user-shadow"))
    assert result.ok is True
    assert result.plan_source == "llm"
    assert result.execution is not None
    assert result.execution.user_message == "legacy-ok"
    assert v2_calls["count"] == 1
    assert any(note == "skill_v2_shadow_mode=1" for note in result.plan.notes)
    assert any(note == "skill_v2_shadow_executed=1" for note in result.plan.notes)


def test_run_agent_analysis_skips_v2_when_rollout_miss(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        skill_v2_shadow_mode = False
        skill_v2_traffic_percent = 0
        llm_response_finalizer_enabled = False

    async def _fake_v2(**kwargs):
        raise AssertionError("v2 should not run when rollout misses")

    llm_plan = _sample_plan()

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="legacy-ok", summary="legacy-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("오늘 서울 날씨 알려줘", ["notion"], "user-rollout-miss"))
    assert result.ok is True
    assert result.plan_source == "llm"
    assert result.execution is not None
    assert result.execution.user_message == "legacy-ok"
    assert any(note == "skill_v2_rollout=rollout_0_miss" for note in result.plan.notes)


def test_run_agent_analysis_falls_back_to_rule(monkeypatch):
    rule_plan = _sample_plan()
    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return None, "llm_planner_disabled"

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)
    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(item.startswith("llm_planner_fallback:") for item in result.plan.notes)


def test_run_agent_analysis_applies_response_finalizer_template(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = False
        llm_response_finalizer_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(
            success=True,
            user_message="기본 응답",
            summary="done",
            steps=[
                AgentExecutionStep(name="turn_1_tool:notion_search", status="success", detail="ok"),
                AgentExecutionStep(name="turn_1_verify", status="success", detail="completion_verified"),
            ],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.execution is not None
    assert "[근거]" in result.execution.user_message
    assert any(item == "response_finalizer=template" for item in result.plan.notes)


def test_run_agent_analysis_prefers_autonomous_when_enabled(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(
            success=True,
            user_message="auto-ok",
            summary="auto-done",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when autonomous succeeds")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "auto-done"
    assert any(item == "execution=autonomous" for item in result.plan.notes)


def test_run_agent_analysis_uses_deterministic_first_when_enabled(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_hybrid_executor_first = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        raise AssertionError("autonomous should not be called in deterministic-first mode")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="det-ok", summary="det-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "det-done"
    assert any(item == "execution=deterministic_first" for item in result.plan.notes)


def test_run_agent_analysis_prefers_autonomous_even_with_rule_plan(monkeypatch):
    rule_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return None, "llm_planner_disabled"

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(
            success=True,
            user_message="auto-ok",
            summary="auto-done",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when autonomous succeeds")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert result.result_summary == "auto-done"
    assert any(item == "execution=autonomous" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_fallback_to_executor(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "done"
    assert any(item == "execution=autonomous_fallback" for item in result.plan.notes)
    assert any(item == "autonomous_error=turn_limit" for item in result.plan.notes)


def test_run_agent_analysis_handles_autonomous_runtime_exception(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        raise httpx.ReadTimeout("upstream timeout")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "done"
    assert any(item == "execution=autonomous_fallback" for item in result.plan.notes)
    assert any(item == "autonomous_error=autonomous_runtime_error" for item in result.plan.notes)
    assert any(item == "autonomous_exception=ReadTimeout" for item in result.plan.notes)


def test_run_agent_analysis_can_disable_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when rule fallback is disabled")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is False
    assert result.result_summary == "auto-fail"
    assert any(item == "execution=autonomous_no_rule_fallback" for item in result.plan.notes)


def test_run_agent_analysis_blocks_rule_fallback_for_mutation_intent(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "verification_failed"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called for mutation intent when blocked")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 페이지 생성해줘 주간 회의록", ["notion"], "user-1"))
    assert result.ok is False
    assert any(item == "execution=autonomous_no_rule_fallback_mutation" for item in result.plan.notes)


def test_run_agent_analysis_allows_rule_fallback_for_lookup_intent(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert any(item == "execution=autonomous_fallback" for item in result.plan.notes)


def test_run_agent_analysis_progress_guard_blocks_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = True
        llm_autonomous_progressive_no_fallback_enabled = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-partial-fail",
            summary="auto-partial-fail",
            artifacts={"error_code": "verification_failed"},
            steps=[
                AgentExecutionStep(
                    name="turn_1_tool:notion_search",
                    status="success",
                    detail="ok",
                )
            ],
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when progress guard is enabled")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is False
    assert any(note.startswith("execution=autonomous_progress_guard:verification_failed:1") for note in result.plan.notes)


def test_run_agent_analysis_progress_guard_disabled_allows_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = True
        llm_autonomous_progressive_no_fallback_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-partial-fail",
            summary="auto-partial-fail",
            artifacts={"error_code": "verification_failed"},
            steps=[
                AgentExecutionStep(
                    name="turn_1_tool:notion_search",
                    status="success",
                    detail="ok",
                )
            ],
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert any(item == "execution=autonomous_fallback" for item in result.plan.notes)


def test_run_agent_analysis_validates_data_source_id_early(monkeypatch):
    called = {"llm": False, "exec": False}

    class _Settings:
        llm_autonomous_enabled = False
        llm_planner_enabled = False

    async def _fake_try_build(**kwargs):
        called["llm"] = True
        raise AssertionError("llm planner should not be called for invalid data source id")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        called["exec"] = True
        raise AssertionError("executor should not be called for invalid data source id")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 데이터소스 invalid-id 조회해줘", ["notion"], "user-1"))
    assert result.ok is False
    assert result.stage == "validation"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "validation_error"
    assert "형식이 올바르지" in result.execution.user_message
    assert called == {"llm": False, "exec": False}


def test_run_agent_analysis_autonomous_strict_no_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = True
        llm_autonomous_limit_retry_once = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called in strict mode")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is False
    assert result.result_summary == "auto-fail"
    assert any(item == "execution=autonomous_strict" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_retry_then_success(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_max_turns = 6
        llm_autonomous_max_tool_calls = 8
        llm_autonomous_timeout_sec = 45
        llm_autonomous_replan_limit = 1
        llm_autonomous_guardrail_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="limit",
                summary="limit",
                artifacts={"error_code": "turn_limit"},
            )
        assert kwargs.get("max_turns_override") == 8
        assert kwargs.get("max_tool_calls_override") == 12
        assert kwargs.get("timeout_sec_override") == 60
        assert kwargs.get("replan_limit_override") == 2
        assert kwargs.get("max_candidates_override") == 20
        assert isinstance(kwargs.get("extra_guidance"), str)
        assert "turn 한도" in kwargs.get("extra_guidance")
        return AgentExecutionResult(
            success=True,
            user_message="auto-retry-ok",
            summary="auto-retry-ok",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called after retry success")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "auto-retry-ok"
    assert calls["count"] == 2
    assert any(item == "autonomous_retry=1" for item in result.plan.notes)
    assert any(item == "execution=autonomous_retry" for item in result.plan.notes)
    assert any(item.startswith("autonomous_retry_budget=") for item in result.plan.notes)
    assert any(item == "autonomous_retry_tuning_rule=error:turn_limit" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_retry_includes_last_tool_error_guidance(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_max_turns = 6
        llm_autonomous_max_tool_calls = 8
        llm_autonomous_timeout_sec = 45
        llm_autonomous_replan_limit = 1
        llm_autonomous_guardrail_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="failed",
                summary="failed",
                artifacts={"error_code": "tool_call_limit"},
                steps=[
                    AgentExecutionStep(
                        name="turn_2_tool:notion_append_block_children",
                        status="error",
                        detail="notion_append_block_children:BAD_REQUEST",
                    )
                ],
            )
        guidance = str(kwargs.get("extra_guidance", ""))
        assert ("도구 호출 한도" in guidance) or ("tool 호출 한도" in guidance)
        assert "직전 도구 오류:" in guidance
        assert "notion_append_block_children" in guidance
        return AgentExecutionResult(
            success=True,
            user_message="ok",
            summary="ok",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called after retry success")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert calls["count"] == 2


def test_run_agent_analysis_guardrail_degrades_before_retry(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = True
        llm_autonomous_progressive_no_fallback_enabled = False
        llm_autonomous_guardrail_enabled = True
        llm_autonomous_guardrail_tool_error_rate_threshold = 0.5
        llm_autonomous_guardrail_replan_ratio_threshold = 1.0
        llm_autonomous_guardrail_cross_service_block_threshold = 99

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        return AgentExecutionResult(
            success=False,
            user_message="auto-fail",
            summary="auto-fail",
            artifacts={"error_code": "turn_limit"},
            steps=[
                AgentExecutionStep(name="turn_1_action", status="success", detail="tool_call"),
                AgentExecutionStep(name="turn_1_tool:notion_search", status="error", detail="notion_search:TOOL_FAILED"),
            ],
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert any(note.startswith("autonomous_guardrail_degrade:tool_error_rate") for note in plan.notes)
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert calls["count"] == 1
    assert any(note.startswith("autonomous_metrics=") for note in result.plan.notes)
    assert any(note.startswith("autonomous_guardrail_degrade:tool_error_rate") for note in result.plan.notes)
    assert any(note == "execution=autonomous_fallback" for note in result.plan.notes)


def test_run_agent_analysis_retries_on_verification_failed(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_max_turns = 6
        llm_autonomous_max_tool_calls = 8
        llm_autonomous_timeout_sec = 45
        llm_autonomous_replan_limit = 1
        llm_autonomous_guardrail_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="verify-fail",
                summary="verify-fail",
                artifacts={"error_code": "verification_failed", "verification_reason": "append_requires_append_block_children"},
            )
        guidance = str(kwargs.get("extra_guidance", ""))
        assert "검증 실패 사유" in guidance
        assert "append_block_children" in guidance
        return AgentExecutionResult(
            success=True,
            user_message="retry-ok",
            summary="retry-ok",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called after retry success")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "retry-ok"
    assert calls["count"] == 2
    assert any(
        item == "autonomous_retry_tuning_rule=verification:append_requires_append_block_children"
        for item in result.plan.notes
    )


def test_run_agent_analysis_retry_overrides_expand_for_mutation(monkeypatch):
    llm_plan = _sample_plan()
    calls = {"count": 0}

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = True
        llm_autonomous_max_turns = 6
        llm_autonomous_max_tool_calls = 8
        llm_autonomous_timeout_sec = 45
        llm_autonomous_replan_limit = 1
        llm_autonomous_guardrail_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="limit",
                summary="limit",
                artifacts={"error_code": "turn_limit"},
            )
        assert kwargs.get("max_turns_override") == 9
        assert kwargs.get("max_tool_calls_override") == 14
        assert kwargs.get("timeout_sec_override") == 60
        assert kwargs.get("replan_limit_override") == 2
        assert kwargs.get("max_candidates_override") == 24
        return AgentExecutionResult(
            success=True,
            user_message="auto-retry-ok",
            summary="auto-retry-ok",
            artifacts={"autonomous": "true"},
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called after retry success")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 페이지 생성해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "auto-retry-ok"
    assert calls["count"] == 2


def test_run_agent_analysis_enriches_bad_llm_plan_before_rule_fallback(monkeypatch):
    # Delete intent인데 llm plan이 delete/update tool을 빠뜨린 경우 registry 기반 보강 후 LLM plan 유지
    bad_llm_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search"],  # intentionally incomplete
        workflow_steps=["1. 검색", "2. 삭제"],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return bad_llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert "notion_update_page" in plan.selected_tools
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    class _Tool:
        def __init__(self, name: str):
            self.tool_name = name

    class _Registry:
        def list_tools(self, service: str):
            if service == "notion":
                return [_Tool("notion_search"), _Tool("notion_update_page")]
            return []

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("일일 회의록 페이지 삭제해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "llm"
    assert any(item == "plan_enriched_from_llm" for item in result.plan.notes)


def test_run_agent_analysis_realigns_to_rule_when_enrichment_still_fails(monkeypatch):
    bad_llm_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=["1. 검색", "2. 삭제"],
        notes=[],
    )
    rule_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search", "notion_update_page"],
        workflow_steps=["1. 검색", "2. 아카이브"],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return bad_llm_plan, None

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.load_registry", lambda: (_ for _ in ()).throw(RuntimeError("registry unavailable")))
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("일일 회의록 페이지 삭제해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(item.startswith("plan_realign_from_llm:") for item in result.plan.notes)


def test_run_agent_analysis_no_rule_fallback_when_llm_plan_missing(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        llm_planner_enabled = True
        llm_planner_rule_fallback_enabled = False

    async def _fake_try_build(**kwargs):
        return None, "llm_unavailable"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called when planner fallback is disabled")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션에서 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is False
    assert result.stage == "planning"
    assert result.plan_source == "llm"
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "llm_planner_failed"
    assert any(note.startswith("llm_planner_failed_no_rule_fallback:") for note in result.plan.notes)


def test_run_agent_analysis_skip_realign_when_rule_fallback_disabled(monkeypatch):
    bad_llm_plan = AgentPlan(
        user_text="일일 회의록 페이지 삭제해줘",
        requirements=[AgentRequirement(summary="페이지 삭제")],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=["1. 검색", "2. 삭제"],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False
        llm_planner_enabled = True
        llm_planner_rule_fallback_enabled = False

    async def _fake_try_build(**kwargs):
        return bad_llm_plan, None

    class _Tool:
        def __init__(self, name: str):
            self.tool_name = name

    class _Registry:
        def list_tools(self, service: str):
            # no delete/update tools -> still inconsistent after enrich
            return [_Tool("notion_search")]

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is bad_llm_plan
        assert any(note.startswith("plan_realign_skipped:") for note in plan.notes)
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.load_registry", lambda: _Registry())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("일일 회의록 페이지 삭제해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "llm"


def test_run_agent_analysis_aligns_selected_tools_to_tasks(monkeypatch):
    llm_plan = AgentPlan(
        user_text="linear에서 BM 기획 이슈를 찾아줘",
        requirements=[AgentRequirement(summary="BM 기획 이슈 조회")],
        target_services=["linear"],
        selected_tools=["linear_search_issues", "notion_retrieve_block_children", "notion_retrieve_page"],
        workflow_steps=["1. 검색"],
        tasks=[
            AgentTask(
                id="task_linear_issues",
                title="Linear 이슈 조회",
                task_type="TOOL",
                service="linear",
                tool_name="linear_search_issues",
                output_schema={"type": "tool_result", "service": "linear", "tool": "linear_search_issues"},
            ),
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan.selected_tools == ["linear_search_issues"]
        assert any(note == "plan_tools_aligned_to_tasks" for note in plan.notes)
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis(llm_plan.user_text, ["linear", "notion"], "user-1"))
    assert result.ok is True


def test_run_agent_analysis_rejects_invalid_plan_contract(monkeypatch):
    llm_plan = AgentPlan(
        user_text="linear 이슈 업데이트",
        requirements=[AgentRequirement(summary="Linear 이슈 수정")],
        target_services=["linear"],
        selected_tools=["linear_update_issue"],
        workflow_steps=["1. update"],
        tasks=[
            AgentTask(
                id="task_linear_update_issue",
                title="Linear 이슈 수정",
                task_type="TOOL",
                service="linear",
                tool_name="linear_update_issue",
                payload={},
                output_schema={},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("invalid plan should be blocked before execution")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("linear 이슈 업데이트", ["linear"], "user-1"))
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "plan_contract_invalid"
    assert result.execution.artifacts.get("contract_reason") == "missing_output_schema:task_linear_update_issue"
    assert result.plan_source == "llm"


def test_run_agent_analysis_realigns_cross_service_tool_leak(monkeypatch):
    bad_llm_plan = AgentPlan(
        user_text="linear에서 BM 기획 이슈의 내용을 200자로 요약해서 본문에 추가해줘",
        requirements=[AgentRequirement(summary="대상 콘텐츠 요약")],
        target_services=["linear", "notion"],
        selected_tools=["linear_search_issues", "notion_retrieve_block_children"],
        workflow_steps=["1. 검색", "2. 요약"],
        notes=[],
    )
    rule_plan = AgentPlan(
        user_text=bad_llm_plan.user_text,
        requirements=[AgentRequirement(summary="대상 콘텐츠 요약")],
        target_services=["linear"],
        selected_tools=["linear_search_issues"],
        workflow_steps=["1. 검색", "2. 요약"],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False

    async def _fake_try_build(**kwargs):
        return bad_llm_plan, None

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        assert "linear" in user_text.lower()
        return rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is rule_plan
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis(bad_llm_plan.user_text, ["linear", "notion"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"
    assert any(item.startswith("plan_realign_from_llm:cross_service_tool_leak_notion") for item in result.plan.notes)
