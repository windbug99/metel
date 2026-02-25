from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.core.state import build_state, verify_state
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/google", tags=["google-oauth"])

# Calendar read-only is the minimum scope for "today events" lookup.
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _validate_google_oauth_settings() -> None:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth 설정이 누락되었습니다.")
    if not settings.google_state_secret:
        raise HTTPException(status_code=500, detail="GOOGLE_STATE_SECRET 설정이 필요합니다.")


@router.post("/start")
async def google_oauth_start(request: Request):
    _validate_google_oauth_settings()
    settings = get_settings()
    user_id = await get_authenticated_user_id(request)
    state = build_state(user_id=user_id, secret=settings.google_state_secret or "")

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPE,
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
    )
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return {"ok": True, "auth_url": auth_url}


@router.get("/callback")
async def google_oauth_callback(code: str, state: str):
    _validate_google_oauth_settings()
    settings = get_settings()

    user_id = verify_state(state=state, secret=settings.google_state_secret or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Google")

    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(access_token)
    scope_text = str(payload.get("scope") or "").strip()
    granted_scopes = [item.strip() for item in scope_text.split(" ") if item.strip()] or ["calendar.read"]
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "google",
            "access_token_encrypted": encrypted,
            "granted_scopes": granted_scopes,
            "workspace_id": None,
            "workspace_name": "google_calendar",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?google=connected", status_code=302)


@router.get("/status")
async def google_oauth_status(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("updated_at")
        .eq("user_id", user_id)
        .eq("provider", "google")
        .maybe_single()
        .execute()
    )
    data = result.data if result is not None else None
    return {"connected": bool(data), "integration": data}


@router.delete("/disconnect")
async def google_oauth_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "google")
        .execute()
    )
    return {"ok": True, "connected": False}
