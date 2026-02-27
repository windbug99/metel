from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from datetime import datetime, timedelta, timezone

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


def _parse_pipeline_json(detail_pairs: dict[str, str]) -> dict:
    value = str(detail_pairs.get("pipeline_json") or "").strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _classify_mode(row: dict) -> str:
    detail_pairs = _parse_detail_pairs(row.get("detail"))
    payload = _parse_pipeline_json(detail_pairs)
    plan_source = str(row.get("plan_source") or "").strip().lower()
    router_mode = str(payload.get("router_mode") or "").strip()
    if router_mode == "STEPWISE_PIPELINE":
        return "stepwise"
    if plan_source == "stepwise_template":
        return "stepwise"
    if bool(payload.get("composed_pipeline")):
        return "dag"
    if plan_source == "dag_template":
        return "dag"
    if str(detail_pairs.get("dag_pipeline") or "").strip() == "1":
        return "dag"
    return "legacy"


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except Exception:
        return None


def _compute_mode_metrics(rows: list[dict]) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[dict]] = {"stepwise": [], "dag": [], "legacy": []}
    for row in rows:
        grouped[_classify_mode(row)].append(row)

    out: dict[str, dict[str, float | int | None]] = {}
    for mode, items in grouped.items():
        total = len(items)
        if total == 0:
            out[mode] = {
                "run_count": 0,
                "success_rate_pct": 0.0,
                "error_rate_pct": 0.0,
                "validation_fail_rate_pct": 0.0,
                "p95_latency_ms": None,
            }
            continue
        success = 0
        validation_fail = 0
        latencies: list[int] = []
        for row in items:
            final_status = str(row.get("final_status") or row.get("status") or "").strip().lower()
            error_code = str(row.get("error_code") or "").strip().lower()
            if final_status == "success":
                success += 1
            if error_code in {"validation_error", "missing_required_fields"}:
                validation_fail += 1
            detail_pairs = _parse_detail_pairs(row.get("detail"))
            latency = _as_int(detail_pairs.get("analysis_latency_ms"))
            if latency is not None and latency >= 0:
                latencies.append(latency)
        error_count = total - success
        p95 = None
        if latencies:
            sorted_values = sorted(latencies)
            idx = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * 0.95) - 1))
            p95 = sorted_values[idx]
        out[mode] = {
            "run_count": total,
            "success_rate_pct": round((success / total) * 100.0, 2),
            "error_rate_pct": round((error_count / total) * 100.0, 2),
            "validation_fail_rate_pct": round((validation_fail / total) * 100.0, 2),
            "p95_latency_ms": p95,
        }
    return out


def _build_markdown(metrics: dict[str, dict[str, float | int | None]], *, window_label: str) -> str:
    lines = [
        "# Stepwise vs Legacy Quality Report",
        "",
        f"- window: {window_label}",
        "",
        "| mode | run_count | success_rate_pct | error_rate_pct | validation_fail_rate_pct | p95_latency_ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode in ("stepwise", "dag", "legacy"):
        item = metrics.get(mode, {})
        lines.append(
            f"| {mode} | {item.get('run_count', 0)} | {item.get('success_rate_pct', 0.0)} | "
            f"{item.get('error_rate_pct', 0.0)} | {item.get('validation_fail_rate_pct', 0.0)} | "
            f"{item.get('p95_latency_ms', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def _window_start_iso_utc(days: int) -> str:
    if int(days) <= 0:
        return ""
    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    return since.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare STEPWISE vs DAG/legacy quality metrics from command_logs.")
    parser.add_argument("--limit", type=int, default=300, help="Max rows from command_logs")
    parser.add_argument("--days", type=int, default=7, help="UTC day window (0 disables)")
    parser.add_argument("--input-json", type=str, default="", help="Optional offline input json file (list of command_logs rows)")
    parser.add_argument("--output", type=str, default="", help="Optional markdown output path")
    parser.add_argument("--output-json", type=str, default="", help="Optional json output path")
    args = parser.parse_args()

    rows: list[dict]
    window_start = _window_start_iso_utc(max(0, int(args.days or 0)))
    window_label = f"last {max(0, int(args.days or 0))} day(s)" if max(0, int(args.days or 0)) > 0 else "all"

    if str(args.input_json or "").strip():
        with open(args.input_json, "r", encoding="utf-8") as fp:
            loaded = json.load(fp)
        rows = [item for item in (loaded or []) if isinstance(item, dict)]
    else:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        query = (
            supabase.table("command_logs")
            .select("status,final_status,error_code,detail,created_at,plan_source")
            .eq("command", "agent_plan")
            .order("created_at", desc=True)
            .limit(max(1, int(args.limit or 300)))
        )
        if window_start:
            query = query.gte("created_at", window_start)
        rows = list(query.execute().data or [])

    metrics = _compute_mode_metrics(rows)
    report_md = _build_markdown(metrics, window_label=window_label)
    print(report_md)

    if args.output:
        pathlib.Path(args.output).write_text(report_md, encoding="utf-8")
    if args.output_json:
        pathlib.Path(args.output_json).write_text(
            json.dumps(
                {
                    "window": window_label,
                    "rows": len(rows),
                    "metrics": metrics,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
