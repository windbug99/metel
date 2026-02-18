import logging
import base64
import hashlib
import hmac
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


def _require_telegram_settings():
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="서버에 TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
    if not settings.telegram_link_secret:
        raise HTTPException(status_code=503, detail="서버에 TELEGRAM_LINK_SECRET이 설정되지 않았습니다.")
    return settings


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode_no_pad(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def _build_telegram_start_token(user_id: str, secret: str, ttl_seconds: int = 1800) -> str:
    uid = uuid.UUID(user_id)
    uid_part = _b64url_no_pad(uid.bytes)
    exp_part = int(time.time()) + ttl_seconds
    exp_part_str = format(exp_part, "x")
    payload = f"{uid_part}.{exp_part_str}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()[:12]
    sig_part = _b64url_no_pad(sig)
    return f"{payload}.{sig_part}"


def _verify_telegram_start_token(token: str, secret: str) -> str | None:
    try:
        uid_part, exp_part_str, sig_part = token.split(".", 2)
        payload = f"{uid_part}.{exp_part_str}"
        expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()[:12]
        expected_sig_part = _b64url_no_pad(expected_sig)
        if not hmac.compare_digest(sig_part, expected_sig_part):
            return None

        expires_at = int(exp_part_str, 16)
        if expires_at < int(time.time()):
            return None

        uid_bytes = _b64url_decode_no_pad(uid_part)
        return str(uuid.UUID(bytes=uid_bytes))
    except Exception:
        return None


async def _telegram_api(method: str, payload: dict):
    settings = _require_telegram_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)
    if response.status_code >= 400:
        logger.warning("telegram api failed: %s %s", response.status_code, response.text)
        raise HTTPException(status_code=400, detail="Telegram API 호출에 실패했습니다.")
    data = response.json()
    if not data.get("ok"):
        logger.warning("telegram api response not ok: %s", data)
        raise HTTPException(status_code=400, detail="Telegram API 응답이 비정상입니다.")
    return data.get("result")


@router.get("/status")
async def telegram_status(request: Request):
    try:
        user_id = await get_authenticated_user_id(request)
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

        result = (
            supabase.table("users")
            .select("telegram_chat_id, telegram_username")
            .eq("id", user_id)
            .single()
            .execute()
        )

        row = result.data or {}
        return {
            "connected": bool(row.get("telegram_chat_id")),
            "telegram_chat_id": row.get("telegram_chat_id"),
            "telegram_username": row.get("telegram_username"),
        }
    except Exception as exc:
        logger.exception("telegram status query failed: %s", exc)
        return {"connected": False, "telegram_chat_id": None, "telegram_username": None}


@router.post("/connect-link")
async def telegram_connect_link(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = _require_telegram_settings()

    username = settings.telegram_bot_username
    if not username:
        me = await _telegram_api("getMe", {})
        username = me.get("username")

    if not username:
        raise HTTPException(status_code=500, detail="텔레그램 봇 username을 확인할 수 없습니다.")

    payload = _build_telegram_start_token(user_id=user_id, secret=settings.telegram_link_secret, ttl_seconds=1800)
    deep_link = f"https://t.me/{username}?start={payload}"
    return {"ok": True, "deep_link": deep_link, "expires_in_seconds": 1800}


@router.delete("/disconnect")
async def telegram_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    (
        supabase.table("users")
        .update(
            {
                "telegram_chat_id": None,
                "telegram_username": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", user_id)
        .execute()
    )

    return {"ok": True, "connected": False}


@router.post("/webhook")
async def telegram_webhook(
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = _require_telegram_settings()

    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="유효하지 않은 webhook secret입니다.")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")

    if not chat_id:
        return {"ok": True}

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    if text.startswith("/start"):
        payload = text.split(" ", 1)[1].strip() if " " in text else ""
        if not payload:
            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "metel 대시보드에서 '텔레그램 연결하기'를 눌러 연결 링크로 다시 시작해주세요.",
                },
            )
            return {"ok": True}

        user_id = _verify_telegram_start_token(payload, settings.telegram_link_secret)
        if not user_id:
            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "연결 링크가 만료되었거나 유효하지 않습니다. 대시보드에서 다시 시도해주세요.",
                },
            )
            return {"ok": True}

        (
            supabase.table("users")
            .update(
                {
                    "telegram_chat_id": chat_id,
                    "telegram_username": from_user.get("username"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", user_id)
            .execute()
        )

        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "연결이 완료되었습니다. 이제 metel 대시보드에서 상태를 확인할 수 있습니다.",
            },
        )
        return {"ok": True}

    result = (
        supabase.table("users")
        .select("id")
        .eq("telegram_chat_id", chat_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "먼저 metel 대시보드에서 텔레그램 연결을 완료해주세요.",
            },
        )
        return {"ok": True}

    await _telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": "연동 확인 완료. 다음 단계에서 AI 응답 기능을 연결합니다.",
        },
    )
    return {"ok": True}
