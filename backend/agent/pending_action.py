from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.types import AgentPlan


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


def get_pending_action(user_id: str) -> PendingAction | None:
    item = _PENDING_ACTIONS.get(user_id)
    if not item:
        return None
    if item.expires_at and item.expires_at < time.time():
        _PENDING_ACTIONS.pop(user_id, None)
        return None
    return item


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


def clear_pending_action(user_id: str) -> None:
    _PENDING_ACTIONS.pop(user_id, None)
