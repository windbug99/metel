from fastapi import HTTPException

from agent.registry import ToolDefinition
from agent.tool_runner import _build_path, _extract_path_params, _strip_path_params
from agent.tool_runner import _validate_payload_by_schema


def test_extract_path_params():
    params = _extract_path_params("/v1/blocks/{block_id}/children")
    assert params == ["block_id"]


def test_build_path():
    path = _build_path("/v1/pages/{page_id}/properties/{property_id}", {"page_id": "p1", "property_id": "title"})
    assert path == "/v1/pages/p1/properties/title"


def test_strip_path_params():
    payload = {"block_id": "b1", "page_size": 20}
    stripped = _strip_path_params("/v1/blocks/{block_id}/children", payload)
    assert stripped == {"page_size": 20}


def _dummy_tool() -> ToolDefinition:
    return ToolDefinition(
        service="notion",
        tool_name="dummy_tool",
        description="dummy",
        method="POST",
        path="/v1/dummy/{id}",
        adapter_function="dummy",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["id"],
        },
        required_scopes=(),
        idempotency_key_policy="none",
        error_map={},
    )


def test_validate_payload_by_schema_ok():
    _validate_payload_by_schema(_dummy_tool(), {"id": "abc", "page_size": 5})


def test_validate_payload_by_schema_error():
    try:
        _validate_payload_by_schema(_dummy_tool(), {"id": "abc", "page_size": 999})
    except HTTPException as exc:
        assert "VALIDATION_MAX:page_size" in str(exc.detail)
    else:
        assert False, "expected HTTPException"
