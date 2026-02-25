from __future__ import annotations

import argparse
import socket
import sys
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


def _extract_host(url: str) -> str:
    parsed = urlparse(url.strip())
    return (parsed.hostname or "").strip()


def _rest_url(url: str) -> str:
    return f"{url.rstrip('/')}/rest/v1/"


def _is_reachable_status(code: int) -> bool:
    # 2xx/3xx/4xx are still useful connectivity signals here.
    return 200 <= code < 500


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for Supabase connectivity")
    parser.add_argument("--timeout-sec", type=float, default=5.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    settings = get_settings()
    supabase_url = str(settings.supabase_url or "").strip()
    service_key = str(settings.supabase_service_role_key or "").strip()
    host = _extract_host(supabase_url)

    print("[supabase-connectivity]")
    print(f"- SUPABASE_URL set: {'yes' if supabase_url else 'no'}")
    print(f"- SUPABASE_SERVICE_ROLE_KEY set: {'yes' if service_key else 'no'}")
    print(f"- host: {host or 'unknown'}")

    if not supabase_url or not service_key or not host:
        print("- verdict: FAIL")
        print("- reason: missing required config")
        return 1

    try:
        socket.getaddrinfo(host, 443)
        print("- dns: OK")
    except Exception as exc:
        print("- dns: FAIL")
        print(f"- reason: {type(exc).__name__}")
        return 1

    rest_url = _rest_url(supabase_url)
    try:
        response = httpx.get(
            rest_url,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=float(args.timeout_sec),
        )
    except Exception as exc:
        print("- http: FAIL")
        print(f"- reason: {type(exc).__name__}")
        return 1

    print(f"- http status: {response.status_code}")
    if _is_reachable_status(int(response.status_code)):
        print("- verdict: PASS")
        return 0

    print("- verdict: FAIL")
    print("- reason: unexpected http status")
    return 1


if __name__ == "__main__":
    sys.exit(main())
