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
    tasks: list["AgentTask"] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AgentTask:
    id: str
    title: str
    task_type: str  # TOOL | LLM
    depends_on: list[str] = field(default_factory=list)
    service: str | None = None
    tool_name: str | None = None
    payload: dict = field(default_factory=dict)
    instruction: str | None = None
    output_schema: dict = field(default_factory=dict)


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
    plan_source: str = "rule"
