from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.core.state import build_state, verify_state
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/github", tags=["github-oauth"])

GITHUB_SCOPE = "read:user repo"


def _frontend_dashboard_url(raw_frontend_url: str, query: str) -> str:
    base = (raw_frontend_url or "").strip().strip("'\"").replace("\r", "").replace("\n", "")
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=500, detail="FRONTEND_URL is invalid. Expected absolute http(s) URL.")
    return f"{base.rstrip('/')}/dashboard/integrations/oauth?{query}"


def _validate_github_settings() -> None:
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret or not settings.github_redirect_uri:
        raise HTTPException(status_code=500, detail="GitHub OAuth 설정이 누락되었습니다.")
    if not settings.github_state_secret:
        raise HTTPException(status_code=500, detail="GITHUB_STATE_SECRET 설정이 필요합니다.")


async def _github_get_user(access_token: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": settings.github_api_version,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"GitHub API 호출 실패: {response.text}")
    return response.json()


@router.post("/start")
async def github_oauth_start(request: Request):
    _validate_github_settings()
    settings = get_settings()
    user_id = await get_authenticated_user_id(request)
    state = build_state(user_id=user_id, secret=settings.github_state_secret or "")

    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": GITHUB_SCOPE,
            "state": state,
        }
    )
    auth_url = f"https://github.com/login/oauth/authorize?{query}"
    return {"ok": True, "auth_url": auth_url}


@router.get("/callback")
async def github_oauth_callback(code: str, state: str):
    _validate_github_settings()
    settings = get_settings()

    user_id = verify_state(state=state, secret=settings.github_state_secret or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"GitHub token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from GitHub")

    user = await _github_get_user(access_token)
    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(access_token)
    scope_text = str(payload.get("scope") or "").strip()
    granted_scopes = [item.strip() for item in scope_text.split(",") if item.strip()] or ["read:user", "repo"]

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "github",
            "access_token_encrypted": encrypted,
            "granted_scopes": granted_scopes,
            "workspace_id": str(user.get("id") or ""),
            "workspace_name": user.get("login") or "github",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return RedirectResponse(url=_frontend_dashboard_url(settings.frontend_url, "github=connected"), status_code=302)


@router.get("/status")
async def github_oauth_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        result = (
            supabase.table("oauth_tokens")
            .select("workspace_name, workspace_id, updated_at")
            .eq("user_id", user_id)
            .eq("provider", "github")
            .maybe_single()
            .execute()
        )
        integration = getattr(result, "data", None)
        return {"connected": bool(integration), "integration": integration}
    except Exception:
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def github_oauth_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "github")
        .execute()
    )
    return {"ok": True, "connected": False}


@router.get("/repos")
async def github_repos_list(request: Request, per_page: int = Query(5, ge=1, le=20)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    token_result = (
        supabase.table("oauth_tokens")
        .select("access_token_encrypted")
        .eq("user_id", user_id)
        .eq("provider", "github")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = token_result.data or []
    if not rows:
        raise HTTPException(status_code=400, detail="GitHub가 연결되어 있지 않습니다. 먼저 연동을 완료해주세요.")
    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail="저장된 GitHub 토큰을 찾을 수 없습니다.")
    token = TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": settings.github_api_version,
            },
            params={"per_page": per_page, "sort": "updated"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="GitHub 저장소 목록 조회에 실패했습니다. 연결을 다시 시도해주세요.")
    items = response.json()
    repos = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "full_name": item.get("full_name"),
            "private": item.get("private"),
            "html_url": item.get("html_url"),
        }
        for item in items
        if isinstance(item, dict)
    ]
    return {"ok": True, "count": len(repos), "repos": repos}
