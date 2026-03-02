from __future__ import annotations

import hashlib
import secrets


API_KEY_PREFIX = "metel_"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    # 32 bytes token -> urlsafe text, stripped for header-safe compact key.
    token = secrets.token_urlsafe(32).rstrip("=")
    return f"{API_KEY_PREFIX}{token}"
