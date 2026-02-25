from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent.pipeline_error_codes import PipelineErrorCode, is_retryable_pipeline_error

_SCHEMA_PATH = Path(__file__).resolve().with_name("pipeline_dsl_schema.json")
_REF_PATTERN = re.compile(r"^\$([a-zA-Z0-9_\-]+)\.([a-zA-Z0-9_\-\.\[\]]+)$")
_WHEN_PATTERN = re.compile(r"^\s*(\$(?:[a-zA-Z0-9_\-]+|item|ctx)\.[^\s]+)\s*(==|!=|>=|<=|>|<|in)\s*(.+?)\s*$")


@dataclass
class PipelineExecutionError(Exception):
    code: PipelineErrorCode
    reason: str
    failed_step: str | None = None
    failed_item_ref: str | None = None
    compensation_status: str = "not_required"
    pipeline_run_id: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.reason}"


def load_pipeline_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _parse_literal(raw: str) -> Any:
    text = raw.strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    try:
        return json.loads(text)
    except Exception:
        try:
            if "." in text:
                return float(text)
            return int(text)
        except Exception:
            return text


def _resolve_pipeline_error_code(raw_code: str | None, detail: str | None = None, error: str | None = None) -> PipelineErrorCode:
    raw = str(raw_code or "").strip()
    if raw:
        try:
            return PipelineErrorCode(raw)
        except ValueError:
            pass

    haystack = " ".join([str(raw_code or ""), str(detail or ""), str(error or "")]).strip().lower()
    if any(token in haystack for token in ("auth_required", "tool_auth_error", "auth_error", "unauthorized", "forbidden")):
        return PipelineErrorCode.TOOL_AUTH_ERROR
    if any(token in haystack for token in ("rate_limited", "too_many_requests", "429")):
        return PipelineErrorCode.TOOL_RATE_LIMITED
    if "dsl_ref_not_found" in haystack:
        return PipelineErrorCode.DSL_REF_NOT_FOUND
    return PipelineErrorCode.TOOL_TIMEOUT


def _parse_ref(ref: str) -> tuple[str, str]:
    match = _REF_PATTERN.match((ref or "").strip())
    if not match:
        raise PipelineExecutionError(
            code=PipelineErrorCode.DSL_REF_NOT_FOUND,
            reason=f"invalid_ref_syntax:{ref}",
        )
    return match.group(1), match.group(2)


def _get_path_value(root: Any, path: str) -> Any:
    current: Any = root
    for token in re.findall(r"[a-zA-Z0-9_\-]+|\[\d+\]", path):
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(current, list) or index >= len(current):
                raise KeyError(path)
            current = current[index]
            continue
        if not isinstance(current, dict) or token not in current:
            raise KeyError(path)
        current = current[token]
    return current


def resolve_ref(
    ref: str,
    *,
    artifacts: dict[str, Any],
    item: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> Any:
    source, path = _parse_ref(ref)
    source_map: Any
    if source == "item":
        source_map = item or {}
    elif source == "ctx":
        source_map = ctx or {}
    else:
        source_map = artifacts.get(source)
        if source_map is None:
            raise PipelineExecutionError(
                code=PipelineErrorCode.DSL_REF_NOT_FOUND,
                reason=f"missing_artifact:{source}",
            )
    try:
        return _get_path_value(source_map, path)
    except KeyError:
        raise PipelineExecutionError(
            code=PipelineErrorCode.DSL_REF_NOT_FOUND,
            reason=f"path_not_found:{ref}",
        ) from None


def evaluate_when(
    expression: str | None,
    *,
    artifacts: dict[str, Any],
    item: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> bool:
    if not expression:
        return True
    match = _WHEN_PATTERN.match(expression)
    if not match:
        raise PipelineExecutionError(
            code=PipelineErrorCode.DSL_VALIDATION_FAILED,
            reason=f"invalid_when_expression:{expression}",
        )
    left_ref, operator, raw_right = match.groups()
    left = resolve_ref(left_ref, artifacts=artifacts, item=item, ctx=ctx)
    right = _parse_literal(raw_right)
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "in":
        if not isinstance(right, list):
            raise PipelineExecutionError(
                code=PipelineErrorCode.DSL_VALIDATION_FAILED,
                reason=f"when_in_requires_array:{expression}",
            )
        return left in right
    raise PipelineExecutionError(
        code=PipelineErrorCode.DSL_VALIDATION_FAILED,
        reason=f"unsupported_operator:{operator}",
    )


def _resolve_embedded_refs(
    value: Any,
    *,
    artifacts: dict[str, Any],
    item: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            key: _resolve_embedded_refs(inner, artifacts=artifacts, item=item, ctx=ctx)
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_resolve_embedded_refs(inner, artifacts=artifacts, item=item, ctx=ctx) for inner in value]
    if isinstance(value, str) and value.startswith("$"):
        return resolve_ref(value, artifacts=artifacts, item=item, ctx=ctx)
    return value


def _validate_minimum_output_schema(output: dict[str, Any], output_schema: dict[str, Any]) -> list[str]:
    required = [str(item).strip() for item in (output_schema or {}).get("required", []) if str(item).strip()]
    missing: list[str] = []
    for key in required:
        value = output.get(key)
        if value is None or value == "":
            missing.append(key)
    return missing


def _topological_order(nodes: list[dict[str, Any]]) -> list[str]:
    node_ids = {node["id"] for node in nodes}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for node in nodes:
        node_id = node["id"]
        for parent in node.get("depends_on") or []:
            if parent not in node_ids:
                raise PipelineExecutionError(
                    code=PipelineErrorCode.DSL_VALIDATION_FAILED,
                    reason=f"unknown_dependency:{parent}",
                    failed_step=node_id,
                )
            graph[parent].append(node_id)
            indegree[node_id] += 1
    queue: deque[str] = deque(sorted([node_id for node_id, degree in indegree.items() if degree == 0]))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in graph[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(node_ids):
        raise PipelineExecutionError(
            code=PipelineErrorCode.DSL_VALIDATION_FAILED,
            reason="cycle_detected",
        )
    return order


def _is_write_skill_name(skill_name: str) -> bool:
    lower = (skill_name or "").strip().lower()
    return any(token in lower for token in ("create", "update", "delete", "append", "archive", "move"))


def _mutation_payload_without_idempotency(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != "idempotency_key"}


def _extract_external_ref(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("calendar_event_id", "event_id", "id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return str(item.get("_index") or "")


def _derive_idempotency_key(
    *,
    user_id: str,
    skill_name: str,
    payload: dict[str, Any],
    item: dict[str, Any] | None,
) -> str:
    explicit = str((payload or {}).get("idempotency_key") or "").strip()
    if explicit:
        return explicit
    basis = {
        "user_id": user_id,
        "skill_name": skill_name,
        "external_ref": _extract_external_ref(item),
        "payload": _mutation_payload_without_idempotency(payload),
    }
    try:
        encoded = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    except TypeError:
        encoded = str(basis)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return f"auto:{digest}"


def validate_pipeline_dsl(
    pipeline: dict[str, Any],
    *,
    write_skill_allowlist: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    required = {"pipeline_id", "version", "limits", "nodes"}
    missing_top = sorted(required - set(pipeline.keys()))
    if missing_top:
        return [f"missing_top_level:{field}" for field in missing_top]

    if pipeline.get("version") != "1.0":
        errors.append("invalid_version")
    limits = pipeline.get("limits") or {}
    max_nodes = int(limits.get("max_nodes") or 0)
    nodes = pipeline.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes_required")
        return errors
    if max_nodes < 1 or max_nodes > 6:
        errors.append("limits.max_nodes_out_of_range")
    if len(nodes) > 6:
        errors.append("nodes_exceed_platform_cap")
    if max_nodes and len(nodes) > max_nodes:
        errors.append("nodes_exceed_declared_limit")

    node_ids: list[str] = [str(node.get("id") or "") for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        errors.append("duplicate_node_id")
    id_set = set(node_ids)

    for node in nodes:
        node_id = str(node.get("id") or "")
        node_type = node.get("type")
        if node_type not in {"skill", "llm_transform", "for_each", "verify"}:
            errors.append(f"{node_id}:invalid_node_type")
            continue

        for parent in node.get("depends_on") or []:
            if parent == node_id:
                errors.append(f"{node_id}:self_dependency")
            if parent not in id_set:
                errors.append(f"{node_id}:unknown_dependency:{parent}")

        when_expr = node.get("when")
        if when_expr is not None and not _WHEN_PATTERN.match(str(when_expr)):
            errors.append(f"{node_id}:invalid_when")

        if node_type == "skill":
            name = str(node.get("name") or "")
            if not name:
                errors.append(f"{node_id}:skill_name_required")
            if write_skill_allowlist is not None:
                lowered = name.lower()
                may_write = any(token in lowered for token in ("create", "update", "delete", "append", "archive"))
                if may_write and name not in write_skill_allowlist:
                    errors.append(f"{node_id}:write_skill_not_allowed:{name}")
        elif node_type == "llm_transform":
            if not isinstance(node.get("output_schema"), dict):
                errors.append(f"{node_id}:output_schema_required")
        elif node_type == "for_each":
            source_ref = str(node.get("source_ref") or "")
            if not _REF_PATTERN.match(source_ref):
                errors.append(f"{node_id}:invalid_source_ref")
            item_nodes = node.get("item_node_ids") or []
            if not isinstance(item_nodes, list) or not item_nodes:
                errors.append(f"{node_id}:item_node_ids_required")
            for item_node_id in item_nodes:
                if item_node_id not in id_set:
                    errors.append(f"{node_id}:unknown_item_node:{item_node_id}")
        elif node_type == "verify":
            rules = node.get("rules")
            if not isinstance(rules, list) or not rules:
                errors.append(f"{node_id}:rules_required")
            else:
                for rule in rules:
                    if not _WHEN_PATTERN.match(str(rule)):
                        errors.append(f"{node_id}:invalid_rule:{rule}")

    if errors:
        return errors
    try:
        _topological_order(nodes)
    except PipelineExecutionError as exc:
        errors.append(exc.reason)
    return errors


async def execute_pipeline_dag(
    *,
    user_id: str,
    pipeline: dict[str, Any],
    ctx: dict[str, Any] | None,
    execute_skill: Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]],
    execute_llm_transform: Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]],
    execute_compensation: Callable[[str, str, dict[str, Any], dict[str, Any] | None], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    pipeline_run_id = f"prun_{uuid.uuid4().hex[:16]}"
    errors = validate_pipeline_dsl(pipeline)
    if errors:
        raise PipelineExecutionError(
            code=PipelineErrorCode.DSL_VALIDATION_FAILED,
            reason=";".join(errors),
            pipeline_run_id=pipeline_run_id,
        )

    nodes: list[dict[str, Any]] = pipeline["nodes"]
    node_by_id = {node["id"]: node for node in nodes}
    order = _topological_order(nodes)
    artifacts: dict[str, Any] = {}
    skipped: set[str] = set()
    delegated_to_foreach: set[str] = set()
    successful_writes: dict[str, Any] = {}
    node_runs: list[dict[str, Any]] = []
    compensation_events: list[dict[str, Any]] = []
    idempotent_success_reuse_count = 0
    for node in nodes:
        if node["type"] == "for_each":
            delegated_to_foreach.update(node.get("item_node_ids") or [])

    async def _run_single_node(
        node: dict[str, Any],
        *,
        item: dict[str, Any] | None = None,
        item_artifacts: dict[str, Any] | None = None,
    ) -> Any:
        nonlocal idempotent_success_reuse_count
        scoped_artifacts = dict(artifacts)
        if item_artifacts:
            scoped_artifacts.update(item_artifacts)

        if not evaluate_when(node.get("when"), artifacts=scoped_artifacts, item=item, ctx=ctx):
            return {"status": "skipped", "reason": "when_false"}

        node_input = _resolve_embedded_refs(node.get("input") or {}, artifacts=scoped_artifacts, item=item, ctx=ctx)
        timeout_sec = int(node.get("timeout_sec") or 20)
        retry = node.get("retry") or {"max_attempts": 1, "backoff_ms": 0}
        max_attempts = max(1, int(retry.get("max_attempts") or 1))
        backoff_ms = max(0, int(retry.get("backoff_ms") or 0))

        last_error: PipelineExecutionError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if node["type"] == "skill":
                    skill_name = str(node["name"] or "")
                    write_skill = _is_write_skill_name(skill_name)
                    idempotency_key = ""
                    if write_skill:
                        idempotency_key = _derive_idempotency_key(
                            user_id=user_id,
                            skill_name=skill_name,
                            payload=node_input,
                            item=item,
                        )
                        key = f"{skill_name}::{idempotency_key}"
                        if key in successful_writes:
                            idempotent_success_reuse_count += 1
                            node_runs.append(
                                {
                                    "pipeline_run_id": pipeline_run_id,
                                    "node_id": node["id"],
                                    "node_type": node["type"],
                                    "status": "success",
                                    "attempt": attempt,
                                    "duration_ms": 0,
                                    "idempotency_key": idempotency_key,
                                    "external_ref": _extract_external_ref(item),
                                    "idempotent_reused": True,
                                }
                            )
                            return successful_writes[key]
                    started = time.monotonic()
                    result = await execute_skill(user_id, node["name"], node_input)
                    duration_ms = max(0, int((time.monotonic() - started) * 1000))
                    if not result.get("ok", False):
                        resolved_code = _resolve_pipeline_error_code(
                            str(result.get("error_code") or "").strip(),
                            str(result.get("detail") or "").strip(),
                            str(result.get("error") or "").strip(),
                        )
                        node_runs.append(
                            {
                                "pipeline_run_id": pipeline_run_id,
                                "node_id": node["id"],
                                "node_type": node["type"],
                                "status": "error",
                                "attempt": attempt,
                                "duration_ms": duration_ms,
                                "error_code": resolved_code.value,
                                "idempotency_key": idempotency_key,
                                "external_ref": _extract_external_ref(item),
                            }
                        )
                        raise PipelineExecutionError(
                            code=resolved_code,
                            reason=str(result.get("detail") or result.get("error") or "skill_failed"),
                            failed_step=node["id"],
                            failed_item_ref=str(item.get("id") or "") if item else None,
                            pipeline_run_id=pipeline_run_id,
                        )
                    output = result.get("data", {})
                    node_runs.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "node_id": node["id"],
                            "node_type": node["type"],
                            "status": "success",
                            "attempt": attempt,
                            "duration_ms": duration_ms,
                            "idempotency_key": idempotency_key,
                            "external_ref": _extract_external_ref(item),
                            "idempotent_reused": False,
                        }
                    )
                    if write_skill:
                        key = f"{skill_name}::{idempotency_key}"
                        successful_writes[key] = output
                    return output
                if node["type"] == "llm_transform":
                    started = time.monotonic()
                    transformed = await execute_llm_transform(user_id, node_input, node.get("output_schema") or {})
                    duration_ms = max(0, int((time.monotonic() - started) * 1000))
                    if not isinstance(transformed, dict):
                        node_runs.append(
                            {
                                "pipeline_run_id": pipeline_run_id,
                                "node_id": node["id"],
                                "node_type": node["type"],
                                "status": "error",
                                "attempt": attempt,
                                "duration_ms": duration_ms,
                                "error_code": PipelineErrorCode.LLM_AUTOFILL_FAILED.value,
                                "external_ref": _extract_external_ref(item),
                            }
                        )
                        raise PipelineExecutionError(
                            code=PipelineErrorCode.LLM_AUTOFILL_FAILED,
                            reason="llm_transform_non_object",
                            failed_step=node["id"],
                            failed_item_ref=str(item.get("id") or "") if item else None,
                            pipeline_run_id=pipeline_run_id,
                        )
                    missing = _validate_minimum_output_schema(transformed, node.get("output_schema") or {})
                    if missing:
                        node_runs.append(
                            {
                                "pipeline_run_id": pipeline_run_id,
                                "node_id": node["id"],
                                "node_type": node["type"],
                                "status": "error",
                                "attempt": attempt,
                                "duration_ms": duration_ms,
                                "error_code": PipelineErrorCode.LLM_AUTOFILL_FAILED.value,
                                "external_ref": _extract_external_ref(item),
                            }
                        )
                        raise PipelineExecutionError(
                            code=PipelineErrorCode.LLM_AUTOFILL_FAILED,
                            reason=f"missing_required_slots:{','.join(missing)}",
                            failed_step=node["id"],
                            failed_item_ref=str(item.get("id") or "") if item else None,
                            pipeline_run_id=pipeline_run_id,
                        )
                    node_runs.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "node_id": node["id"],
                            "node_type": node["type"],
                            "status": "success",
                            "attempt": attempt,
                            "duration_ms": duration_ms,
                            "external_ref": _extract_external_ref(item),
                        }
                    )
                    return transformed
                if node["type"] == "verify":
                    started = time.monotonic()
                    rules = node.get("rules") or []
                    all_passed = all(
                        evaluate_when(rule, artifacts=scoped_artifacts, item=item, ctx=ctx)
                        for rule in rules
                    )
                    duration_ms = max(0, int((time.monotonic() - started) * 1000))
                    if not all_passed:
                        node_runs.append(
                            {
                                "pipeline_run_id": pipeline_run_id,
                                "node_id": node["id"],
                                "node_type": node["type"],
                                "status": "error",
                                "attempt": attempt,
                                "duration_ms": duration_ms,
                                "error_code": PipelineErrorCode.VERIFY_COUNT_MISMATCH.value,
                                "external_ref": _extract_external_ref(item),
                            }
                        )
                        raise PipelineExecutionError(
                            code=PipelineErrorCode.VERIFY_COUNT_MISMATCH,
                            reason="verify_rule_failed",
                            failed_step=node["id"],
                            pipeline_run_id=pipeline_run_id,
                        )
                    node_runs.append(
                        {
                            "pipeline_run_id": pipeline_run_id,
                            "node_id": node["id"],
                            "node_type": node["type"],
                            "status": "success",
                            "attempt": attempt,
                            "duration_ms": duration_ms,
                            "external_ref": _extract_external_ref(item),
                        }
                    )
                    return {"pass": True, "reason": "ok"}
                raise PipelineExecutionError(
                    code=PipelineErrorCode.DSL_VALIDATION_FAILED,
                    reason=f"unsupported_node_type:{node['type']}",
                    failed_step=node["id"],
                    pipeline_run_id=pipeline_run_id,
                )
            except PipelineExecutionError as exc:
                last_error = exc
                llm_retryable = node["type"] == "llm_transform" and exc.code == PipelineErrorCode.LLM_AUTOFILL_FAILED
                if attempt >= max_attempts or (not llm_retryable and not is_retryable_pipeline_error(exc.code)):
                    raise
                if backoff_ms:
                    import asyncio

                    await asyncio.sleep(backoff_ms / 1000)
            except Exception as exc:
                last_error = PipelineExecutionError(
                    code=PipelineErrorCode.TOOL_TIMEOUT,
                    reason=f"unhandled_error:{exc}",
                    failed_step=node["id"],
                    failed_item_ref=str(item.get("id") or "") if item else None,
                    pipeline_run_id=pipeline_run_id,
                )
                if attempt >= max_attempts:
                    raise last_error
        if last_error is not None:
            raise last_error
        raise PipelineExecutionError(
            code=PipelineErrorCode.TOOL_TIMEOUT,
            reason="unexpected_execution_exit",
            failed_step=node["id"],
            pipeline_run_id=pipeline_run_id,
        )

    for node_id in order:
        if node_id in skipped:
            continue
        node = node_by_id[node_id]
        if node_id in delegated_to_foreach:
            artifacts[node_id] = {"status": "delegated"}
            continue
        if node["type"] == "for_each":
            source_items = resolve_ref(node["source_ref"], artifacts=artifacts, ctx=ctx or {}, item=None)
            if not isinstance(source_items, list):
                raise PipelineExecutionError(
                    code=PipelineErrorCode.DSL_VALIDATION_FAILED,
                    reason=f"for_each_source_not_array:{node_id}",
                    failed_step=node_id,
                )
            max_fanout = int((pipeline.get("limits") or {}).get("max_fanout") or 50)
            if len(source_items) > max_fanout:
                raise PipelineExecutionError(
                    code=PipelineErrorCode.DSL_VALIDATION_FAILED,
                    reason=f"fanout_exceeds_limit:{len(source_items)}>{max_fanout}",
                    failed_step=node_id,
                )
            item_results: list[dict[str, Any]] = []
            for item_index, raw_item in enumerate(source_items):
                item = raw_item if isinstance(raw_item, dict) else {"value": raw_item}
                item.setdefault("_index", item_index)
                local_outputs: dict[str, Any] = {}
                completed_write_nodes: list[tuple[str, str, dict[str, Any]]] = []
                for item_node_id in node.get("item_node_ids") or []:
                    item_node = copy.deepcopy(node_by_id[item_node_id])
                    item_node["input"] = item_node.get("input") or {}
                    try:
                        result = await _run_single_node(item_node, item=item, item_artifacts=local_outputs)
                        local_outputs[item_node_id] = result
                        if item_node["type"] == "skill" and _is_write_skill_name(str(item_node.get("name") or "")):
                            completed_write_nodes.append((item_node_id, str(item_node.get("name") or ""), result))
                    except PipelineExecutionError as exc:
                        if completed_write_nodes and execute_compensation is not None:
                            compensation_failed = False
                            for written_node_id, written_skill_name, written_output in reversed(completed_write_nodes):
                                ok = await execute_compensation(written_node_id, written_skill_name, written_output, item)
                                compensation_events.append(
                                    {
                                        "pipeline_run_id": pipeline_run_id,
                                        "node_id": written_node_id,
                                        "skill_name": written_skill_name,
                                        "status": "success" if ok else "error",
                                        "external_ref": _extract_external_ref(item),
                                    }
                                )
                                if not ok:
                                    compensation_failed = True
                            exc.compensation_status = "failed" if compensation_failed else "completed"
                            if compensation_failed:
                                raise PipelineExecutionError(
                                    code=PipelineErrorCode.COMPENSATION_FAILED,
                                    reason=f"compensation_failed_after:{exc.reason}",
                                    failed_step=exc.failed_step,
                                    failed_item_ref=exc.failed_item_ref,
                                    compensation_status="failed",
                                    pipeline_run_id=pipeline_run_id,
                                ) from None
                        elif completed_write_nodes:
                            exc.compensation_status = "manual_required"
                        raise
                item_results.append(local_outputs)
            artifacts[node_id] = {"item_results": item_results, "item_count": len(source_items)}
            continue

        result = await _run_single_node(node)
        artifacts[node_id] = result

    return {
        "pipeline_run_id": pipeline_run_id,
        "pipeline_id": pipeline["pipeline_id"],
        "status": "succeeded",
        "artifacts": artifacts,
        "node_runs": node_runs,
        "compensation_events": compensation_events,
        "idempotent_success_reuse_count": idempotent_success_reuse_count,
    }
