from __future__ import annotations

from supabase import create_client

from app.core.config import get_settings
from app.security.token_vault import TokenVault


def load_user_provider_token(user_id: str, provider: str) -> str | None:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("access_token_encrypted")
        .eq("user_id", user_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None

    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        return None

    try:
        return TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)
    except Exception:
        return None

