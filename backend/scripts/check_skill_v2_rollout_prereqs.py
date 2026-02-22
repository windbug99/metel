from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _host_from_url(raw_url: str) -> str:
    parsed = urlparse(str(raw_url or "").strip())
    return str(parsed.hostname or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for Skill V2 rollout scripts.")
    parser.add_argument(
        "--check-dns",
        action="store_true",
        help="Resolve Supabase host DNS and fail when unresolved.",
    )
    args = parser.parse_args()

    settings = get_settings()
    supabase_url = str(getattr(settings, "supabase_url", "") or "").strip()
    service_key = str(getattr(settings, "supabase_service_role_key", "") or "").strip()
    host = _host_from_url(supabase_url)

    issues: list[str] = []
    checks: dict[str, str] = {}

    if not supabase_url:
        issues.append("missing_supabase_url")
        checks["supabase_url"] = "missing"
    else:
        checks["supabase_url"] = "ok"

    if not service_key:
        issues.append("missing_supabase_service_role_key")
        checks["supabase_service_role_key"] = "missing"
    else:
        checks["supabase_service_role_key"] = "ok"

    if not host:
        issues.append("invalid_supabase_url_host")
        checks["supabase_host"] = "invalid"
    else:
        checks["supabase_host"] = host
        if args.check_dns:
            try:
                socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
                checks["dns_resolution"] = "ok"
            except Exception as exc:
                issues.append(f"dns_resolution_failed:{type(exc).__name__}")
                checks["dns_resolution"] = "failed"

    ok = len(issues) == 0
    payload = {"ok": ok, "checks": checks, "issues": issues}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

