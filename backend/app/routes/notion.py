from urllib.parse import urlencode
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from supabase import create_client

from app.core.config import get_settings
from app.core.state import build_state, verify_state
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/notion", tags=["notion-oauth"])


@router.get("/start")
async def notion_oauth_start(user_id: str = Query(..., min_length=10)):
    settings = get_settings()
    state = build_state(user_id=user_id, secret=settings.notion_state_secret)

    query = urlencode(
        {
            "client_id": settings.notion_client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": settings.notion_redirect_uri,
            "state": state,
        }
    )
    auth_url = f"https://api.notion.com/v1/oauth/authorize?{query}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def notion_oauth_callback(code: str, state: str):
    settings = get_settings()

    user_id = verify_state(state=state, secret=settings.notion_state_secret)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            auth=(settings.notion_client_id, settings.notion_client_secret),
            headers={"Content-Type": "application/json"},
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.notion_redirect_uri,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Notion token exchange failed: {response.text}")

    data = response.json()
    access_token = data.get("access_token")

    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Notion")

    vault = TokenVault(settings.notion_token_encryption_key)
    encrypted = vault.encrypt(access_token)

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    upsert_payload = {
        "user_id": user_id,
        "provider": "notion",
        "access_token_encrypted": encrypted,
        "workspace_id": data.get("workspace_id"),
        "workspace_name": data.get("workspace_name"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    supabase.table("oauth_tokens").upsert(upsert_payload, on_conflict="user_id,provider").execute()

    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?notion=connected", status_code=302)


@router.get("/status")
async def notion_oauth_status(user_id: str = Query(..., min_length=10)):
    try:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

        result = (
            supabase.table("oauth_tokens")
            .select("workspace_name, workspace_id, updated_at")
            .eq("user_id", user_id)
            .eq("provider", "notion")
            .maybe_single()
            .execute()
        )

        return {"connected": bool(result.data), "integration": result.data}
    except Exception:
        # Avoid bubbling runtime errors as opaque CORS failures on the frontend.
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def notion_oauth_disconnect(user_id: str = Query(..., min_length=10)):
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "notion")
        .execute()
    )

    return {"ok": True, "connected": False}
