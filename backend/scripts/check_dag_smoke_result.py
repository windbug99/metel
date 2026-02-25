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


def _print_data_source_error(settings: object, exc: Exception) -> None:
    supabase_url = str(getattr(settings, "supabase_url", "") or "").strip()
    service_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
    host_hint = "unknown-host"
    try:
        host_hint = supabase_url.split("://", 1)[-1].split("/", 1)[0] or host_hint
    except Exception:
        host_hint = "unknown-host"
    print("[dag-smoke-check]")
    print("- verdict: FAIL")
    print(f"- reasons:\n  - data_source_error:{type(exc).__name__}")
    print("- diagnostics:")
    print(f"  - SUPABASE_URL set: {'yes' if supabase_url else 'no'}")
    print(f"  - SUPABASE_SERVICE_ROLE_KEY set: {'yes' if service_key else 'no'}")
    print(f"  - target host: {host_hint}")
    print("  - action: run in reachable environment and retry")


def _parse_detail_pairs(detail: str | None) -> dict[str, str]:
    raw = str(detail or "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for token in raw.split(";"):
        item = token.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _find_latest_dag_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        detail_map = _parse_detail_pairs(row.get("detail"))
        if detail_map.get("dag_pipeline") == "1":
            return row
        if str(row.get("plan_source") or "").strip() == "dag_template":
            return row
    return None


def _read_dag_quality_verdict(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("verdict") or "").strip()


def _evaluate_smoke(
    *,
    dag_row_found: bool,
    pipeline_run_id: str,
    succeeded_links_count: int,
    dag_quality_verdict: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not dag_row_found:
        reasons.append("missing_dag_row")
    if not pipeline_run_id:
        reasons.append("missing_pipeline_run_id")
    if succeeded_links_count <= 0:
        reasons.append("missing_succeeded_pipeline_links")
    if dag_quality_verdict != "PASS":
        reasons.append(f"dag_quality_not_pass:{dag_quality_verdict or 'missing'}")
    return len(reasons) == 0, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Check DAG staging smoke verification points")
    parser.add_argument("--limit", type=int, default=100, help="Recent command_logs rows to inspect")
    parser.add_argument(
        "--dag-quality-json",
        type=str,
        default=str(ROOT.parent / "docs" / "reports" / "dag_quality_latest.json"),
        help="Path to dag quality JSON report",
    )
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    table = (settings.pipeline_links_table or "pipeline_links").strip() or "pipeline_links"

    try:
        logs = (
            supabase.table("command_logs")
            .select("detail,created_at,status,error_code,plan_source,execution_mode")
            .eq("command", "agent_plan")
            .order("created_at", desc=True)
            .limit(max(1, int(args.limit)))
            .execute()
            .data
            or []
        )
    except Exception as exc:
        _print_data_source_error(settings, exc)
        return 1
    dag_row = _find_latest_dag_row(logs)
    latest_row = logs[0] if logs else {}
    detail_map = _parse_detail_pairs((dag_row or {}).get("detail"))
    pipeline_run_id = str(detail_map.get("pipeline_run_id") or "").strip()

    links: list[dict[str, Any]] = []
    if pipeline_run_id:
        try:
            links = (
                supabase.table(table)
                .select("status,run_id,updated_at")
                .eq("run_id", pipeline_run_id)
                .order("updated_at", desc=True)
                .limit(100)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            _print_data_source_error(settings, exc)
            return 1
    succeeded_links_count = len(
        [row for row in links if str(row.get("status") or "").strip().lower() == "succeeded"]
    )
    dag_quality_verdict = _read_dag_quality_verdict(pathlib.Path(args.dag_quality_json))

    passed, reasons = _evaluate_smoke(
        dag_row_found=dag_row is not None,
        pipeline_run_id=pipeline_run_id,
        succeeded_links_count=succeeded_links_count,
        dag_quality_verdict=dag_quality_verdict,
    )

    print("[dag-smoke-check]")
    print(f"- dag_row_found: {'yes' if dag_row is not None else 'no'}")
    print(f"- pipeline_run_id: {pipeline_run_id or 'missing'}")
    print(f"- succeeded_pipeline_links: {succeeded_links_count}")
    print(f"- dag_quality_verdict: {dag_quality_verdict or 'missing'}")
    if dag_row is None and latest_row:
        print("- latest_agent_plan_row:")
        print(f"  - created_at: {str(latest_row.get('created_at') or '').strip() or 'missing'}")
        print(f"  - status: {str(latest_row.get('status') or '').strip() or 'missing'}")
        print(f"  - plan_source: {str(latest_row.get('plan_source') or '').strip() or 'missing'}")
        print(f"  - execution_mode: {str(latest_row.get('execution_mode') or '').strip() or 'missing'}")
        print(f"  - error_code: {str(latest_row.get('error_code') or '').strip() or 'none'}")
        print(f"  - detail: {str(latest_row.get('detail') or '').strip() or 'missing'}")
    print(f"- verdict: {'PASS' if passed else 'FAIL'}")
    if reasons:
        print("- reasons:")
        for reason in reasons:
            print(f"  - {reason}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
