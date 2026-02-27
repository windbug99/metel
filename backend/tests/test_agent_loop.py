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


def test_run_agent_analysis_calendar_pipeline_uses_dag_template(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-dag"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        return AgentExecutionResult(
            success=True,
            user_message="dag ok",
            summary="DAG 파이프라인 실행 완료",
            artifacts={"router_mode": "PIPELINE_DAG", "pipeline_run_id": "prun_test"},
            steps=[AgentExecutionStep(name="pipeline_dag", status="success", detail="succeeded")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더 오늘 회의를 notion 페이지로 만들고 linear 이슈로 등록해줘",
            ["google", "notion", "linear"],
            "user-dag",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_run_agent_analysis_calendar_pipeline_uses_stepwise_fixture_when_enabled(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        llm_stepwise_pipeline_enabled = True

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-stepwise"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        payload = plan.tasks[0].payload or {}
        assert (payload.get("pipeline") or {}).get("pipeline_id") == "google_calendar_to_notion_linear_stepwise_v1"
        return AgentExecutionResult(
            success=True,
            user_message="stepwise ok",
            summary="stepwise DAG 파이프라인 실행 완료",
            artifacts={"router_mode": "PIPELINE_DAG", "pipeline_run_id": "prun_stepwise"},
            steps=[AgentExecutionStep(name="pipeline_dag", status="success", detail="succeeded")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의 일정만 조회해서 노션에 회의록 서식으로 생성하고 리니어에 이슈 생성하세요",
            ["google", "notion", "linear"],
            "user-stepwise",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_run_agent_analysis_uses_stepwise_template_when_enabled(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        llm_stepwise_pipeline_enabled = True

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_stepwise_plan(user_text: str, connected_services: list[str], user_id: str):
        _ = (user_text, connected_services, user_id)
        return AgentPlan(
            user_text="stepwise",
            requirements=[AgentRequirement(summary="stepwise")],
            target_services=["notion"],
            selected_tools=["notion_search"],
            workflow_steps=["1. 노션 검색"],
            tasks=[
                AgentTask(
                    id="task_stepwise_pipeline_v1",
                    title="stepwise",
                    task_type="STEPWISE_PIPELINE",
                    payload={"tasks": [{"task_id": "step_1", "sentence": "검색", "service": "notion", "tool_name": "notion_search"}]},
                )
            ],
            notes=[],
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-stepwise-template"
        assert plan.tasks and plan.tasks[0].task_type == "STEPWISE_PIPELINE"
        return AgentExecutionResult(
            success=True,
            user_message="stepwise template ok",
            summary="stepwise template done",
            artifacts={"router_mode": "STEPWISE_PIPELINE"},
            steps=[AgentExecutionStep(name="step_1", status="success", detail="executed")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_stepwise_pipeline_plan", _fake_stepwise_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "노션에서 최근 페이지 조회해줘",
            ["notion"],
            "user-stepwise-template",
        )
    )
    assert result.ok is True
    assert result.plan_source == "stepwise_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "STEPWISE_PIPELINE"


def test_run_agent_analysis_calendar_notion_todo_uses_dag_template(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-todo"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        assert plan.tasks[0].title == "calendar->notion(todo) DAG"
        assert plan.selected_tools == ["google_calendar_list_events", "notion_create_page"]
        return AgentExecutionResult(
            success=True,
            user_message="작업결과\n- 생성 완료\n\n링크\n- Notion: https://notion.so/page-1",
            summary="calendar notion todo done",
            artifacts={"router_mode": "PIPELINE_DAG", "pipeline_run_id": "prun_todo"},
            steps=[AgentExecutionStep(name="calendar_notion_todo", status="success", detail="done")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정을 노션에 할일 목록으로 생성하세요",
            ["google", "notion"],
            "user-todo",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_run_agent_analysis_calendar_notion_minutes_uses_dag_template(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-minutes"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        assert plan.tasks[0].title == "calendar->notion(minutes) DAG"
        assert plan.selected_tools == ["google_calendar_list_events", "notion_create_page"]
        return AgentExecutionResult(
            success=True,
            user_message="작업결과\n- 생성 완료\n\n링크\n- Notion: https://notion.so/page-1",
            summary="calendar notion minutes done",
            artifacts={"router_mode": "PIPELINE_DAG", "pipeline_run_id": "prun_minutes"},
            steps=[AgentExecutionStep(name="calendar_notion_minutes", status="success", detail="done")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성하세요",
            ["google", "notion"],
            "user-minutes",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_run_agent_analysis_calendar_notion_minutes_summary_phrase_uses_dag_template(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_traffic_percent = 100
        skill_llm_transform_pipeline_shadow_mode = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-minutes-summary"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        assert plan.tasks[0].title == "calendar->notion(minutes) DAG"
        return AgentExecutionResult(
            success=True,
            user_message="ok",
            summary="ok",
            artifacts={"router_mode": "PIPELINE_DAG"},
            steps=[AgentExecutionStep(name="calendar_notion_minutes", status="success", detail="done")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더 오늘 회의를 노션에 회의 요약 템플릿으로 정리해줘",
            ["google", "notion"],
            "user-minutes-summary",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"


def test_run_agent_analysis_calendar_notion_minutes_flag_off_uses_legacy_path(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-minutes-off"
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="legacy", summary="legacy")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성하세요",
            ["google", "notion"],
            "user-minutes-off",
        )
    )
    assert result.ok is True
    assert result.plan is llm_plan


def test_run_agent_analysis_calendar_notion_minutes_shadow_mode_runs_compiled_and_keeps_legacy(monkeypatch):
    llm_plan = _sample_plan()
    calls: list[str] = []

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_shadow_mode = True
        skill_llm_transform_pipeline_traffic_percent = 0

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-minutes-shadow"
        if plan.tasks and plan.tasks[0].task_type == "PIPELINE_DAG":
            calls.append("compiled_shadow")
            assert plan.tasks[0].title == "calendar->notion(minutes) DAG"
            return AgentExecutionResult(success=True, user_message="shadow", summary="shadow")
        calls.append("legacy")
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="legacy", summary="legacy")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성하세요",
            ["google", "notion"],
            "user-minutes-shadow",
        )
    )
    assert result.ok is True
    assert result.plan is llm_plan
    assert calls == ["compiled_shadow", "legacy"]
    assert "skill_llm_transform_rollout=rollout_0_shadow" in result.plan.notes
    assert "skill_llm_transform_shadow_executed=1" in result.plan.notes


def test_run_agent_analysis_calendar_notion_minutes_allowlist_forces_compiled_serve(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_shadow_mode = False
        skill_llm_transform_pipeline_traffic_percent = 0
        skill_llm_transform_pipeline_allowlist = "user-allow,another-user"

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-allow"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        assert plan.tasks[0].title == "calendar->notion(minutes) DAG"
        return AgentExecutionResult(
            success=True,
            user_message="allowlist serve",
            summary="allowlist serve",
            artifacts={"router_mode": "PIPELINE_DAG"},
            steps=[AgentExecutionStep(name="calendar_notion_minutes", status="success", detail="allowlist")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성하세요",
            ["google", "notion"],
            "user-allow",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.plan is not None
    assert "skill_llm_transform_rollout=allowlist" in result.plan.notes


def test_run_agent_analysis_calendar_linear_minutes_uses_dag_template(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_traffic_percent = 100
        skill_llm_transform_pipeline_shadow_mode = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-linear-minutes"
        assert plan.tasks
        assert plan.tasks[0].task_type == "PIPELINE_DAG"
        assert plan.tasks[0].title == "calendar->linear(minutes) DAG"
        assert plan.selected_tools == ["google_calendar_list_events", "linear_create_issue", "linear_list_teams"]
        return AgentExecutionResult(
            success=True,
            user_message="작업결과\n- 생성 완료\n\n링크\n- Linear: https://linear.app/issue/1",
            summary="calendar linear minutes done",
            artifacts={"router_mode": "PIPELINE_DAG", "pipeline_run_id": "prun_linear_minutes"},
            steps=[AgentExecutionStep(name="calendar_linear_minutes", status="success", detail="done")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
            ["google", "linear"],
            "user-linear-minutes",
        )
    )
    assert result.ok is True
    assert result.plan_source == "dag_template"
    assert result.execution is not None
    assert result.execution.artifacts.get("router_mode") == "PIPELINE_DAG"


def test_run_agent_analysis_calendar_linear_minutes_shadow_mode_runs_compiled_and_keeps_legacy_with_notes(monkeypatch):
    calls: list[str] = []

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_shadow_mode = True
        skill_llm_transform_pipeline_traffic_percent = 0

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-linear-minutes-shadow"
        if plan.tasks and plan.tasks[0].task_type == "PIPELINE_DAG":
            calls.append("compiled_shadow")
            assert plan.tasks[0].title == "calendar->linear(minutes) DAG"
            return AgentExecutionResult(success=True, user_message="shadow", summary="shadow")
        calls.append("legacy")
        assert plan.notes and "plan_source=calendar_linear_template" in plan.notes
        return AgentExecutionResult(success=True, user_message="legacy", summary="legacy")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 리니어에 회의록 서식 이슈 생성",
            ["google", "linear"],
            "user-linear-minutes-shadow",
        )
    )
    assert result.ok is True
    assert calls == ["compiled_shadow", "legacy"]
    assert "skill_llm_transform_rollout=rollout_0_shadow" in result.plan.notes
    assert "skill_llm_transform_shadow_executed=1" in result.plan.notes


def test_run_agent_analysis_location_food_recommendation_requires_map_skill(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_traffic_percent = 100
        skill_llm_transform_pipeline_shadow_mode = False

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fail_execute_agent_plan(user_id: str, plan: AgentPlan):
        _ = (user_id, plan)
        raise AssertionError("execute_agent_plan should not be called when capability guard blocks request")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fail_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 일정 중 식사 일정만 조회해서 약속장소 근처 식당 추천하세요.",
            ["google", "notion"],
            "user-food-no-map",
        )
    )
    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "unsupported_capability"
    assert "지도/장소 검색 연동이 필요합니다." in result.execution.summary
    assert "Naver Map" in result.execution.user_message


def test_run_agent_analysis_skill_llm_compile_miss_reason_is_logged(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = False
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0
        skill_llm_transform_pipeline_enabled = True
        skill_llm_transform_pipeline_shadow_mode = False
        skill_llm_transform_pipeline_traffic_percent = 30

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert user_id == "user-miss-reason"
        return AgentExecutionResult(success=True, user_message="legacy", summary="legacy")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더 조회해줘",
            ["google", "notion"],
            "user-miss-reason",
        )
    )
    assert result.ok is True
    assert any(note.startswith("skill_llm_transform_compile_miss_reason=") for note in result.plan.notes)


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
        llm_planner_rule_fallback_enabled = False
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

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    calls = {"count": 0}
    pending_store: dict[str, object] = {}

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        calls["count"] += 1
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


def test_run_agent_analysis_blocks_execution_on_precheck_blocking_slot(monkeypatch):
    clear_pending_action("user-precheck-block")
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
        llm_autonomous_enabled = True
        slot_loop_enabled = True
        slot_loop_rollout_percent = 100

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        raise AssertionError("autonomous should not run when blocking slot is missing at precheck")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not run when blocking slot is missing at precheck")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("Linear 이슈 생성해줘", ["linear"], "user-precheck-block"))

    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "validation_error"
    assert result.execution.artifacts.get("missing_slot") == "title"
    assert any(item == "slot_policy_blocking_precheck" for item in result.plan.notes)
    assert get_pending_action("user-precheck-block") is not None
    clear_pending_action("user-precheck-block")


def test_run_agent_analysis_allows_non_blocking_precheck_slot(monkeypatch):
    llm_plan = AgentPlan(
        user_text="Linear 최근 이슈 조회",
        requirements=[AgentRequirement(summary="Linear 이슈 조회")],
        target_services=["linear"],
        selected_tools=["linear_search_issues"],
        workflow_steps=["1. search"],
        tasks=[
            AgentTask(
                id="task_linear_search_issues",
                title="Linear 이슈 조회",
                task_type="TOOL",
                service="linear",
                tool_name="linear_search_issues",
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
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("Linear 최근 이슈 조회", ["linear"], "user-precheck-non-block"))

    assert result.ok is True
    assert any(item.startswith("slot_policy_non_blocking_autofill:linear_search_issues") for item in result.plan.notes)


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


def test_run_agent_analysis_replaces_pending_on_service_action_text(monkeypatch):
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

    # New service-action phrase should start a new request instead of consuming pending slots.
    second = asyncio.run(run_agent_analysis("notion 내용 추가", ["notion"], "user-pending-keep"))
    assert second.ok is True
    assert second.result_summary == "done"
    assert get_pending_action("user-pending-keep") is None
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


def test_run_agent_analysis_falls_back_to_legacy_when_v2_realtime_unavailable(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        llm_response_finalizer_enabled = False

    llm_plan = _sample_plan()

    async def _fake_v2(**kwargs):
        plan = AgentPlan(
            user_text=kwargs["user_text"],
            requirements=[AgentRequirement(summary="v2")],
            target_services=["google", "notion", "linear"],
            selected_tools=[],
            workflow_steps=["1"],
            notes=[],
        )
        execution = AgentExecutionResult(
            success=False,
            user_message="실시간 조회 불가.",
            summary="실시간 조회 불가로 외부 서비스 반영 생략",
            artifacts={"error_code": "realtime_data_unavailable"},
        )
        return AgentRunResult(
            ok=False,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        _ = user_id
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="legacy-ok", summary="legacy-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(
        run_agent_analysis(
            "구글캘린더에서 오늘 회의일정 조회해서 각 회의마다 노션에 회의록 초안 생성하고 각 회의를 리니어 이슈로 등록",
            ["google", "notion", "linear"],
            "user-v2-fallback",
        )
    )
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.user_message == "legacy-ok"
    assert result.plan_source == "llm"
    assert "router_v2_fallback=realtime_data_unavailable" in result.plan.notes


def test_run_agent_analysis_falls_back_to_legacy_when_v2_raises(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        llm_response_finalizer_enabled = False

    llm_plan = _sample_plan()

    async def _fake_v2(**kwargs):
        raise RuntimeError("v2_crash")

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        _ = user_id
        assert plan is llm_plan
        return AgentExecutionResult(success=True, user_message="legacy-ok", summary="legacy-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 페이지 하나 요약해줘", ["notion"], "user-v2-error-fallback"))
    assert result.ok is True
    assert result.execution is not None
    assert result.execution.user_message == "legacy-ok"
    assert any(note == "skill_v2_exception=RuntimeError" for note in result.plan.notes)


def test_run_agent_analysis_returns_v2_result_in_shadow_mode(monkeypatch):
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

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)

    result = asyncio.run(run_agent_analysis("오늘 서울 날씨 알려줘", ["notion"], "user-shadow"))
    assert result.ok is True
    assert result.plan_source == "router_v2"
    assert result.execution is not None
    assert result.execution.user_message == "v2-ok"
    assert v2_calls["count"] == 1
    assert any(note == "skill_v2_shadow_mode=1" for note in result.plan.notes)
    assert any(note == "skill_v2_shadow_executed=1" for note in result.plan.notes)


def test_run_agent_analysis_runs_v2_in_shadow_mode_even_when_rollout_zero(monkeypatch):
    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        skill_v2_shadow_mode = True
        skill_v2_traffic_percent = 0
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

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)

    result = asyncio.run(run_agent_analysis("오늘 서울 날씨 알려줘", ["notion"], "user-shadow-zero"))
    assert result.ok is True
    assert result.plan_source == "router_v2"
    assert result.execution is not None
    assert result.execution.user_message == "v2-ok"
    assert v2_calls["count"] == 1
    assert any(note == "skill_v2_rollout=rollout_0_shadow" for note in result.plan.notes)
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


def test_run_agent_analysis_resumes_router_v2_needs_input_with_followup(monkeypatch):
    clear_pending_action("user-v2-needs-input")

    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        skill_v2_shadow_mode = False
        skill_v2_traffic_percent = 100
        llm_response_finalizer_enabled = False
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls: list[str] = []

    async def _fake_v2(**kwargs):
        user_text = kwargs["user_text"]
        calls.append(user_text)
        plan = AgentPlan(
            user_text=user_text,
            requirements=[AgentRequirement(summary="v2")],
            target_services=["notion"],
            selected_tools=["notion_search", "notion_append_block_children"],
            workflow_steps=["1"],
            notes=[],
        )
        if len(calls) == 1:
            execution = AgentExecutionResult(
                success=False,
                user_message="입력값이 더 필요합니다.",
                summary="추가 입력 필요",
                artifacts={"needs_input": "true", "error_code": "validation_error"},
            )
            return AgentRunResult(
                ok=False,
                stage="execution",
                plan=plan,
                result_summary=execution.summary,
                execution=execution,
                plan_source="router_v2",
            )
        execution = AgentExecutionResult(
            success=True,
            user_message="본문 업데이트 완료",
            summary="완료",
            artifacts={},
        )
        return AgentRunResult(
            ok=True,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)

    first = asyncio.run(
        run_agent_analysis(
            '노션에서 "스프린트 보고서" 페이지 업데이트해줘',
            ["notion"],
            "user-v2-needs-input",
        )
    )
    assert first.ok is False
    assert first.execution is not None
    assert first.execution.artifacts.get("needs_input") == "true"
    assert get_pending_action("user-v2-needs-input") is not None

    second = asyncio.run(
        run_agent_analysis(
            '본문에 내용 추가 "우리는 달려간다"',
            ["notion"],
            "user-v2-needs-input",
        )
    )
    assert second.ok is True
    assert second.execution is not None
    assert "본문 업데이트 완료" in second.execution.user_message
    assert len(calls) == 2
    assert '노션에서 "스프린트 보고서" 페이지 업데이트해줘' in calls[1]
    assert '본문에 내용 추가 "우리는 달려간다"' in calls[1]
    assert get_pending_action("user-v2-needs-input") is None


def test_run_agent_analysis_resumes_router_v2_linear_team_followup_without_key(monkeypatch):
    clear_pending_action("user-v2-linear-team")

    class _Settings:
        llm_autonomous_enabled = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        skill_v2_shadow_mode = False
        skill_v2_traffic_percent = 100
        llm_response_finalizer_enabled = False
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    calls: list[str] = []

    async def _fake_v2(**kwargs):
        user_text = kwargs["user_text"]
        calls.append(user_text)
        plan = AgentPlan(
            user_text=user_text,
            requirements=[AgentRequirement(summary="v2")],
            target_services=["linear"],
            selected_tools=["linear_create_issue"],
            workflow_steps=["1"],
            notes=[],
        )
        if len(calls) == 1:
            execution = AgentExecutionResult(
                success=False,
                user_message="입력값이 더 필요합니다.",
                summary="추가 입력 필요",
                artifacts={
                    "needs_input": "true",
                    "error_code": "validation_error",
                    "missing_fields_json": '["team_id"]',
                    "questions_json": '["이슈를 생성할 Linear 팀을 선택해 주세요."]',
                },
            )
            return AgentRunResult(
                ok=False,
                stage="execution",
                plan=plan,
                result_summary=execution.summary,
                execution=execution,
                plan_source="router_v2",
            )
        execution = AgentExecutionResult(
            success=True,
            user_message="이슈 생성 완료",
            summary="완료",
            artifacts={},
        )
        return AgentRunResult(
            ok=True,
            stage="execution",
            plan=plan,
            result_summary=execution.summary,
            execution=execution,
            plan_source="router_v2",
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)

    first = asyncio.run(run_agent_analysis("linear 이슈 생성", ["linear"], "user-v2-linear-team"))
    assert first.ok is False
    assert get_pending_action("user-v2-linear-team") is not None

    second = asyncio.run(run_agent_analysis("operate", ["linear"], "user-v2-linear-team"))
    assert second.ok is True
    assert len(calls) == 2
    assert "linear 이슈 생성" in calls[1]
    assert "팀: operate" in calls[1]
    assert get_pending_action("user-v2-linear-team") is None


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


def test_run_agent_analysis_skips_autonomous_when_rollout_miss(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_traffic_percent = 0

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        raise AssertionError("autonomous should not be called when rollout percent is 0")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="det-ok", summary="det-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-rollout-miss"))
    assert result.ok is True
    assert result.result_summary == "det-done"
    assert any(item == "execution=autonomous_rollout_miss" for item in result.plan.notes)


def test_run_agent_analysis_runs_autonomous_shadow_when_rollout_miss(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_traffic_percent = 0
        llm_autonomous_shadow_mode = True

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    shadow_calls = {"count": 0}

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        shadow_calls["count"] += 1
        return AgentExecutionResult(success=True, user_message="shadow-ok", summary="shadow-done", artifacts={"autonomous": "true"})

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(success=True, user_message="det-ok", summary="det-done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("text", ["notion"], "user-shadow-rollout-miss"))
    assert result.ok is True
    assert result.result_summary == "det-done"
    assert shadow_calls["count"] == 1
    assert any(item == "execution=autonomous_rollout_miss" for item in result.plan.notes)
    assert any(item == "autonomous_shadow_executed=1" for item in result.plan.notes)
    assert any(item == "autonomous_shadow_ok=1" for item in result.plan.notes)


def test_run_agent_analysis_autonomous_clarification_required_starts_slot_loop(monkeypatch):
    clear_pending_action("user-auto-clarify")
    llm_plan = AgentPlan(
        user_text="노션 최근 페이지 조회",
        requirements=[AgentRequirement(summary="조회")],
        target_services=["notion"],
        selected_tools=["notion_search"],
        workflow_steps=["1. search"],
        tasks=[
            AgentTask(
                id="task_notion_search",
                title="검색",
                task_type="TOOL",
                service="notion",
                tool_name="notion_search",
                payload={"query": "metel"},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = True
        slot_loop_enabled = True
        slot_loop_rollout_percent = 100

    class _PendingSettings:
        pending_action_storage = "memory"
        pending_action_ttl_seconds = 900
        pending_action_table = "pending_actions"

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan):
        return AgentExecutionResult(
            success=False,
            user_message="query 값이 필요합니다.",
            summary="clarification",
            artifacts={
                "error_code": "clarification_required",
                "slot_action": "notion_search",
                "slot_task_id": "task_notion_search",
                "missing_slot": "query",
                "missing_slots": "query",
                "slot_payload_json": "{}",
            },
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not run for clarification_required")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.pending_action.get_settings", lambda: _PendingSettings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 조회", ["notion"], "user-auto-clarify"))

    assert result.ok is False
    assert result.execution is not None
    assert result.execution.artifacts.get("error_code") == "clarification_required"
    assert any(item == "execution=autonomous_clarification_required" for item in result.plan.notes)
    assert get_pending_action("user-auto-clarify") is not None
    clear_pending_action("user-auto-clarify")


def test_run_agent_analysis_bypasses_autonomous_for_recent_lookup(monkeypatch):
    forced_plan = AgentPlan(
        user_text="리니어에서 최근 이슈 5개 조회",
        requirements=[AgentRequirement(summary="Linear 이슈 조회", quantity=5)],
        target_services=["linear"],
        selected_tools=["linear_search_issues"],
        workflow_steps=["1. 최근 이슈 조회"],
        tasks=[
            AgentTask(
                id="task_linear_search",
                title="Linear 이슈 조회",
                task_type="TOOL",
                service="linear",
                tool_name="linear_search_issues",
                payload={"query": "최근", "first": 5},
                output_schema={"type": "tool_result"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_traffic_percent = 100
        llm_autonomous_shadow_mode = False
        skill_router_v2_enabled = True
        skill_runner_v2_enabled = True
        slot_loop_enabled = False
        slot_loop_rollout_percent = 0

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        _ = connected_services
        assert user_text == "리니어에서 최근 이슈 5개 조회"
        return forced_plan

    async def _fake_run_autonomous_loop(*args, **kwargs):
        raise AssertionError("autonomous should be bypassed for recent lookup intent")

    async def _fake_v2(*args, **kwargs):
        raise AssertionError("router_v2 should be bypassed for recent lookup intent")

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        _ = user_id
        assert plan.user_text == "리니어에서 최근 이슈 5개 조회"
        return AgentExecutionResult(
            success=True,
            summary="deterministic",
            user_message="최근 이슈\n1. [OPT-1] 로그인 오류\n   링크: https://linear.app/issue/OPT-1",
            artifacts={},
            steps=[AgentExecutionStep(name="task_linear_search", status="success", detail="ok")],
        )

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_run_autonomous_loop)
    monkeypatch.setattr("agent.loop.try_run_v2_orchestration", _fake_v2)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("리니어에서 최근 이슈 5개 조회", ["linear"], "user-recent-bypass"))
    assert result.ok is True
    assert result.plan_source == "rule_recent_lookup"
    assert result.execution is not None
    assert "https://linear.app/issue/OPT-1" in result.execution.user_message
    assert any(note == "autonomous_bypass=recent_lookup_intent" for note in result.plan.notes)


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
        slot_loop_enabled = False
        slot_loop_enabled = False

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


def test_run_agent_analysis_verifier_scope_violation_blocks_rule_fallback(monkeypatch):
    llm_plan = _sample_plan()

    class _Settings:
        llm_autonomous_enabled = True
        llm_autonomous_strict = False
        llm_autonomous_limit_retry_once = False
        llm_autonomous_rule_fallback_enabled = True
        llm_autonomous_rule_fallback_mutation_enabled = True
        llm_autonomous_progressive_no_fallback_enabled = False
        slot_loop_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        return AgentExecutionResult(
            success=False,
            user_message="auto-scope-violation",
            summary="auto-scope-violation",
            artifacts={
                "error_code": "verification_failed",
                "verifier_failed_rule": "target_scope_linear_only_violation",
                "verifier_remediation_type": "scope_violation",
            },
        )

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        raise AssertionError("executor should not be called for verifier scope violation")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.run_autonomous_loop", _fake_autonomous_loop)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is False
    assert any(item == "execution=autonomous_verifier_block:scope_violation" for item in result.plan.notes)


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
        llm_autonomous_guardrail_min_tool_samples = 1
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


def test_run_agent_analysis_retries_on_tool_timeout_code(monkeypatch):
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
        slot_loop_enabled = False

    async def _fake_try_build(**kwargs):
        return llm_plan, None

    async def _fake_autonomous_loop(user_id: str, plan: AgentPlan, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return AgentExecutionResult(
                success=False,
                user_message="tool-timeout",
                summary="tool-timeout",
                artifacts={"error_code": "TOOL_TIMEOUT"},
            )
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

    result = asyncio.run(run_agent_analysis("노션 최근 페이지 3개 조회해줘", ["notion"], "user-1"))
    assert result.ok is True
    assert result.result_summary == "retry-ok"
    assert calls["count"] == 2
    assert any(item == "autonomous_retry_tuning_rule=error:TOOL_TIMEOUT" for item in result.plan.notes)


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
        llm_planner_rule_fallback_enabled = False

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


def test_run_agent_analysis_recovers_invalid_llm_plan_contract_with_rule_fallback(monkeypatch):
    invalid_llm_plan = AgentPlan(
        user_text="openweather API 사용방법을 정리해서 linear OPT-46 설명에 추가해줘",
        requirements=[AgentRequirement(summary="요약")],
        target_services=["linear", "spotify"],
        selected_tools=["linear_search_issues"],
        workflow_steps=["1. summarize"],
        tasks=[
            AgentTask(
                id="task_llm_summary",
                title="요약",
                task_type="LLM",
                instruction="요약",
                output_schema={"type": "text", "sentences": 3},
            )
        ],
        notes=[],
    )
    valid_rule_plan = AgentPlan(
        user_text=invalid_llm_plan.user_text,
        requirements=[AgentRequirement(summary="Linear 이슈 수정")],
        target_services=["linear"],
        selected_tools=["linear_search_issues", "linear_update_issue"],
        workflow_steps=["1. search", "2. update"],
        tasks=[
            AgentTask(
                id="task_linear_search",
                title="Linear 이슈 조회",
                task_type="TOOL",
                service="linear",
                tool_name="linear_search_issues",
                payload={"query": "OPT-46", "first": 5},
                output_schema={"type": "tool_result", "service": "linear", "tool": "linear_search_issues"},
            )
        ],
        notes=[],
    )

    class _Settings:
        llm_autonomous_enabled = False
        llm_planner_rule_fallback_enabled = True

    async def _fake_try_build(**kwargs):
        return invalid_llm_plan, None

    def _fake_build_plan(user_text: str, connected_services: list[str]):
        return valid_rule_plan

    async def _fake_execute_agent_plan(user_id: str, plan: AgentPlan):
        assert plan is valid_rule_plan
        assert any(
            note.startswith("plan_contract_recovered_from_llm:") or note.startswith("plan_realign_from_llm:")
            for note in plan.notes
        )
        return AgentExecutionResult(success=True, user_message="ok", summary="done")

    monkeypatch.setattr("agent.loop.get_settings", lambda: _Settings())
    monkeypatch.setattr("agent.loop.try_build_agent_plan_with_llm", _fake_try_build)
    monkeypatch.setattr("agent.loop.build_agent_plan", _fake_build_plan)
    monkeypatch.setattr("agent.loop.execute_agent_plan", _fake_execute_agent_plan)

    result = asyncio.run(run_agent_analysis(invalid_llm_plan.user_text, ["linear", "spotify"], "user-1"))
    assert result.ok is True
    assert result.plan_source == "rule"


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
