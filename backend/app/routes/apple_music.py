from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.integrations.apple_music import build_apple_music_headers, generate_apple_music_developer_token
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/apple-music", tags=["apple-music-oauth"])
logger = logging.getLogger(__name__)


def _validate_apple_music_settings() -> None:
    settings = get_settings()
    if not settings.apple_music_team_id or not settings.apple_music_key_id or not settings.apple_music_private_key:
        raise HTTPException(status_code=500, detail="Apple Music OAuth 설정이 누락되었습니다.")


@router.post("/start")
async def apple_music_start(request: Request):
    _validate_apple_music_settings()
    _ = await get_authenticated_user_id(request)
    settings = get_settings()
    return {
        "ok": True,
        "developer_token": generate_apple_music_developer_token(),
        "app_name": settings.apple_music_app_name,
    }


@router.post("/connect")
async def apple_music_connect(request: Request):
    _validate_apple_music_settings()
    user_id = await get_authenticated_user_id(request)
    payload = await request.json()
    music_user_token = (payload.get("music_user_token") or "").strip() if isinstance(payload, dict) else ""
    if not music_user_token:
        raise HTTPException(status_code=400, detail="music_user_token이 필요합니다.")

    settings = get_settings()
    headers = build_apple_music_headers(music_user_token)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.music.apple.com/v1/me/storefront", headers=headers)

    if response.status_code >= 400:
        logger.warning("apple music connect verify failed: %s %s", response.status_code, response.text)
        raise HTTPException(status_code=400, detail="Apple Music 사용자 토큰 검증에 실패했습니다.")

    storefront_id = None
    try:
        data = response.json()
        items = data.get("data") or []
        if items:
            storefront_id = items[0].get("id")
    except Exception:
        storefront_id = None

    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(music_user_token)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "apple_music",
            "access_token_encrypted": encrypted,
            "workspace_id": storefront_id,
            "workspace_name": "apple_music",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return {"ok": True, "connected": True, "storefront_id": storefront_id}


@router.get("/status")
async def apple_music_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        result = (
            supabase.table("oauth_tokens")
            .select("workspace_id, updated_at")
            .eq("user_id", user_id)
            .eq("provider", "apple_music")
            .maybe_single()
            .execute()
        )
        return {"connected": bool(result.data), "integration": result.data}
    except Exception as exc:
        logger.exception("apple music status query failed: %s", exc)
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def apple_music_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "apple_music")
        .execute()
    )
    return {"ok": True, "connected": False}

