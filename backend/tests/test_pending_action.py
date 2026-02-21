from agent.pending_action import clear_pending_action
from agent.pending_action import get_pending_action
from agent.pending_action import set_pending_action
from agent.types import AgentPlan
from agent.types import AgentRequirement


def _plan() -> AgentPlan:
    return AgentPlan(
        user_text="Linear 이슈 생성",
        requirements=[AgentRequirement(summary="issue create")],
        target_services=["linear"],
        selected_tools=["linear_create_issue"],
        workflow_steps=["1"],
        notes=[],
    )


def test_pending_action_memory_mode_roundtrip(monkeypatch):
    monkeypatch.setattr("agent.pending_action._storage_mode", lambda: "memory")
    clear_pending_action("user-memory")

    set_pending_action(
        user_id="user-memory",
        intent="create",
        action="linear_create_issue",
        task_id="task1",
        plan=_plan(),
        plan_source="llm",
        collected_slots={"title": "로그인 오류 수정"},
        missing_slots=["team_id"],
        ttl_seconds=300,
    )

    item = get_pending_action("user-memory")
    assert item is not None
    assert item.action == "linear_create_issue"
    assert item.collected_slots.get("title") == "로그인 오류 수정"
    clear_pending_action("user-memory")
    assert get_pending_action("user-memory") is None


def test_pending_action_auto_mode_falls_back_to_memory_when_db_fails(monkeypatch):
    monkeypatch.setattr("agent.pending_action._storage_mode", lambda: "auto")
    monkeypatch.setattr("agent.pending_action._db_upsert_pending_action", lambda item: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr("agent.pending_action._db_get_pending_action", lambda user_id: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr("agent.pending_action._db_update_status", lambda user_id, status: (_ for _ in ()).throw(RuntimeError("db down")))
    clear_pending_action("user-fallback")

    set_pending_action(
        user_id="user-fallback",
        intent="update",
        action="linear_update_issue",
        task_id="task2",
        plan=_plan(),
        plan_source="rule",
        collected_slots={"issue_id": "OPT-36"},
        missing_slots=["description"],
        ttl_seconds=300,
    )

    item = get_pending_action("user-fallback")
    assert item is not None
    assert item.action == "linear_update_issue"
    assert item.missing_slots == ["description"]
    clear_pending_action("user-fallback")
