from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/openai", tags=["openai"])
logger = logging.getLogger(__name__)


def _mask_openai_key(api_key: str) -> str:
    suffix = (api_key or "").strip()[-4:]
    if not suffix:
        return "****"
    return f"****{suffix}"


async def _validate_openai_key(api_key: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="OpenAI API 키 검증에 실패했습니다.")


@router.post("/start")
async def openai_start(request: Request):
    _ = await get_authenticated_user_id(request)
    return {
        "ok": True,
        "mode": "api_key",
        "instructions": "OpenAI API 키를 입력해 연결하세요.",
    }


@router.post("/connect")
async def openai_connect(request: Request):
    user_id = await get_authenticated_user_id(request)
    payload = await request.json()
    api_key = (payload.get("api_key") or "").strip() if isinstance(payload, dict) else ""
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key가 필요합니다.")

    await _validate_openai_key(api_key)

    settings = get_settings()
    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(api_key)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "openai",
            "access_token_encrypted": encrypted,
            "workspace_id": _mask_openai_key(api_key),
            "workspace_name": "openai",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return {"ok": True, "connected": True, "key_masked": _mask_openai_key(api_key)}


@router.get("/status")
async def openai_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        result = (
            supabase.table("oauth_tokens")
            .select("workspace_id, updated_at")
            .eq("user_id", user_id)
            .eq("provider", "openai")
            .maybe_single()
            .execute()
        )
        return {"connected": bool(result.data), "integration": result.data}
    except Exception as exc:
        logger.exception("openai status query failed: %s", exc)
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def openai_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "openai")
        .execute()
    )
    return {"ok": True, "connected": False}

