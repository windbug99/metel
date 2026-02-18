import logging
from urllib.parse import urlencode
from datetime import datetime, timezone
from json import JSONDecodeError

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from supabase import create_client

from app.core.config import get_settings
from app.core.state import build_state, verify_state
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/notion", tags=["notion-oauth"])
logger = logging.getLogger(__name__)


def _extract_page_title(page: dict) -> str:
    properties = page.get("properties", {})
    for value in properties.values():
        if value.get("type") == "title":
            chunks = value.get("title", [])
            text = "".join(chunk.get("plain_text", "") for chunk in chunks).strip()
            if text:
                return text
    return "(제목 없음)"


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
    except Exception as exc:
        logger.exception("notion status query failed: %s", exc)
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


@router.get("/pages")
async def notion_pages_list(user_id: str = Query(..., min_length=10), page_size: int = Query(5, ge=1, le=20)):
    try:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

        token_result = (
            supabase.table("oauth_tokens")
            .select("access_token_encrypted")
            .eq("user_id", user_id)
            .eq("provider", "notion")
            .limit(1)
            .execute()
        )

        rows = token_result.data or []
        if not rows:
            raise HTTPException(status_code=400, detail="Notion이 연결되어 있지 않습니다. 먼저 연동을 완료해주세요.")

        encrypted = rows[0].get("access_token_encrypted")
        if not encrypted:
            raise HTTPException(status_code=500, detail="저장된 Notion 토큰을 찾을 수 없습니다.")

        try:
            token = TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)
        except Exception as exc:
            logger.exception("failed to decrypt notion token: %s", exc)
            raise HTTPException(status_code=500, detail="Notion 인증 정보를 복호화하지 못했습니다.") from exc

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.notion.com/v1/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={
                    "filter": {"property": "object", "value": "page"},
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                    "page_size": page_size,
                },
            )

        if response.status_code >= 400:
            logger.warning("notion pages API failed: %s %s", response.status_code, response.text)
            raise HTTPException(
                status_code=400,
                detail="Notion 페이지 목록 조회에 실패했습니다. 연결을 해제 후 다시 연동해주세요.",
            )

        try:
            payload = response.json()
        except JSONDecodeError as exc:
            logger.exception("notion pages response parse failed: %s", exc)
            raise HTTPException(status_code=502, detail="Notion 응답 파싱에 실패했습니다.") from exc

        pages = payload.get("results", [])
        normalized = [
            {
                "id": page.get("id"),
                "title": _extract_page_title(page),
                "url": page.get("url"),
                "last_edited_time": page.get("last_edited_time"),
            }
            for page in pages
        ]

        return {"ok": True, "count": len(normalized), "pages": normalized}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("notion pages endpoint failed: %s", exc)
        raise HTTPException(status_code=500, detail="Notion 페이지 조회 처리 중 오류가 발생했습니다.") from exc
