from __future__ import annotations

import argparse
import pathlib
import sys

from supabase import create_client

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


DEFAULT_SCOPES_BY_PROVIDER: dict[str, list[str]] = {
    "google": ["calendar.read"],
    "notion": ["insert_content"],
    "linear": ["read", "write"],
}


def _print_data_source_error(settings: object, exc: Exception) -> None:
    supabase_url = str(getattr(settings, "supabase_url", "") or "").strip()
    service_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
    host_hint = "unknown-host"
    try:
        host_hint = supabase_url.split("://", 1)[-1].split("/", 1)[0] or host_hint
    except Exception:
        host_hint = "unknown-host"
    print("[backfill-oauth-scopes]")
    print(f"- status: FAIL ({type(exc).__name__})")
    print(f"- SUPABASE_URL set: {'yes' if supabase_url else 'no'}")
    print(f"- SUPABASE_SERVICE_ROLE_KEY set: {'yes' if service_key else 'no'}")
    print(f"- target host: {host_hint}")
    print("- action: check .env value, DNS/network/VPN/firewall, then retry")


def _normalize_scopes(value: object) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    if isinstance(value, str):
        return [item.strip() for item in value.split(" ") if item.strip()]
    return []


def _needs_backfill(provider: str, granted_scopes: object) -> bool:
    normalized = _normalize_scopes(granted_scopes)
    return provider in DEFAULT_SCOPES_BY_PROVIDER and not normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill oauth_tokens.granted_scopes with provider defaults")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default is dry-run)")
    parser.add_argument("--limit", type=int, default=1000, help="Max rows to scan")
    args = parser.parse_args()

    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        rows = (
            supabase.table("oauth_tokens")
            .select("id,provider,granted_scopes,user_id")
            .limit(max(1, int(args.limit)))
            .execute()
            .data
            or []
        )
    except Exception as exc:
        _print_data_source_error(settings, exc)
        return 1

    candidates = [
        row for row in rows
        if _needs_backfill(str(row.get("provider") or "").strip().lower(), row.get("granted_scopes"))
    ]

    print("[backfill-oauth-scopes]")
    print(f"- scanned: {len(rows)}")
    print(f"- candidates: {len(candidates)}")
    print(f"- mode: {'apply' if args.apply else 'dry-run'}")

    updated = 0
    for row in candidates:
        provider = str(row.get("provider") or "").strip().lower()
        scopes = DEFAULT_SCOPES_BY_PROVIDER.get(provider, [])
        row_id = row.get("id")
        print(f"- candidate id={row_id} provider={provider} scopes={scopes}")
        if not args.apply:
            continue
        try:
            (
                supabase.table("oauth_tokens")
                .update({"granted_scopes": scopes})
                .eq("id", row_id)
                .execute()
            )
        except Exception as exc:
            _print_data_source_error(settings, exc)
            return 1
        updated += 1

    print(f"- updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
