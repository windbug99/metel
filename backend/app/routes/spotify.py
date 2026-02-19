import base64
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

router = APIRouter(prefix="/api/oauth/spotify", tags=["spotify-oauth"])

SPOTIFY_SCOPE = "user-read-recently-played user-top-read playlist-read-private playlist-modify-private playlist-modify-public"


def _validate_spotify_settings() -> None:
    settings = get_settings()
    if not settings.spotify_client_id or not settings.spotify_client_secret or not settings.spotify_redirect_uri:
        raise HTTPException(status_code=500, detail="Spotify OAuth 설정이 누락되었습니다.")
    if not settings.spotify_state_secret:
        raise HTTPException(status_code=500, detail="SPOTIFY_STATE_SECRET 설정이 필요합니다.")


@router.post("/start")
async def spotify_oauth_start(request: Request):
    _validate_spotify_settings()
    settings = get_settings()
    user_id = await get_authenticated_user_id(request)
    state = build_state(user_id=user_id, secret=settings.spotify_state_secret or "")

    query = urlencode(
        {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "state": state,
            "scope": SPOTIFY_SCOPE,
            "show_dialog": "true",
        }
    )
    auth_url = f"https://accounts.spotify.com/authorize?{query}"
    return {"ok": True, "auth_url": auth_url}


@router.get("/callback")
async def spotify_oauth_callback(code: str, state: str):
    _validate_spotify_settings()
    settings = get_settings()

    user_id = verify_state(state=state, secret=settings.spotify_state_secret or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    basic = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    auth_header = base64.b64encode(basic).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Spotify token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Spotify")

    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(access_token)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "spotify",
            "access_token_encrypted": encrypted,
            "workspace_id": None,
            "workspace_name": "spotify",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?spotify=connected", status_code=302)


@router.get("/status")
async def spotify_oauth_status(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("updated_at")
        .eq("user_id", user_id)
        .eq("provider", "spotify")
        .maybe_single()
        .execute()
    )
    return {"connected": bool(result.data), "integration": result.data}


@router.delete("/disconnect")
async def spotify_oauth_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "spotify")
        .execute()
    )
    return {"ok": True, "connected": False}
