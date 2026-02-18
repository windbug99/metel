import logging
import base64
import hashlib
import hmac
import re
import time
import uuid
from json import JSONDecodeError
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from supabase import create_client

from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.security.token_vault import TokenVault

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
    exp_part_str = format(exp_part, "08x")
    payload = f"{uid_part}{exp_part_str}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()[:12]
    sig_part = _b64url_no_pad(sig)
    return f"{payload}{sig_part}"


def _verify_telegram_start_token(token: str, secret: str) -> str | None:
    try:
        # Telegram deep-link payload: 1-64 chars, only A-Z a-z 0-9 _ -
        # token format (46 chars): [uid:22][exp_hex:8][sig:16]
        if len(token) != 46:
            return None
        uid_part = token[:22]
        exp_part_str = token[22:30]
        sig_part = token[30:]
        payload = f"{uid_part}{exp_part_str}"
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


def _extract_page_title(page: dict) -> str:
    properties = page.get("properties", {})
    for value in properties.values():
        if value.get("type") == "title":
            chunks = value.get("title", [])
            text = "".join(chunk.get("plain_text", "") for chunk in chunks).strip()
            if text:
                return text
    return "(제목 없음)"


async def _fetch_notion_pages_for_user(user_id: str, page_size: int = 5) -> list[dict]:
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
        raise HTTPException(status_code=400, detail="notion_not_connected")

    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail="notion_token_missing")

    token = TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)

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
        logger.warning("telegram notion pages API failed: %s %s", response.status_code, response.text)
        raise HTTPException(status_code=400, detail="notion_api_failed")

    try:
        payload = response.json()
    except JSONDecodeError as exc:
        logger.exception("telegram notion pages parse failed: %s", exc)
        raise HTTPException(status_code=502, detail="notion_parse_failed") from exc

    pages = payload.get("results", [])
    return [
        {
            "id": page.get("id"),
            "title": _extract_page_title(page),
            "url": page.get("url"),
            "last_edited_time": page.get("last_edited_time"),
        }
        for page in pages
    ]


def _load_notion_access_token_for_user(user_id: str) -> str:
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
        raise HTTPException(status_code=400, detail="notion_not_connected")

    encrypted = rows[0].get("access_token_encrypted")
    if not encrypted:
        raise HTTPException(status_code=500, detail="notion_token_missing")

    return TokenVault(settings.notion_token_encryption_key).decrypt(encrypted)


async def _create_notion_page_for_user(user_id: str, title: str) -> dict:
    token = _load_notion_access_token_for_user(user_id)
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "parent": {"workspace": True},
                "properties": {
                    "title": {
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": title},
                            }
                        ]
                    }
                },
            },
        )

    if response.status_code >= 400:
        logger.warning("telegram notion create API failed: %s %s", response.status_code, response.text)
        raise HTTPException(status_code=400, detail="notion_create_failed")

    try:
        payload = response.json()
    except JSONDecodeError as exc:
        logger.exception("telegram notion create parse failed: %s", exc)
        raise HTTPException(status_code=502, detail="notion_parse_failed") from exc

    return {
        "id": payload.get("id"),
        "url": payload.get("url"),
        "title": title,
    }


def _disconnect_telegram_user(user_id: str):
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


def _load_linked_user_by_chat_id(chat_id: int):
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("users")
        .select("id, telegram_username")
        .eq("telegram_chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    return result.data


def _is_notion_connected(user_id: str) -> bool:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("id")
        .eq("user_id", user_id)
        .eq("provider", "notion")
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _map_natural_text_to_command(text: str) -> tuple[str, str]:
    raw = text.strip()
    lower = raw.lower()
    list_keywords = ["목록", "리스트", "최근", "조회", "보여", "불러", "확인"]
    create_keywords = ["만들", "생성", "create", "추가", "작성"]
    notion_keywords = ["notion", "노션"]
    page_keywords = ["페이지", "문서"]

    if any(keyword in lower for keyword in ["도움말", "help", "메뉴", "menu", "명령어"]):
        return "/help", ""

    if any(keyword in lower for keyword in ["상태", "status", "연결상태"]):
        return "/status", ""

    # 생성 의도는 목록보다 먼저 매칭해야 오탐이 줄어듭니다.
    if any(keyword in lower for keyword in create_keywords) and (
        any(keyword in lower for keyword in page_keywords) or any(keyword in lower for keyword in notion_keywords)
    ):
        title = raw
        patterns = [
            r"(?i)^\s*(notion|노션)\s*(페이지|문서)?\s*(만들어줘|만들어|생성해줘|생성|추가해줘|작성해줘|create)\s*",
            r"(?i)^\s*(페이지|문서)\s*(만들어줘|만들어|생성해줘|생성|추가해줘|작성해줘)\s*",
            r"(?i)^\s*(create)\s*",
        ]
        for pattern in patterns:
            title = re.sub(pattern, "", title).strip(" :")
        # 조사/접속어 등 불필요한 앞부분 제거
        title = re.sub(r"^(으로|로|에|를|을)\s*", "", title).strip()
        title = re.sub(r"\s+(만들어줘|생성해줘|작성해줘)$", "", title, flags=re.IGNORECASE).strip()
        return "/notion_create", title

    if (
        (any(keyword in lower for keyword in list_keywords) or "몇 개" in raw or "몇개" in raw)
        and (any(keyword in lower for keyword in notion_keywords) or any(keyword in lower for keyword in page_keywords))
        and not any(keyword in lower for keyword in create_keywords)
    ):
        count_match = re.search(r"(\d{1,2})\s*(개|개만|개만요|개 보여|개 보여줘)?", raw)
        count = count_match.group(1) if count_match else ""
        return "/notion_pages", count

    return "", ""


def _record_command_log(
    *,
    user_id: str | None,
    chat_id: int | None,
    command: str,
    status: str,
    error_code: str | None = None,
    detail: str | None = None,
):
    try:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        payload = {
            "user_id": user_id,
            "channel": "telegram",
            "chat_id": chat_id,
            "command": command,
            "status": status,
            "error_code": error_code,
            "detail": detail,
        }
        supabase.table("command_logs").insert(payload).execute()
    except Exception as exc:
        logger.exception("failed to record command log: %s", exc)


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
    tg_deep_link = f"tg://resolve?domain={username}&start={payload}"
    return {
        "ok": True,
        "bot_username": username,
        "start_token": payload,
        "start_command": f"/start {payload}",
        "deep_link": deep_link,
        "tg_deep_link": tg_deep_link,
        "expires_in_seconds": 1800,
    }


@router.delete("/disconnect")
async def telegram_disconnect(request: Request):
    user_id = await get_authenticated_user_id(request)
    _disconnect_telegram_user(user_id)

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

    logger.info("telegram webhook received chat_id=%s has_text=%s", chat_id, bool(text))

    if not chat_id:
        return {"ok": True}

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    command_token, _, _ = text.partition(" ")
    normalized_command = command_token.split("@", 1)[0].strip().lower() if command_token else "(empty)"

    if text.startswith("/start"):
        payload = text.split(" ", 1)[1].strip() if " " in text else ""
        if not payload:
            _record_command_log(
                user_id=None,
                chat_id=chat_id,
                command="/start",
                status="error",
                error_code="missing_payload",
            )
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
            _record_command_log(
                user_id=None,
                chat_id=chat_id,
                command="/start",
                status="error",
                error_code="invalid_or_expired_payload",
            )
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
        _record_command_log(
            user_id=user_id,
            chat_id=chat_id,
            command="/start",
            status="success",
            detail="telegram linked",
        )

        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "연결이 완료되었습니다. 이제 metel 대시보드에서 상태를 확인할 수 있습니다.",
            },
        )
        return {"ok": True}

    result = _load_linked_user_by_chat_id(chat_id)

    if not result:
        _record_command_log(
            user_id=None,
            chat_id=chat_id,
            command=normalized_command,
            status="error",
            error_code="telegram_not_linked",
        )
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "먼저 metel 대시보드에서 텔레그램 연결을 완료해주세요.",
            },
        )
        return {"ok": True}

    user_id = result.get("id")
    command, _, rest = text.partition(" ")
    command = command.split("@", 1)[0].strip().lower()
    if not command.startswith("/"):
        mapped_command, mapped_rest = _map_natural_text_to_command(text)
        if mapped_command:
            command = mapped_command
            rest = mapped_rest

    if command in {"/status", "/my_status"}:
        notion_connected = _is_notion_connected(user_id)
        _record_command_log(
            user_id=user_id,
            chat_id=chat_id,
            command=command,
            status="success",
            detail=f"notion_connected={notion_connected}",
        )
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "현재 연동 상태입니다.\n"
                    "- Telegram: 연결됨\n"
                    f"- Notion: {'연결됨' if notion_connected else '미연결'}\n"
                    "Notion 페이지 조회: /notion_pages"
                ),
            },
        )
        return {"ok": True}

    if command in {"/disconnect", "/unlink"}:
        _disconnect_telegram_user(user_id)
        _record_command_log(
            user_id=user_id,
            chat_id=chat_id,
            command=command,
            status="success",
            detail="telegram disconnected",
        )
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "텔레그램 연동이 해제되었습니다. 다시 연결하려면 대시보드에서 Telegram 연결하기를 눌러주세요.",
            },
        )
        return {"ok": True}

    if command in {"/notion_pages", "/pages"}:
        size = 5
        if rest.strip().isdigit():
            size = max(1, min(10, int(rest.strip())))
        try:
            pages = await _fetch_notion_pages_for_user(user_id=user_id, page_size=size)
            if not pages:
                msg = "최근 Notion 페이지를 찾지 못했습니다."
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="success",
                    detail="pages_count=0",
                )
            else:
                lines = ["최근 Notion 페이지입니다:"]
                for idx, page in enumerate(pages, start=1):
                    lines.append(f"{idx}. {page['title']}")
                    lines.append(f"   {page['url']}")
                msg = "\n".join(lines)
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="success",
                    detail=f"pages_count={len(pages)}",
                )
        except HTTPException as exc:
            if exc.detail == "notion_not_connected":
                msg = "Notion이 아직 연결되지 않았습니다. 대시보드에서 먼저 Notion 연동을 완료해주세요."
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="error",
                    error_code="notion_not_connected",
                )
            else:
                msg = "Notion 페이지 조회에 실패했습니다. 잠시 후 다시 시도해주세요."
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="error",
                    error_code=str(exc.detail),
                )

        await _telegram_api(
            "sendMessage",
            {"chat_id": chat_id, "text": msg, "disable_web_page_preview": True},
        )
        return {"ok": True}

    if command in {"/notion_create", "/create"}:
        title = rest.strip()
        if not title:
            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command=command,
                status="error",
                error_code="missing_title",
            )
            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "생성할 제목을 입력해주세요.\n예: /notion_create Metel 회의록",
                },
            )
            return {"ok": True}
        if len(title) > 100:
            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command=command,
                status="error",
                error_code="title_too_long",
            )
            await _telegram_api(
                "sendMessage",
                {"chat_id": chat_id, "text": "제목은 100자 이내로 입력해주세요."},
            )
            return {"ok": True}
        try:
            page = await _create_notion_page_for_user(user_id=user_id, title=title)
            msg = f"Notion 페이지를 생성했습니다.\n- 제목: {page['title']}\n- 링크: {page['url']}"
            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command=command,
                status="success",
                detail=f"created_page_id={page.get('id')}",
            )
        except HTTPException as exc:
            if exc.detail == "notion_not_connected":
                msg = "Notion이 아직 연결되지 않았습니다. 대시보드에서 먼저 Notion 연동을 완료해주세요."
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="error",
                    error_code="notion_not_connected",
                )
            else:
                msg = "Notion 페이지 생성에 실패했습니다. 권한(콘텐츠 입력)과 연동 상태를 확인해주세요."
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command=command,
                    status="error",
                    error_code=str(exc.detail),
                )

        await _telegram_api(
            "sendMessage",
            {"chat_id": chat_id, "text": msg, "disable_web_page_preview": True},
        )
        return {"ok": True}

    if command in {"/help", "/menu"}:
        _record_command_log(
            user_id=user_id,
            chat_id=chat_id,
            command=command,
            status="success",
        )
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "사용 가능한 명령어\n"
                    "- /status\n"
                    "- /notion_pages\n"
                    "- /notion_pages 5\n"
                    "- /notion_create 제목\n"
                    "- /disconnect\n"
                    "- /help"
                ),
            },
        )
        return {"ok": True}

    _record_command_log(
        user_id=user_id,
        chat_id=chat_id,
        command=command or "(empty)",
        status="error",
        error_code="unknown_command",
    )
    await _telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": "명령을 이해하지 못했습니다. /help 를 입력해 사용 가능한 명령을 확인해주세요.",
        },
    )
    return {"ok": True}
