from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, quote_plus

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.connector_jobs import record_connector_job_run
from app.core.config import get_settings
from app.core.state import build_state, verify_state
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/oauth/canva", tags=["canva-oauth"])
CANVA_DEFAULT_OAUTH_SCOPES = ("profile:read", "design:meta:read")
CANVA_RESTRICTED_OAUTH_SCOPES = {
    "comment:read",
    "comment:write",
    "brandtemplate:meta:read",
    "brandtemplate:content:read",
}


class CanvaDesignCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    design_type: dict
    asset_id: str | None = None


class CanvaExportCreateRequest(BaseModel):
    design_id: str = Field(min_length=1)
    format: dict


class CanvaFolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_folder_id: str = Field(default="root", min_length=1, max_length=50)


class CanvaFolderMoveRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=50)
    to_folder_id: str = Field(min_length=1, max_length=50)


class CanvaAssetUrlUploadCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=2048)
    tags: list[str] | None = None


class CanvaUrlImportCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    mime_type: str | None = Field(default=None, min_length=1, max_length=100)


class CanvaResizeCreateRequest(BaseModel):
    design_id: str = Field(min_length=1, max_length=50)
    design_type: dict


class CanvaCommentThreadCreateRequest(BaseModel):
    message_plaintext: str = Field(min_length=1, max_length=2048)
    assignee_id: str | None = Field(default=None, min_length=1, max_length=100)


class CanvaCommentReplyCreateRequest(BaseModel):
    message_plaintext: str = Field(min_length=1, max_length=2048)


class CanvaBrandTemplateListQuery(BaseModel):
    query: str | None = None
    continuation: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    ownership: str | None = None
    sort_by: str | None = None
    dataset: str | None = None


def _frontend_dashboard_url(raw_frontend_url: str, query: str) -> str:
    base = (raw_frontend_url or "").strip().strip("'\"").replace("\r", "").replace("\n", "")
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=500, detail="FRONTEND_URL is invalid. Expected absolute http(s) URL.")
    return f"{base.rstrip('/')}/dashboard/integrations/oauth?{query}"


def _frontend_oauth_error_url(raw_frontend_url: str, message: str) -> str:
    normalized = str(message or "").strip() or "Canva OAuth callback is missing required parameters."
    return _frontend_dashboard_url(raw_frontend_url, f"canva=error&oauth_error={quote_plus(normalized)}")


def _validate_canva_settings() -> None:
    settings = get_settings()
    if not settings.canva_client_id or not settings.canva_client_secret or not settings.canva_redirect_uri:
        raise HTTPException(status_code=500, detail="Canva OAuth 설정이 누락되었습니다.")
    if not settings.canva_state_secret:
        raise HTTPException(status_code=500, detail="CANVA_STATE_SECRET 설정이 필요합니다.")


def _token_vault() -> TokenVault:
    settings = get_settings()
    return TokenVault(settings.canva_token_encryption_key or settings.notion_token_encryption_key)


def _normalize_scope_text(raw_scope_text: str | None, fallback_scope_text: str) -> list[str]:
    items = [item.strip() for item in str(raw_scope_text or "").split(" ") if item.strip()]
    if items:
        return items
    return [item.strip() for item in fallback_scope_text.split(" ") if item.strip()]


def _canva_requested_scope_text() -> str:
    # Canva OAuth connect should stay on the minimum stable scope set.
    # Advanced scopes are gated per feature because some clients are not
    # entitled to request them at auth time, which causes the whole connect
    # flow to fail with "Requested scopes are not allowed for this client."
    return " ".join(CANVA_DEFAULT_OAUTH_SCOPES)


def _match_canva_folder_item(item: dict, query: str) -> bool:
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return True
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "folder" and isinstance(item.get("folder"), dict):
        label = str(item["folder"].get("name") or "").strip().lower()
    elif item_type == "design" and isinstance(item.get("design"), dict):
        label = str(item["design"].get("title") or "").strip().lower()
    elif item_type == "image" and isinstance(item.get("image"), dict):
        label = str(item["image"].get("name") or "").strip().lower()
    else:
        label = ""
    return normalized_query in label


def _granted_scope_set(row: dict | None) -> set[str]:
    raw = row.get("granted_scopes") if isinstance(row, dict) else None
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(" ") if item.strip()}
    return set()


async def _require_canva_token_row(user_id: str) -> tuple[str, dict]:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    row = _load_canva_oauth_row(supabase=supabase, user_id=user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Canva가 연결되어 있지 않습니다. 먼저 연동을 완료해주세요.")
    row = await _refresh_canva_access_token_if_needed(supabase=supabase, row=row)
    encrypted = str((row or {}).get("access_token_encrypted") or "").strip()
    if not encrypted:
        raise HTTPException(status_code=500, detail="저장된 Canva 토큰을 찾을 수 없습니다.")
    return _token_vault().decrypt(encrypted), row


async def _require_canva_scopes(user_id: str, required_scopes: set[str]) -> str:
    access_token, row = await _require_canva_token_row(user_id)
    granted = _granted_scope_set(row)
    missing = sorted(scope for scope in required_scopes if scope not in granted)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "Canva client does not currently grant the required scopes for this feature. "
                f"Missing scopes: {', '.join(missing)}"
            ),
        )
    return access_token


def _build_pkce_verifier() -> str:
    # RFC 7636 permits 43-128 chars; token_urlsafe(72) stays within the bound.
    return secrets.token_urlsafe(72)[:96]


def _build_pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _consume_pkce_verifier(*, supabase, state: str) -> str | None:
    rows = (
        supabase.table("oauth_pending_states")
        .select("state,code_verifier,expires_at")
        .eq("state", state)
        .eq("provider", "canva")
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    expires_at_raw = row.get("expires_at")
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
        except ValueError:
            expires_at = None
        if expires_at and expires_at < datetime.now(timezone.utc):
            (
                supabase.table("oauth_pending_states")
                .delete()
                .eq("state", state)
                .execute()
            )
            return None
    (
        supabase.table("oauth_pending_states")
        .delete()
        .eq("state", state)
        .execute()
    )
    code_verifier = str(row.get("code_verifier") or "").strip()
    return code_verifier or None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_expired(value: str | None) -> bool:
    expires_at = _parse_iso_datetime(value)
    if not expires_at:
        return False
    return expires_at <= datetime.now(timezone.utc)


async def _canva_api_get(access_token: str, path: str) -> dict:
    payload = await _canva_api_request("GET", path, access_token=access_token)
    return payload if isinstance(payload, dict) else {}


async def _canva_api_request(method: str, path: str, *, access_token: str, params: dict | None = None, json_body: dict | None = None) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(
            method.upper(),
            f"{settings.canva_api_base_url.rstrip('/')}{path}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if json_body is not None else {}),
            },
            params=params,
            json=json_body,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Canva API 호출 실패: {response.text}")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def _fetch_canva_identity(access_token: str) -> tuple[dict, dict | None, dict | None]:
    me_payload = await _canva_api_get(access_token, "/users/me")
    profile_payload: dict | None = None
    capabilities_payload: dict | None = None
    try:
        profile_payload = await _canva_api_get(access_token, "/users/me/profile")
    except HTTPException:
        profile_payload = None
    try:
        capabilities_payload = await _canva_api_get(access_token, "/users/me/capabilities")
    except HTTPException:
        capabilities_payload = None
    return me_payload, profile_payload, capabilities_payload


def _extract_identity_fields(me_payload: dict, profile_payload: dict | None, capabilities_payload: dict | None) -> tuple[str | None, str | None, str | None, dict]:
    me = me_payload.get("user") if isinstance(me_payload.get("user"), dict) else me_payload
    profile = profile_payload.get("profile") if isinstance(profile_payload and profile_payload.get("profile"), dict) else profile_payload
    capabilities = capabilities_payload.get("capabilities") if isinstance(capabilities_payload and capabilities_payload.get("capabilities"), dict) else capabilities_payload

    user_id = str((me or {}).get("user_id") or (me or {}).get("id") or "").strip() or None
    team_id = str((me or {}).get("team_id") or (me or {}).get("team", {}).get("id") or "").strip() or None
    workspace_name = str((profile or {}).get("display_name") or (profile or {}).get("name") or "canva").strip() or "canva"

    provider_metadata = {
        "me": me_payload or {},
        "profile": profile_payload or {},
        "capabilities": capabilities or capabilities_payload or {},
    }
    return user_id, team_id, workspace_name, provider_metadata


def _load_canva_oauth_row(*, supabase, user_id: str) -> dict | None:
    result = (
        supabase.table("oauth_tokens")
        .select(
            "user_id,provider,access_token_encrypted,refresh_token_encrypted,token_expires_at,granted_scopes,"
            "workspace_id,workspace_name,provider_account_id,provider_team_id,provider_metadata,updated_at"
        )
        .eq("user_id", user_id)
        .eq("provider", "canva")
        .maybe_single()
        .execute()
    )
    data = getattr(result, "data", None)
    return data if isinstance(data, dict) else None


async def _refresh_canva_access_token_if_needed(*, supabase, row: dict | None) -> dict | None:
    if not row:
        return None
    if not _is_expired(row.get("token_expires_at")):
        return row

    refresh_token_encrypted = str(row.get("refresh_token_encrypted") or "").strip()
    if not refresh_token_encrypted:
        return row

    settings = get_settings()
    vault = _token_vault()
    refresh_token = vault.decrypt(refresh_token_encrypted)
    if not refresh_token:
        return row

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{settings.canva_api_base_url.rstrip('/')}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.canva_client_id,
                "client_secret": settings.canva_client_secret,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Canva token refresh failed: {response.text}")

    payload = response.json()
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Canva refresh")

    next_refresh_token = str(payload.get("refresh_token") or "").strip()
    now = datetime.now(timezone.utc)
    expires_in = int(payload.get("expires_in") or 0)
    updated_row = {
        **row,
        "access_token_encrypted": vault.encrypt(access_token),
        "refresh_token_encrypted": vault.encrypt(next_refresh_token) if next_refresh_token else refresh_token_encrypted,
        "token_expires_at": (now + timedelta(seconds=max(expires_in - 60, 0))).isoformat() if expires_in else None,
        "granted_scopes": _normalize_scope_text(payload.get("scope"), _canva_requested_scope_text()),
        "updated_at": now.isoformat(),
    }
    supabase.table("oauth_tokens").upsert(updated_row, on_conflict="user_id,provider").execute()
    return updated_row


def _serialize_canva_integration(row: dict | None) -> dict | None:
    if not isinstance(row, dict):
        return None
    return {
        "workspace_name": row.get("workspace_name"),
        "workspace_id": row.get("workspace_id"),
        "provider_team_id": row.get("provider_team_id"),
        "token_expires_at": row.get("token_expires_at"),
        "updated_at": row.get("updated_at"),
        "provider_metadata": row.get("provider_metadata"),
    }


async def _require_canva_access_token(user_id: str) -> str:
    access_token, _row = await _require_canva_token_row(user_id)
    return access_token


async def load_canva_access_token_for_user(user_id: str) -> str:
    return await _require_canva_access_token(user_id)


@router.post("/start")
async def canva_oauth_start(request: Request):
    _validate_canva_settings()
    settings = get_settings()
    user_id = await get_authenticated_user_id(request)
    state = build_state(user_id=user_id, secret=settings.canva_state_secret or "")
    code_verifier = _build_pkce_verifier()
    code_challenge = _build_pkce_challenge(code_verifier)
    now = datetime.now(timezone.utc)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_pending_states")
        .upsert(
            {
                "state": state,
                "user_id": user_id,
                "provider": "canva",
                "code_verifier": code_verifier,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
            },
            on_conflict="state",
        )
        .execute()
    )

    query = urlencode(
        {
            "client_id": settings.canva_client_id,
            "redirect_uri": settings.canva_redirect_uri,
            "response_type": "code",
            "scope": _canva_requested_scope_text(),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{settings.canva_oauth_authorize_url.rstrip('/')}?{query}"
    return {"ok": True, "auth_url": auth_url}


@router.get("/callback")
async def canva_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    _validate_canva_settings()
    settings = get_settings()

    if error:
        detail = str(error_description or error).strip() or "Canva OAuth authorization failed."
        return RedirectResponse(
            url=_frontend_oauth_error_url(settings.frontend_url, detail),
            status_code=302,
        )

    normalized_code = str(code or "").strip()
    normalized_state = str(state or "").strip()
    if not normalized_code or not normalized_state:
        return RedirectResponse(
            url=_frontend_oauth_error_url(
                settings.frontend_url,
                "Canva OAuth callback is missing required code/state parameters. Verify the authorized redirect URI in Canva Developer Portal.",
            ),
            status_code=302,
        )

    user_id = verify_state(state=normalized_state, secret=settings.canva_state_secret or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    code_verifier = _consume_pkce_verifier(supabase=supabase, state=normalized_state)
    if not code_verifier:
        existing = (
            supabase.table("oauth_tokens")
            .select("provider,updated_at")
            .eq("user_id", user_id)
            .eq("provider", "canva")
            .maybe_single()
            .execute()
        )
        if getattr(existing, "data", None):
            return RedirectResponse(
                url=_frontend_dashboard_url(settings.frontend_url, "canva=connected&oauth_notice=duplicate_callback"),
                status_code=302,
            )
        raise HTTPException(status_code=400, detail="Canva PKCE verifier를 찾을 수 없습니다. 연결을 다시 시도해주세요.")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{settings.canva_api_base_url.rstrip('/')}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": normalized_code,
                "redirect_uri": settings.canva_redirect_uri,
                "client_id": settings.canva_client_id,
                "client_secret": settings.canva_client_secret,
                "code_verifier": code_verifier,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Canva token exchange failed: {response.text}")

    payload = response.json()
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token from Canva")

    me_payload, profile_payload, capabilities_payload = await _fetch_canva_identity(access_token)
    provider_account_id, provider_team_id, workspace_name, provider_metadata = _extract_identity_fields(
        me_payload,
        profile_payload,
        capabilities_payload,
    )

    now = datetime.now(timezone.utc)
    expires_in = int(payload.get("expires_in") or 0)
    token_expires_at = (now + timedelta(seconds=max(expires_in - 60, 0))).isoformat() if expires_in else None
    scope_text = str(payload.get("scope") or "").strip()
    vault = _token_vault()
    upsert_payload = {
        "user_id": user_id,
        "provider": "canva",
        "access_token_encrypted": vault.encrypt(access_token),
        "refresh_token_encrypted": vault.encrypt(refresh_token) if refresh_token else None,
        "token_expires_at": token_expires_at,
        "granted_scopes": _normalize_scope_text(scope_text, _canva_requested_scope_text()),
        "workspace_id": provider_account_id,
        "workspace_name": workspace_name,
        "provider_account_id": provider_account_id,
        "provider_team_id": provider_team_id,
        "provider_metadata": provider_metadata,
        "updated_at": now.isoformat(),
    }
    supabase.table("oauth_tokens").upsert(upsert_payload, on_conflict="user_id,provider").execute()

    return RedirectResponse(url=_frontend_dashboard_url(settings.frontend_url, "canva=connected"), status_code=302)


@router.get("/status")
async def canva_oauth_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        integration = _load_canva_oauth_row(supabase=supabase, user_id=user_id)
        integration = await _refresh_canva_access_token_if_needed(supabase=supabase, row=integration)
        return {"connected": bool(integration), "integration": _serialize_canva_integration(integration)}
    except Exception:
        return {"connected": False, "integration": None}


@router.delete("/disconnect")
async def canva_oauth_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    (
        supabase.table("oauth_tokens")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "canva")
        .execute()
    )
    (
        supabase.table("oauth_pending_states")
        .delete()
        .eq("user_id", user_id)
        .eq("provider", "canva")
        .execute()
    )
    return {"ok": True, "connected": False}


@router.get("/designs")
async def canva_designs_list(
    request: Request,
    query: str | None = None,
    ownership: str | None = None,
    sort_by: str | None = None,
    continuation: str | None = None,
    limit: int = 20,
):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_access_token(user_id)
    params = {"limit": min(max(limit, 1), 100)}
    if query:
        params["query"] = query
    if ownership:
        params["ownership"] = ownership
    if sort_by:
        params["sort_by"] = sort_by
    if continuation:
        params["continuation"] = continuation
    payload = await _canva_api_request("GET", "/designs", access_token=access_token, params=params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("designs")
    designs = items if isinstance(items, list) else []
    return {
        "ok": True,
        "count": len(designs),
        "designs": designs,
        "continuation": payload.get("continuation"),
    }


@router.get("/designs/{design_id}")
async def canva_design_get(request: Request, design_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_access_token(user_id)
    payload = await _canva_api_request("GET", f"/designs/{design_id}", access_token=access_token)
    return {"ok": True, "design": payload.get("design") if isinstance(payload.get("design"), dict) else payload}


@router.get("/designs/{design_id}/export-formats")
async def canva_design_export_formats(request: Request, design_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:read"})
    payload = await _canva_api_request("GET", f"/designs/{design_id}/export-formats", access_token=access_token)
    formats = payload.get("formats") if isinstance(payload.get("formats"), list) else []
    return {"ok": True, "count": len(formats), "formats": formats}


@router.get("/folders/{folder_id}/items")
async def canva_folder_items_list(
    request: Request,
    folder_id: str,
    continuation: str | None = None,
    limit: int = 50,
    item_types: str | None = None,
    sort_by: str | None = None,
    pin_status: str | None = None,
):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"folder:read"})
    params = {"limit": min(max(limit, 1), 100)}
    if continuation:
        params["continuation"] = continuation
    if item_types:
        params["item_types"] = item_types
    if sort_by:
        params["sort_by"] = sort_by
    if pin_status:
        params["pin_status"] = pin_status
    payload = await _canva_api_request("GET", f"/folders/{folder_id}/items", access_token=access_token, params=params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return {"ok": True, "count": len(items), "items": items, "continuation": payload.get("continuation")}


@router.get("/folders/search")
async def canva_folder_search(
    request: Request,
    query: str | None = None,
    folder_id: str = "root",
    continuation: str | None = None,
    limit: int = 50,
    sort_by: str | None = None,
):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"folder:read"})
    params = {
        "limit": min(max(limit, 1), 100),
        "item_types": "folder",
    }
    if continuation:
        params["continuation"] = continuation
    if sort_by:
        params["sort_by"] = sort_by
    payload = await _canva_api_request("GET", f"/folders/{folder_id}/items", access_token=access_token, params=params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    matched = [item for item in items if isinstance(item, dict) and _match_canva_folder_item(item, query or "")]
    return {"ok": True, "count": len(matched), "items": matched, "continuation": payload.get("continuation")}


@router.post("/folders")
async def canva_folder_create(request: Request, body: CanvaFolderCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"folder:write"})
    json_body = {
        "name": body.name,
        "parent_folder_id": body.parent_folder_id,
    }
    payload = await _canva_api_request("POST", "/folders", access_token=access_token, json_body=json_body)
    folder = payload.get("folder") if isinstance(payload.get("folder"), dict) else payload
    if isinstance(folder, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="folder_create",
            status="success",
            resource_id=str(folder.get("id") or "").strip() or None,
            resource_title=str(folder.get("name") or body.name or "").strip() or None,
            request_payload=json_body,
            result_payload=folder,
        )
    return {"ok": True, "folder": folder}


@router.post("/folders/move")
async def canva_folder_move(request: Request, body: CanvaFolderMoveRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"folder:write"})
    json_body = {
        "item_id": body.item_id,
        "to_folder_id": body.to_folder_id,
    }
    payload = await _canva_api_request("POST", "/folders/move", access_token=access_token, json_body=json_body)
    record_connector_job_run(
        user_id=user_id,
        provider="canva",
        job_type="folder_move",
        status="success",
        resource_id=body.item_id,
        request_payload=json_body,
        result_payload=payload if isinstance(payload, dict) else None,
    )
    return {"ok": True, "result": payload if isinstance(payload, dict) else {}}


@router.get("/assets/{asset_id}")
async def canva_asset_get(request: Request, asset_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"asset:read"})
    payload = await _canva_api_request("GET", f"/assets/{asset_id}", access_token=access_token)
    return {"ok": True, "asset": payload.get("asset") if isinstance(payload.get("asset"), dict) else payload}


@router.post("/url-asset-uploads")
async def canva_url_asset_upload_create(request: Request, body: CanvaAssetUrlUploadCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"asset:write"})
    json_body = {
        "name": body.name,
        "url": body.url,
        **({"tags": body.tags} if body.tags else {}),
    }
    payload = await _canva_api_request("POST", "/url-asset-uploads", access_token=access_token, json_body=json_body)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="asset_url_upload",
            external_job_id=str(job.get("id") or "").strip() or None,
            resource_title=body.name,
            status=str(job.get("status") or "in_progress").strip().lower() or "in_progress",
            request_payload=json_body,
            result_payload=job,
        )
    return {"ok": True, "job": job}


@router.get("/url-asset-uploads/{job_id}")
async def canva_url_asset_upload_get(request: Request, job_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"asset:read"})
    payload = await _canva_api_request("GET", f"/url-asset-uploads/{job_id}", access_token=access_token)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        asset_id = str((job.get("asset") or {}).get("id") or job.get("asset_id") or "").strip() or None
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="asset_url_upload",
            external_job_id=job_id,
            resource_id=asset_id,
            status=str(job.get("status") or "unknown").strip().lower() or "unknown",
            result_payload=job,
            error_message=str(job.get("error") or "").strip() or None,
        )
    return {"ok": True, "job": job}


@router.post("/url-imports")
async def canva_url_import_create(request: Request, body: CanvaUrlImportCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:write"})
    json_body = {
        "title": body.title,
        "url": body.url,
        **({"mime_type": body.mime_type} if body.mime_type else {}),
    }
    payload = await _canva_api_request("POST", "/url-imports", access_token=access_token, json_body=json_body)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="url_import",
            external_job_id=str(job.get("id") or "").strip() or None,
            resource_title=body.title,
            status=str(job.get("status") or "in_progress").strip().lower() or "in_progress",
            request_payload=json_body,
            result_payload=job,
        )
    return {"ok": True, "job": job}


@router.get("/url-imports/{job_id}")
async def canva_url_import_get(request: Request, job_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:meta:read"})
    payload = await _canva_api_request("GET", f"/url-imports/{job_id}", access_token=access_token)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        design_id = str((job.get("design") or {}).get("id") or job.get("design_id") or "").strip() or None
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="url_import",
            external_job_id=job_id,
            resource_id=design_id,
            status=str(job.get("status") or "unknown").strip().lower() or "unknown",
            result_payload=job,
            error_message=str(job.get("error") or "").strip() or None,
        )
    return {"ok": True, "job": job}


@router.post("/resizes")
async def canva_resize_create(request: Request, body: CanvaResizeCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:read", "design:content:write"})
    json_body = {
        "design_id": body.design_id,
        "design_type": body.design_type,
    }
    payload = await _canva_api_request("POST", "/resizes", access_token=access_token, json_body=json_body)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="resize_create",
            external_job_id=str(job.get("id") or "").strip() or None,
            resource_id=body.design_id,
            status=str(job.get("status") or "in_progress").strip().lower() or "in_progress",
            request_payload=json_body,
            result_payload=job,
        )
    return {"ok": True, "job": job}


@router.get("/resizes/{job_id}")
async def canva_resize_get(request: Request, job_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:read"})
    payload = await _canva_api_request("GET", f"/resizes/{job_id}", access_token=access_token)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        resized_design_id = str((job.get("design") or {}).get("id") or job.get("design_id") or "").strip() or None
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="resize_create",
            external_job_id=job_id,
            resource_id=resized_design_id,
            status=str(job.get("status") or "unknown").strip().lower() or "unknown",
            result_payload=job,
            error_message=str(job.get("error") or "").strip() or None,
        )
    return {"ok": True, "job": job}


@router.post("/designs/{design_id}/comments")
async def canva_comment_thread_create(request: Request, design_id: str, body: CanvaCommentThreadCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"comment:write"})
    json_body = {
        "message_plaintext": body.message_plaintext,
        **({"assignee_id": body.assignee_id} if body.assignee_id else {}),
    }
    payload = await _canva_api_request("POST", f"/designs/{design_id}/comments", access_token=access_token, json_body=json_body)
    thread = payload.get("thread") if isinstance(payload.get("thread"), dict) else payload
    if isinstance(thread, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="comment_thread_create",
            status="success",
            resource_id=str(thread.get("id") or "").strip() or None,
            request_payload={"design_id": design_id, **json_body},
            result_payload=thread,
        )
    return {"ok": True, "thread": thread}


@router.get("/designs/{design_id}/comments/{thread_id}")
async def canva_comment_thread_get(request: Request, design_id: str, thread_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"comment:read"})
    payload = await _canva_api_request("GET", f"/designs/{design_id}/comments/{thread_id}", access_token=access_token)
    return {"ok": True, "thread": payload.get("thread") if isinstance(payload.get("thread"), dict) else payload}


@router.post("/designs/{design_id}/comments/{thread_id}/replies")
async def canva_comment_reply_create(request: Request, design_id: str, thread_id: str, body: CanvaCommentReplyCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"comment:write"})
    json_body = {"message_plaintext": body.message_plaintext}
    payload = await _canva_api_request(
        "POST",
        f"/designs/{design_id}/comments/{thread_id}/replies",
        access_token=access_token,
        json_body=json_body,
    )
    reply = payload.get("reply") if isinstance(payload.get("reply"), dict) else payload
    if isinstance(reply, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="comment_reply_create",
            status="success",
            resource_id=str(reply.get("id") or "").strip() or None,
            request_payload={"design_id": design_id, "thread_id": thread_id, **json_body},
            result_payload=reply,
        )
    return {"ok": True, "reply": reply}


@router.get("/designs/{design_id}/comments/{thread_id}/replies")
async def canva_comment_replies_list(request: Request, design_id: str, thread_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"comment:read"})
    payload = await _canva_api_request("GET", f"/designs/{design_id}/comments/{thread_id}/replies", access_token=access_token)
    replies = payload.get("replies") if isinstance(payload.get("replies"), list) else []
    return {"ok": True, "count": len(replies), "replies": replies}


@router.get("/brand-templates")
async def canva_brand_templates_list(
    request: Request,
    query: str | None = None,
    continuation: str | None = None,
    limit: int = 25,
    ownership: str | None = None,
    sort_by: str | None = None,
    dataset: str | None = None,
):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"brandtemplate:meta:read"})
    params = {"limit": min(max(limit, 1), 100)}
    if query:
        params["query"] = query
    if continuation:
        params["continuation"] = continuation
    if ownership:
        params["ownership"] = ownership
    if sort_by:
        params["sort_by"] = sort_by
    if dataset:
        params["dataset"] = dataset
    payload = await _canva_api_request("GET", "/brand-templates", access_token=access_token, params=params)
    items = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("brand_templates")
    templates = items if isinstance(items, list) else []
    return {"ok": True, "count": len(templates), "brand_templates": templates, "continuation": payload.get("continuation")}


@router.get("/brand-templates/{brand_template_id}")
async def canva_brand_template_get(request: Request, brand_template_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"brandtemplate:meta:read"})
    payload = await _canva_api_request("GET", f"/brand-templates/{brand_template_id}", access_token=access_token)
    return {"ok": True, "brand_template": payload.get("brand_template") if isinstance(payload.get("brand_template"), dict) else payload}


@router.get("/brand-templates/{brand_template_id}/dataset")
async def canva_brand_template_dataset_get(request: Request, brand_template_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"brandtemplate:content:read"})
    payload = await _canva_api_request("GET", f"/brand-templates/{brand_template_id}/dataset", access_token=access_token)
    return {"ok": True, "dataset": payload.get("dataset") if isinstance(payload.get("dataset"), dict) else payload}


@router.post("/designs")
async def canva_design_create(request: Request, body: CanvaDesignCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:write"})
    json_body = {
        "design_type": body.design_type,
        **({"title": body.title} if body.title else {}),
        **({"asset_id": body.asset_id} if body.asset_id else {}),
    }
    payload = await _canva_api_request("POST", "/designs", access_token=access_token, json_body=json_body)
    design = payload.get("design") if isinstance(payload.get("design"), dict) else payload
    if isinstance(design, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="design_create",
            status="success",
            resource_id=str(design.get("id") or "").strip() or None,
            resource_title=str(design.get("title") or body.title or "").strip() or None,
            request_payload=json_body,
            result_payload=design,
        )
    return {"ok": True, "design": design}


@router.post("/exports")
async def canva_export_create(request: Request, body: CanvaExportCreateRequest):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:read"})
    payload = await _canva_api_request(
        "POST",
        "/exports",
        access_token=access_token,
        json_body={"design_id": body.design_id, "format": body.format},
    )
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="export_create",
            external_job_id=str(job.get("id") or "").strip() or None,
            resource_id=body.design_id,
            status=str(job.get("status") or "in_progress").strip().lower() or "in_progress",
            request_payload={"design_id": body.design_id, "format": body.format},
            result_payload=job,
            download_urls=job.get("urls") if isinstance(job.get("urls"), list) else None,
        )
    return {"ok": True, "job": job}


@router.get("/exports/{export_id}")
async def canva_export_get(request: Request, export_id: str):
    user_id = await get_authenticated_user_id(request)
    access_token = await _require_canva_scopes(user_id, {"design:content:read"})
    payload = await _canva_api_request("GET", f"/exports/{export_id}", access_token=access_token)
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if isinstance(job, dict):
        record_connector_job_run(
            user_id=user_id,
            provider="canva",
            job_type="export_create",
            external_job_id=export_id,
            status=str(job.get("status") or "unknown").strip().lower() or "unknown",
            result_payload=job,
            download_urls=job.get("urls") if isinstance(job.get("urls"), list) else None,
            error_message=str(job.get("error") or "").strip() or None,
        )
    return {"ok": True, "job": job}
