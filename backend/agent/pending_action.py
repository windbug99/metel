from __future__ import annotations

import logging
import time
from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any

from agent.types import AgentPlan
from agent.types import AgentRequirement
from agent.types import AgentTask
from app.core.config import get_settings

try:
    from supabase import create_client
except Exception:  # pragma: no cover - import error is handled by memory fallback
    create_client = None  # type: ignore[assignment]


logger = logging.getLogger("metel-backend.pending_action")


@dataclass
class PendingAction:
    user_id: str
    intent: str
    action: str
    task_id: str
    plan: AgentPlan
    plan_source: str
    collected_slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    expires_at: float = 0.0


_PENDING_ACTIONS: dict[str, PendingAction] = {}


def _storage_mode() -> str:
    try:
        mode = (get_settings().pending_action_storage or "auto").strip().lower()
    except Exception:
        return "memory"
    if mode in {"auto", "db", "memory"}:
        return mode
    return "auto"


def _default_ttl_seconds() -> int:
    try:
        return max(60, int(get_settings().pending_action_ttl_seconds))
    except Exception:
        return 900


def _pending_table_name() -> str:
    try:
        value = (get_settings().pending_action_table or "pending_actions").strip()
    except Exception:
        value = "pending_actions"
    return value or "pending_actions"


def _build_client():
    if create_client is None:
        return None
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _plan_to_dict(plan: AgentPlan) -> dict[str, Any]:
    return {
        "user_text": plan.user_text,
        "requirements": [asdict(item) for item in plan.requirements],
        "target_services": list(plan.target_services),
        "selected_tools": list(plan.selected_tools),
        "workflow_steps": list(plan.workflow_steps),
        "tasks": [asdict(task) for task in plan.tasks],
        "notes": list(plan.notes),
    }


def _plan_from_dict(payload: dict[str, Any]) -> AgentPlan:
    requirements = [
        AgentRequirement(
            summary=str(item.get("summary", "")),
            quantity=item.get("quantity"),
            constraints=list(item.get("constraints") or []),
        )
        for item in (payload.get("requirements") or [])
        if isinstance(item, dict)
    ]
    tasks = [
        AgentTask(
            id=str(item.get("id", "")),
            title=str(item.get("title", "")),
            task_type=str(item.get("task_type", "")),
            depends_on=list(item.get("depends_on") or []),
            service=item.get("service"),
            tool_name=item.get("tool_name"),
            payload=dict(item.get("payload") or {}),
            instruction=item.get("instruction"),
            output_schema=dict(item.get("output_schema") or {}),
        )
        for item in (payload.get("tasks") or [])
        if isinstance(item, dict)
    ]
    return AgentPlan(
        user_text=str(payload.get("user_text", "")),
        requirements=requirements,
        target_services=list(payload.get("target_services") or []),
        selected_tools=list(payload.get("selected_tools") or []),
        workflow_steps=list(payload.get("workflow_steps") or []),
        tasks=tasks,
        notes=list(payload.get("notes") or []),
    )


def _pending_from_row(row: dict[str, Any]) -> PendingAction | None:
    try:
        expires_at = float(row.get("expires_at", 0.0))
    except (TypeError, ValueError):
        expires_at = 0.0
    plan_payload = row.get("plan_json")
    if not isinstance(plan_payload, dict):
        return None
    return PendingAction(
        user_id=str(row.get("user_id", "")),
        intent=str(row.get("intent", "")),
        action=str(row.get("action", "")),
        task_id=str(row.get("task_id", "")),
        plan=_plan_from_dict(plan_payload),
        plan_source=str(row.get("plan_source", "rule")),
        collected_slots=dict(row.get("collected_slots") or {}),
        missing_slots=list(row.get("missing_slots") or []),
        expires_at=expires_at,
    )


def _db_get_pending_action(user_id: str) -> PendingAction | None:
    client = _build_client()
    table = _pending_table_name()
    response = (
        client.table(table)
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None
    item = _pending_from_row(rows[0])
    if not item:
        return None
    if item.expires_at and item.expires_at < time.time():
        _db_update_status(user_id, "expired")
        return None
    return item


def _db_upsert_pending_action(item: PendingAction) -> PendingAction:
    client = _build_client()
    table = _pending_table_name()
    payload = {
        "user_id": item.user_id,
        "intent": item.intent,
        "action": item.action,
        "task_id": item.task_id,
        "plan_json": _plan_to_dict(item.plan),
        "plan_source": item.plan_source,
        "collected_slots": dict(item.collected_slots),
        "missing_slots": list(item.missing_slots),
        "expires_at": item.expires_at,
        "status": "active",
    }
    client.table(table).upsert(payload, on_conflict="user_id").execute()
    return item


def _db_update_status(user_id: str, status: str) -> None:
    client = _build_client()
    table = _pending_table_name()
    client.table(table).update({"status": status}).eq("user_id", user_id).execute()


def _mem_get_pending_action(user_id: str) -> PendingAction | None:
    item = _PENDING_ACTIONS.get(user_id)
    if not item:
        return None
    if item.expires_at and item.expires_at < time.time():
        _PENDING_ACTIONS.pop(user_id, None)
        return None
    return item


def _mem_set_pending_action(
    *,
    user_id: str,
    intent: str,
    action: str,
    task_id: str,
    plan: AgentPlan,
    plan_source: str,
    collected_slots: dict[str, Any],
    missing_slots: list[str],
    ttl_seconds: int = 900,
) -> PendingAction:
    item = PendingAction(
        user_id=user_id,
        intent=intent,
        action=action,
        task_id=task_id,
        plan=plan,
        plan_source=plan_source,
        collected_slots=dict(collected_slots),
        missing_slots=list(missing_slots),
        expires_at=time.time() + max(60, ttl_seconds),
    )
    _PENDING_ACTIONS[user_id] = item
    return item


def _mem_clear_pending_action(user_id: str) -> None:
    _PENDING_ACTIONS.pop(user_id, None)


def get_pending_action(user_id: str) -> PendingAction | None:
    mode = _storage_mode()
    if mode == "memory":
        return _mem_get_pending_action(user_id)
    if mode in {"auto", "db"}:
        try:
            result = _db_get_pending_action(user_id)
            if result or mode == "db":
                return result
        except Exception as exc:
            if mode == "db":
                logger.warning("pending_action db read failed (db mode): %s", exc)
                return None
            logger.warning("pending_action db read failed, fallback to memory: %s", exc)
    return _mem_get_pending_action(user_id)


def set_pending_action(
    *,
    user_id: str,
    intent: str,
    action: str,
    task_id: str,
    plan: AgentPlan,
    plan_source: str,
    collected_slots: dict[str, Any],
    missing_slots: list[str],
    ttl_seconds: int | None = None,
) -> PendingAction:
    item = _mem_set_pending_action(
        user_id=user_id,
        intent=intent,
        action=action,
        task_id=task_id,
        plan=plan,
        plan_source=plan_source,
        collected_slots=collected_slots,
        missing_slots=missing_slots,
        ttl_seconds=ttl_seconds or _default_ttl_seconds(),
    )
    mode = _storage_mode()
    if mode == "memory":
        return item
    if mode in {"auto", "db"}:
        try:
            return _db_upsert_pending_action(item)
        except Exception as exc:
            if mode == "db":
                logger.warning("pending_action db write failed (db mode): %s", exc)
                return item
            logger.warning("pending_action db write failed, fallback to memory: %s", exc)
    return item


def clear_pending_action(user_id: str) -> None:
    _mem_clear_pending_action(user_id)
    mode = _storage_mode()
    if mode == "memory":
        return
    if mode in {"auto", "db"}:
        try:
            _db_update_status(user_id, "completed")
        except Exception as exc:
            if mode == "db":
                logger.warning("pending_action db clear failed (db mode): %s", exc)
            else:
                logger.warning("pending_action db clear failed, fallback to memory: %s", exc)
