from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentRequirement:
    summary: str
    quantity: int | None = None
    constraints: list[str] = field(default_factory=list)


@dataclass
class AgentPlan:
    user_text: str
    requirements: list[AgentRequirement]
    target_services: list[str]
    selected_tools: list[str]
    workflow_steps: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class AgentExecutionStep:
    name: str
    status: str
    detail: str


@dataclass
class AgentExecutionResult:
    success: bool
    user_message: str
    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    steps: list[AgentExecutionStep] = field(default_factory=list)


@dataclass
class AgentRunResult:
    ok: bool
    stage: str
    plan: AgentPlan
    result_summary: str
    execution: AgentExecutionResult | None = None
