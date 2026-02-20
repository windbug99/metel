from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.loop import run_agent_analysis
from app.core.config import get_settings


@dataclass
class Scenario:
    name: str
    prompt: str


SCENARIOS = [
    Scenario(
        name="linear_to_notion_summary",
        prompt="Linear의 기획관련 이슈를 찾아서 3문장으로 요약해 Notion의 새로운 페이지에 생성해서 저장하세요",
    ),
    Scenario(
        name="notion_data_source_to_notion_summary",
        prompt="노션 데이터소스 {data_source_id} 최근 5개를 3문장으로 요약해서 새 페이지에 저장하세요",
    ),
]


def _connected_services_for_user(user_id: str) -> list[str]:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("oauth_tokens")
        .select("provider")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    providers = sorted({str(row.get("provider", "")).strip().lower() for row in rows if row.get("provider")})
    return [item for item in providers if item]


def _find_user_with_services(required: set[str]) -> str | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = supabase.table("oauth_tokens").select("user_id,provider").execute().data or []
    service_map: dict[str, set[str]] = {}
    for row in rows:
        user_id = str(row.get("user_id") or "").strip()
        provider = str(row.get("provider") or "").strip().lower()
        if not user_id or not provider:
            continue
        service_map.setdefault(user_id, set()).add(provider)
    for user_id, providers in service_map.items():
        if required.issubset(providers):
            return user_id
    return None


def _load_any_data_source_id(user_id: str) -> str | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    rows = (
        supabase.table("command_logs")
        .select("detail")
        .eq("user_id", user_id)
        .like("detail", "%data_source%")
        .limit(20)
        .execute()
        .data
        or []
    )
    import re

    for row in rows:
        detail = str(row.get("detail") or "")
        match = re.search(r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})", detail)
        if match:
            return match.group(1)
    return None


async def _run(user_id: str, data_source_id: str | None, *, dry_run: bool) -> int:
    connected_services = _connected_services_for_user(user_id)
    print(f"user_id={user_id}")
    print(f"connected_services={connected_services}")

    if dry_run:
        print("dry_run=true")
        for scenario in SCENARIOS:
            prompt = scenario.prompt.format(data_source_id=(data_source_id or "<DATA_SOURCE_ID>"))
            print(f"- scenario={scenario.name}")
            print(f"  prompt={prompt}")
        return 0

    for scenario in SCENARIOS:
        prompt = scenario.prompt.format(data_source_id=(data_source_id or ""))
        if "{data_source_id}" in scenario.prompt and not data_source_id:
            print(f"scenario={scenario.name} skipped (data_source_id missing)")
            continue

        print(f"scenario={scenario.name} running")
        result = await run_agent_analysis(prompt, connected_services, user_id)
        status = "ok" if result.ok else "error"
        print(f"  status={status} stage={result.stage} plan_source={result.plan_source}")
        print(f"  result_summary={result.result_summary}")
        if result.execution:
            print(f"  execution_success={result.execution.success}")
            print(f"  execution_summary={result.execution.summary}")
            for step in result.execution.steps[:8]:
                print(f"    - {step.name}: {step.status} ({step.detail})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live metel agent E2E scenarios")
    parser.add_argument("--user-id", default="", help="Target user id; omit to auto-find one")
    parser.add_argument("--data-source-id", default="", help="Notion data_source_id for scenario 2")
    parser.add_argument("--dry-run", action="store_true", help="Print scenarios without executing")
    args = parser.parse_args()

    if args.dry_run and not args.user_id.strip():
        print("dry_run=true")
        print("user_id=<AUTO_FIND_AT_RUNTIME>")
        for scenario in SCENARIOS:
            prompt = scenario.prompt.format(data_source_id="<DATA_SOURCE_ID>")
            print(f"- scenario={scenario.name}")
            print(f"  prompt={prompt}")
        return 0

    try:
        user_id = args.user_id.strip() or _find_user_with_services({"notion", "linear"})
    except Exception as exc:
        print(f"failed_to_find_user: {exc.__class__.__name__}")
        return 1
    if not user_id:
        print("No user found with both notion and linear connections.")
        return 1

    try:
        data_source_id = args.data_source_id.strip() or _load_any_data_source_id(user_id)
    except Exception:
        data_source_id = args.data_source_id.strip()
    return asyncio.run(_run(user_id=user_id, data_source_id=data_source_id or None, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
