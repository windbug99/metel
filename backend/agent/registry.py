from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


TOOL_SPECS_DIR = Path(__file__).resolve().parent / "tool_specs"


class ToolSpecValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    service: str
    tool_name: str
    description: str
    method: str
    path: str
    adapter_function: str
    input_schema: dict[str, Any]
    required_scopes: tuple[str, ...]
    idempotency_key_policy: str
    error_map: dict[str, str]

    def to_llm_tool(self) -> dict[str, Any]:
        return {
            "name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolSpecValidationError(f"Invalid JSON in {path}") from exc


def _require_str(spec: dict[str, Any], key: str, path: Path) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolSpecValidationError(f"{path}: '{key}' must be a non-empty string")
    return value


def _validate_service_spec(spec: dict[str, Any], path: Path) -> None:
    _require_str(spec, "service", path)
    _require_str(spec, "version", path)
    _require_str(spec, "base_url", path)
    auth = spec.get("auth")
    if not isinstance(auth, dict):
        raise ToolSpecValidationError(f"{path}: 'auth' must be an object")
    if not isinstance(auth.get("required_scopes", []), list):
        raise ToolSpecValidationError(f"{path}: 'auth.required_scopes' must be an array")
    tools = spec.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ToolSpecValidationError(f"{path}: 'tools' must be a non-empty array")
    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise ToolSpecValidationError(f"{path}: tools[{idx}] must be an object")
        for field in ("tool_name", "description", "method", "path", "adapter_function"):
            _require_str(tool, field, path)
        if not isinstance(tool.get("input_schema"), dict):
            raise ToolSpecValidationError(f"{path}: tools[{idx}].input_schema must be an object")
        required_scopes = tool.get("required_scopes", [])
        if not isinstance(required_scopes, list):
            raise ToolSpecValidationError(f"{path}: tools[{idx}].required_scopes must be an array")


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition]):
        self._tools = tools
        self._by_name = {tool.tool_name: tool for tool in tools}

    @classmethod
    def load_from_disk(cls) -> "ToolRegistry":
        tools: list[ToolDefinition] = []
        for path in sorted(TOOL_SPECS_DIR.glob("*.json")):
            if path.name == "schema.json":
                continue
            spec = _load_json(path)
            _validate_service_spec(spec, path)
            service = spec["service"].strip().lower()
            for item in spec["tools"]:
                tools.append(
                    ToolDefinition(
                        service=service,
                        tool_name=item["tool_name"].strip(),
                        description=item["description"].strip(),
                        method=item["method"].strip(),
                        path=item["path"].strip(),
                        adapter_function=item["adapter_function"].strip(),
                        input_schema=item["input_schema"],
                        required_scopes=tuple(item.get("required_scopes", [])),
                        idempotency_key_policy=item.get("idempotency_key_policy", "none"),
                        error_map=item.get("error_map", {}),
                    )
                )
        return cls(tools)

    def list_services(self) -> list[str]:
        return sorted({tool.service for tool in self._tools})

    def list_tools(self, service: str | None = None) -> list[ToolDefinition]:
        if not service:
            return list(self._tools)
        normalized = service.lower().strip()
        return [tool for tool in self._tools if tool.service == normalized]

    def get_tool(self, tool_name: str) -> ToolDefinition:
        try:
            return self._by_name[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {tool_name}") from exc

    def list_available_tools(
        self,
        *,
        connected_services: Iterable[str],
        granted_scopes: dict[str, set[str]] | None = None,
    ) -> list[ToolDefinition]:
        connected = {service.lower().strip() for service in connected_services}
        scope_map = {k.lower().strip(): v for k, v in (granted_scopes or {}).items()}
        allowed: list[ToolDefinition] = []
        for tool in self._tools:
            if tool.service not in connected:
                continue
            required = set(tool.required_scopes)
            if not required:
                allowed.append(tool)
                continue
            granted = scope_map.get(tool.service)
            if granted is None or required.issubset(granted):
                allowed.append(tool)
        return allowed

    def list_llm_tools(
        self,
        *,
        connected_services: Iterable[str],
        granted_scopes: dict[str, set[str]] | None = None,
    ) -> list[dict[str, Any]]:
        return [tool.to_llm_tool() for tool in self.list_available_tools(connected_services=connected_services, granted_scopes=granted_scopes)]


@lru_cache(maxsize=1)
def load_registry() -> ToolRegistry:
    return ToolRegistry.load_from_disk()


def reload_registry() -> ToolRegistry:
    load_registry.cache_clear()
    return load_registry()

