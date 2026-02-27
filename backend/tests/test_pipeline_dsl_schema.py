import json
from pathlib import Path


def test_pipeline_dsl_schema_has_required_top_level_fields():
    path = Path(__file__).resolve().parents[1] / "agent" / "pipeline_dsl_schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["type"] == "object"
    assert "required" in payload
    assert {"pipeline_id", "version", "limits", "nodes"}.issubset(set(payload["required"]))
    assert payload["properties"]["version"]["enum"] == ["1.0"]
    assert payload["properties"]["limits"]["properties"]["max_nodes"]["maximum"] == 6


def test_pipeline_dsl_schema_node_type_enum_is_fixed():
    path = Path(__file__).resolve().parents[1] / "agent" / "pipeline_dsl_schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    node_enum = payload["definitions"]["node"]["properties"]["type"]["enum"]
    assert node_enum == ["skill", "llm_transform", "for_each", "aggregate", "verify"]


def test_pipeline_dsl_schema_for_each_extended_fields():
    path = Path(__file__).resolve().parents[1] / "agent" / "pipeline_dsl_schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    node_props = payload["definitions"]["node"]["properties"]
    assert "items_ref" in node_props
    assert "max_items" in node_props
    assert "concurrency" in node_props
    assert node_props["on_item_fail"]["enum"] == ["stop_all", "skip", "compensate"]


def test_pipeline_dsl_schema_verify_extended_fields():
    path = Path(__file__).resolve().parents[1] / "agent" / "pipeline_dsl_schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    node_props = payload["definitions"]["node"]["properties"]
    assert node_props["on_fail"]["enum"] == ["stop", "fallback", "clarification"]
    assert "fallback_policy" in node_props
