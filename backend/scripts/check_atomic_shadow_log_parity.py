from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _parse_detail_pairs(detail: str | None) -> dict[str, str]:
    raw = str(detail or "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for token in raw.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _load_rows(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def evaluate_parity(*, command_rows: list[dict[str, Any]], pipeline_rows: list[dict[str, Any]]) -> dict[str, Any]:
    target: list[dict[str, Any]] = []
    for row in command_rows:
        detail_map = _parse_detail_pairs(str(row.get("detail") or ""))
        mode = detail_map.get("atomic_overhaul_shadow_mode")
        if mode not in {"0", "1"}:
            continue
        request_id = detail_map.get("request_id") or ""
        if not request_id:
            continue
        target.append(
            {
                "request_id": request_id,
                "shadow_mode": mode,
                "status": str(row.get("status") or "").strip().lower(),
                "error_code": str(row.get("error_code") or "").strip().lower(),
            }
        )

    pipeline_request_ids = {
        str(item.get("request_id") or "").strip()
        for item in pipeline_rows
        if str(item.get("request_id") or "").strip()
    }
    matched = [item for item in target if item["request_id"] in pipeline_request_ids]
    shadow_rows = [item for item in target if item["shadow_mode"] == "1"]
    shadow_matched = [item for item in matched if item["shadow_mode"] == "1"]

    return {
        "command_target_count": len(target),
        "pipeline_row_count": len(pipeline_rows),
        "matched_count": len(matched),
        "shadow_target_count": len(shadow_rows),
        "shadow_matched_count": len(shadow_matched),
        "compare_ready": len(matched) > 0,
        "shadow_compare_ready": len(shadow_matched) > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Atomic command_logs/pipeline_step_logs parity by request_id.")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--input-command-json", type=str, default="")
    parser.add_argument("--input-pipeline-json", type=str, default="")
    parser.add_argument("--output-json", type=str, default="")
    args = parser.parse_args()

    if args.input_command_json and args.input_pipeline_json:
        command_rows = _load_rows(args.input_command_json)
        pipeline_rows = _load_rows(args.input_pipeline_json)
    else:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        command_rows = (
            supabase.table("command_logs")
            .select("status,error_code,detail,created_at")
            .eq("command", "agent_plan")
            .order("created_at", desc=True)
            .limit(max(1, int(args.limit)))
            .execute()
            .data
            or []
        )
        pipeline_rows = (
            supabase.table("pipeline_step_logs")
            .select("request_id,created_at")
            .order("created_at", desc=True)
            .limit(max(1, int(args.limit) * 3))
            .execute()
            .data
            or []
        )

    report = evaluate_parity(command_rows=command_rows, pipeline_rows=pipeline_rows)
    print("[Atomic Shadow Log Parity]")
    print(f"- command target rows: {report['command_target_count']}")
    print(f"- pipeline rows: {report['pipeline_row_count']}")
    print(f"- matched request_id rows: {report['matched_count']}")
    print(f"- shadow target rows: {report['shadow_target_count']}")
    print(f"- shadow matched rows: {report['shadow_matched_count']}")
    print(f"- compare_ready: {report['compare_ready']}")
    print(f"- shadow_compare_ready: {report['shadow_compare_ready']}")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(report, fp, ensure_ascii=False, indent=2)

    return 0 if report["compare_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
