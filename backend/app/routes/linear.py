from __future__ import annotations

import logging
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

router = APIRouter(prefix="/api/oauth/linear", tags=["linear-oauth"])
logger = logging.getLogger(__name__)

LINEAR_SCOPE = "read write"


def _validate_linear_settings() -> None:
    settings = get_settings()
    if not settings.linear_client_id or not settings.linear_client_secret or not settings.linear_redirect_uri:
        raise HTTPException(status_code=500, detail="Linear OAuth 설정이 누락되었습니다.")
    if not settings.linear_state_secret:
        raise HTTPException(status_code=500, detail="LINEAR_STATE_SECRET 설정이 필요합니다.")


async def _linear_graphql(token: str, query: str, variables: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables or {}},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Linear API 호출 실패: {response.text}")
    payload = response.json()
    if payload.get("errors"):
        raise HTTPException(status_code=400, detail=f"Linear GraphQL 오류: {payload['errors']}")
    return payload.get("data") or {}


@router.post("/start")
async def linear_oauth_start(request: Request):
    _validate_linear_settings()
    settings = get_settings()
    user_id = await get_authenticated_user_id(request)
    state = build_state(user_id=user_id, secret=settings.linear_state_secret or "")

    query = urlencode(
        {
            "client_id": settings.linear_client_id,
            "redirect_uri": settings.linear_redirect_uri,
            "response_type": "code",
            "scope": LINEAR_SCOPE,
            "state": state,
            "prompt": "consent",
        }
    )
    auth_url = f"https://linear.app/oauth/authorize?{query}"
    return {"ok": True, "auth_url": auth_url}


@router.get("/callback")
async def linear_oauth_callback(code: str, state: str):
    _validate_linear_settings()
    settings = get_settings()

    user_id = verify_state(state=state, secret=settings.linear_state_secret or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.linear.app/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.linear_redirect_uri,
                "client_id": settings.linear_client_id,
                "client_secret": settings.linear_client_secret,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Linear token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Linear")

    viewer_query = """
    query Viewer {
      viewer {
        id
        name
      }
    }
    """
    viewer_name = "linear"
    viewer_id = None
    try:
        viewer_data = await _linear_graphql(access_token, viewer_query)
        viewer = (viewer_data or {}).get("viewer") or {}
        viewer_name = viewer.get("name") or "linear"
        viewer_id = viewer.get("id")
    except Exception:
        logger.warning("linear viewer query failed during oauth callback")

    encrypted = TokenVault(settings.notion_token_encryption_key).encrypt(access_token)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    supabase.table("oauth_tokens").upsert(
        {
            "user_id": user_id,
            "provider": "linear",
            "access_token_encrypted": encrypted,
            "workspace_id": viewer_id,
            "workspace_name": viewer_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,provider",
    ).execute()

    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?linear=connected", status_code=302)


@router.get("/status")
async def linear_oauth_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        result = (
            supabase.table("oauth_tokens")
            .select("workspace_name, workspace_id, updated_at")
            .eq("user_id", user_id)
            .eq("provider", "linear")
            .maybe_single()
            .execute()
        )
        return {"connected": bool(result.data), "integration": result.data}
    except Exception as exc:
        logger.exception("linear status query failed: %s", exc)
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def linear_oauth_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "linear")
        .execute()
    )
    return {"ok": True, "connected": False}


@router.get("/issues")
async def linear_issues_list(request: Request, first: int = Query(5, ge=1, le=20)):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    token_result = (
        supabase.table("oauth_tokens")
        .select("access_token_encrypted")
        .eq("user_id", user_id)
        .eq("provider", "linear")
        .limit(1)
        .execute()
    )
    rows = token_result.data or []
    if not rows:
        raise HTTPException(status_code=400, detail="Linear가 연결되어 있지 않습니다. 먼저 연동을 완료해주세요.")
    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail="저장된 Linear 토큰을 찾을 수 없습니다.")
    token = TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)

    query = """
    query Issues($first: Int!) {
      issues(first: $first, orderBy: updatedAt) {
        nodes {
          id
          identifier
          title
          url
          state {
            name
          }
        }
      }
    }
    """
    data = await _linear_graphql(token, query, {"first": first})
    nodes = (((data or {}).get("issues") or {}).get("nodes")) or []
    issues = [
        {
            "id": node.get("id"),
            "identifier": node.get("identifier"),
            "title": node.get("title"),
            "url": node.get("url"),
            "state": ((node.get("state") or {}).get("name")),
        }
        for node in nodes
    ]
    return {"ok": True, "count": len(issues), "issues": issues}

