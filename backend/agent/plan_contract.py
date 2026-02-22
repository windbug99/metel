from __future__ import annotations

from agent.types import AgentPlan


def validate_plan_contract(plan: AgentPlan) -> tuple[bool, str | None]:
    target_services = [str(item or "").strip().lower() for item in (plan.target_services or []) if str(item or "").strip()]
    if not target_services:
        return False, "missing_target_services"

    tasks = plan.tasks or []
    if not tasks:
        for tool_name in plan.selected_tools or []:
            lowered = str(tool_name or "").strip().lower()
            if ("oauth" in lowered) or ("token_exchange" in lowered):
                return False, f"internal_tool_selected:{tool_name}"
        return True, None

    task_ids = [str(task.id or "").strip() for task in tasks]
    if any(not task_id for task_id in task_ids):
        return False, "missing_task_id"
    if len(task_ids) != len(set(task_ids)):
        return False, "duplicate_task_id"
    task_id_set = set(task_ids)

    has_tool_task = False
    for task in tasks:
        task_type = str(task.task_type or "").strip().upper()
        if task_type not in {"TOOL", "LLM"}:
            return False, f"invalid_task_type:{task.id}"

        if task_type == "TOOL":
            has_tool_task = True
            service = str(task.service or "").strip().lower()
            tool_name = str(task.tool_name or "").strip()
            if not service:
                return False, f"missing_task_service:{task.id}"
            if service not in target_services:
                return False, f"task_service_not_in_target:{task.id}:{service}"
            if not tool_name:
                return False, f"missing_task_tool_name:{task.id}"
            if not tool_name.startswith(f"{service}_"):
                return False, f"tool_service_mismatch:{task.id}:{tool_name}"
            lowered = tool_name.lower()
            if ("oauth" in lowered) or ("token_exchange" in lowered):
                return False, f"internal_tool_selected:{task.id}:{tool_name}"

        if task_type == "LLM":
            instruction = str(task.instruction or "").strip()
            if not instruction:
                return False, f"missing_llm_instruction:{task.id}"

        output_schema = task.output_schema or {}
        if not isinstance(output_schema, dict) or not output_schema:
            return False, f"missing_output_schema:{task.id}"

        for dep in task.depends_on or []:
            dep_id = str(dep or "").strip()
            if dep_id and dep_id not in task_id_set:
                return False, f"depends_on_not_found:{task.id}:{dep_id}"

    if not has_tool_task:
        return False, "missing_tool_task"

    return True, None
