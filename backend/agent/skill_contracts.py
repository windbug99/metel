from __future__ import annotations

import json
from pathlib import Path

REQUIRED_TOP_KEYS = {
    "name",
    "version",
    "summary",
    "provider",
    "autofill",
    "input_schema",
    "output_schema",
    "examples",
    "runtime_tools",
}


def _contracts_dir() -> Path:
    return Path(__file__).resolve().parent / "skills" / "contracts"


def list_contract_files() -> list[Path]:
    root = _contracts_dir()
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*.json") if path.is_file())


def load_contract(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError(f"contract must be object: {path}")
    return payload


def validate_contract(contract: dict, path: Path | None = None) -> list[str]:
    errors: list[str] = []
    missing = sorted(key for key in REQUIRED_TOP_KEYS if key not in contract)
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")

    name = str(contract.get("name") or "").strip()
    if not name or "." not in name:
        errors.append("name must include service prefix (e.g., notion.page_create)")

    provider = contract.get("provider")
    if not isinstance(provider, dict):
        errors.append("provider must be object")
    else:
        service = str(provider.get("service") or "").strip()
        if service and name and name.split(".", 1)[0] != service:
            errors.append("name/service prefix mismatch")

    runtime_tools = contract.get("runtime_tools")
    if not isinstance(runtime_tools, list) or not runtime_tools:
        errors.append("runtime_tools must be non-empty array")
    else:
        invalid_tools = [item for item in runtime_tools if not isinstance(item, str) or not item.strip()]
        if invalid_tools:
            errors.append("runtime_tools items must be non-empty strings")

    for schema_key in ("input_schema", "output_schema"):
        schema = contract.get(schema_key)
        if not isinstance(schema, dict):
            errors.append(f"{schema_key} must be object")
            continue
        if str(schema.get("type") or "") != "object":
            errors.append(f"{schema_key}.type must be 'object'")

    examples = contract.get("examples")
    if not isinstance(examples, list) or not examples:
        errors.append("examples must be non-empty array")

    if path is not None:
        expected_prefix = path.stem.replace("_", ".")
        if name and not name.startswith(expected_prefix.split(".", 1)[0]):
            errors.append("file name/service mismatch")

    return errors


def validate_all_contracts() -> tuple[int, dict[str, list[str]]]:
    files = list_contract_files()
    failures: dict[str, list[str]] = {}
    for file_path in files:
        try:
            contract = load_contract(file_path)
        except Exception as exc:
            failures[str(file_path)] = [f"load_error: {exc}"]
            continue
        errors = validate_contract(contract, path=file_path)
        if errors:
            failures[str(file_path)] = errors
    return len(files), failures


def load_all_contracts() -> list[dict]:
    contracts: list[dict] = []
    for path in list_contract_files():
        contracts.append(load_contract(path))
    return contracts


def load_contract_by_name(skill_name: str) -> dict | None:
    target = str(skill_name or "").strip()
    if not target:
        return None
    for contract in load_all_contracts():
        if str(contract.get("name") or "").strip() == target:
            return contract
    return None


def service_for_skill(skill_name: str) -> str | None:
    contract = load_contract_by_name(skill_name)
    if not isinstance(contract, dict):
        return None
    provider = contract.get("provider")
    if not isinstance(provider, dict):
        return None
    service = str(provider.get("service") or "").strip().lower()
    return service or None


def runtime_tools_for_skill(skill_name: str) -> list[str]:
    contract = load_contract_by_name(skill_name)
    if not contract:
        return []
    out: list[str] = []
    for tool in contract.get("runtime_tools") or []:
        tool_name = str(tool or "").strip()
        if tool_name and tool_name not in out:
            out.append(tool_name)
    return out


def required_scopes_for_skill(skill_name: str) -> list[str]:
    contract = load_contract_by_name(skill_name)
    if not contract:
        return []
    provider = contract.get("provider")
    if not isinstance(provider, dict):
        return []
    scopes = provider.get("scopes")
    if not isinstance(scopes, list):
        return []
    out: list[str] = []
    for scope in scopes:
        value = str(scope or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def infer_skill_name_from_runtime_tools(selected_tools: list[str]) -> str | None:
    requested = [str(item or "").strip() for item in selected_tools if str(item or "").strip()]
    if not requested:
        return None
    request_set = set(requested)

    exact_matches: list[str] = []
    superset_matches: list[tuple[str, int]] = []
    for contract in load_all_contracts():
        name = str(contract.get("name") or "").strip()
        if not name:
            continue
        tools = [str(item or "").strip() for item in (contract.get("runtime_tools") or []) if str(item or "").strip()]
        if not tools:
            continue
        tool_set = set(tools)
        if tool_set == request_set:
            exact_matches.append(name)
        elif request_set.issubset(tool_set):
            superset_matches.append((name, len(tool_set)))

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None

    if not superset_matches:
        return None
    superset_matches.sort(key=lambda item: item[1])
    smallest_size = superset_matches[0][1]
    smallest_names = [name for name, size in superset_matches if size == smallest_size]
    if len(smallest_names) == 1:
        return smallest_names[0]
    return None


def runtime_tools_for_services(services: list[str]) -> list[str]:
    target = {item.strip().lower() for item in services if item and item.strip()}
    out: list[str] = []
    seen: set[str] = set()
    for contract in load_all_contracts():
        provider = contract.get("provider") if isinstance(contract, dict) else None
        service = str((provider or {}).get("service") or "").strip().lower() if isinstance(provider, dict) else ""
        if service not in target:
            continue
        for tool in contract.get("runtime_tools") or []:
            tool_name = str(tool or "").strip()
            if not tool_name or tool_name in seen:
                continue
            seen.add(tool_name)
            out.append(tool_name)
    return out
