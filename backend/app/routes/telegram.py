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

from agent.loop import run_agent_analysis
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
                "Notion-Version": settings.notion_api_version,
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
    parent_page_id = (settings.notion_default_parent_page_id or "").strip()
    parent = {"page_id": parent_page_id} if parent_page_id else {"workspace": True}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": settings.notion_api_version,
                "Content-Type": "application/json",
            },
            json={
                "parent": parent,
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


def _get_connected_services_for_user(user_id: str) -> list[str]:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("provider")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    services = []
    for row in rows:
        provider = (row.get("provider") or "").strip().lower()
        if provider:
            services.append(provider)
    # unique while preserving order
    return list(dict.fromkeys(services))


def _agent_error_guide(error_code: str | None, verification_reason: str | None = None) -> str:
    if not error_code:
        return ""

    guides = {
        "notion_not_connected": "Notion 미연결 상태입니다. 대시보드에서 Notion 연동 후 다시 시도해주세요.",
        "token_missing": "연동 토큰이 없거나 손상되었습니다. 연동을 해제 후 다시 연결해주세요.",
        "auth_error": "권한이 부족하거나 만료되었습니다. Notion 권한을 다시 승인해주세요.",
        "rate_limited": "외부 API 호출 한도를 초과했습니다. 1~2분 후 다시 시도해주세요.",
        "validation_error": "요청 형식을 확인해주세요. 페이지 제목/데이터소스 ID/개수 형식을 점검해주세요.",
        "not_found": "요청한 페이지 또는 데이터를 찾지 못했습니다. 제목/ID를 다시 확인해주세요.",
        "upstream_error": "Notion 응답 처리에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "execution_error": "실행 중 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        "verification_failed": "자율 실행 결과가 요청 조건을 충족하지 못했습니다. 더 구체적으로 다시 요청해주세요.",
    }
    hint = guides.get(error_code)
    if error_code == "verification_failed" and verification_reason:
        verification_hints = {
            "move_requires_update_page": "이동 요청이지만 실제 페이지 이동(update_page)이 수행되지 않았습니다.",
            "append_requires_append_block_children": "추가 요청이지만 실제 본문 추가(append_block_children)가 수행되지 않았습니다.",
            "append_requires_multiple_targets": "여러 페이지 각각에 추가 요청이지만 일부 대상에만 추가되었습니다.",
            "rename_requires_update_page": "제목 변경 요청이지만 실제 페이지 업데이트가 수행되지 않았습니다.",
            "archive_requires_archive_tool": "삭제/아카이브 요청이지만 아카이브 도구 호출이 수행되지 않았습니다.",
            "lookup_requires_tool_call": "조회 요청이지만 실제 조회 도구 호출이 수행되지 않았습니다.",
            "creation_requires_artifact_reference": "생성 요청이지만 생성 결과(id/url) 확인이 되지 않았습니다.",
            "mutation_requires_mutation_tool": "변경 요청이지만 변경 도구 호출이 수행되지 않았습니다.",
            "empty_final_response": "최종 응답이 비어 있습니다.",
        }
        detail_hint = verification_hints.get(verification_reason)
        if detail_hint:
            hint = f"{hint}\n  세부: {detail_hint}"
    if not hint:
        return ""
    return f"\n\n[오류 가이드]\n- 코드: {error_code}\n- 안내: {hint}"


def _autonomous_fallback_hint(reason: str | None) -> str:
    if not reason:
        return ""
    guides = {
        "turn_limit": "자율 루프 turn 한도에 도달했습니다. 요청 범위를 더 좁혀서 다시 시도해주세요.",
        "tool_call_limit": "자율 루프 도구 호출 한도에 도달했습니다. 대상 페이지/개수를 명시해보세요.",
        "timeout": "자율 실행 시간 제한에 도달했습니다. 더 짧은 요청으로 재시도해주세요.",
        "replan_limit": "재계획 한도를 초과했습니다. 요청을 두 단계로 나눠서 시도해주세요.",
        "verification_failed": "실행은 되었지만 요청 조건 충족 검증에 실패했습니다. 결과 조건을 더 구체화해주세요.",
        "move_requires_update_page": "이동 요청의 핵심 단계(update_page)가 실행되지 않았습니다. 원본/상위 페이지를 명확히 지정해주세요.",
        "append_requires_append_block_children": "추가 요청의 핵심 단계(append_block_children)가 실행되지 않았습니다. 대상 페이지 제목을 명시해주세요.",
        "append_requires_multiple_targets": "각각 추가 요청으로 인식되었지만 일부 페이지만 갱신되었습니다. 대상 페이지 수를 명시해 다시 시도해주세요.",
        "rename_requires_update_page": "제목 변경의 핵심 단계(update_page)가 실행되지 않았습니다. 기존/새 제목을 따옴표로 명시해주세요.",
        "archive_requires_archive_tool": "삭제/아카이브 도구 호출이 누락되었습니다. 페이지 삭제 요청임을 명시해주세요.",
    }
    return guides.get(reason, "")


def _map_natural_text_to_command(text: str) -> tuple[str, str]:
    raw = text.strip()
    lower = raw.lower()

    if any(keyword in lower for keyword in ["도움말", "help", "메뉴", "menu", "명령어"]):
        return "/help", ""

    if any(keyword in lower for keyword in ["상태", "status", "연결상태"]):
        return "/status", ""

    # 자연어 요청은 가능한 한 자율 에이전트 경로로 전달한다.
    # (/notion_pages, /notion_create 등 단축 명령은 사용자가 명시적으로 입력한 경우에만 처리)
    return "", ""


def _record_command_log(
    *,
    user_id: str | None,
    chat_id: int | None,
    command: str,
    status: str,
    error_code: str | None = None,
    detail: str | None = None,
    plan_source: str | None = None,
    execution_mode: str | None = None,
    autonomous_fallback_reason: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    verification_reason: str | None = None,
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
            "plan_source": plan_source,
            "execution_mode": execution_mode,
            "autonomous_fallback_reason": autonomous_fallback_reason,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "verification_reason": verification_reason,
        }
        try:
            supabase.table("command_logs").insert(payload).execute()
        except Exception as exc:
            # Backward compatibility: if SQL migration is not applied yet, retry with legacy fields only.
            text = str(exc).lower()
            if any(
                marker in text
                for marker in (
                    "column",
                    "plan_source",
                    "execution_mode",
                    "autonomous_fallback_reason",
                    "llm_provider",
                    "llm_model",
                    "verification_reason",
                )
            ):
                legacy_payload = {
                    "user_id": user_id,
                    "channel": "telegram",
                    "chat_id": chat_id,
                    "command": command,
                    "status": status,
                    "error_code": error_code,
                    "detail": detail,
                }
                supabase.table("command_logs").insert(legacy_payload).execute()
            else:
                raise
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
        else:
            connected_services = _get_connected_services_for_user(user_id)
            analysis = await run_agent_analysis(text, connected_services, user_id)

            requirements_text = "\n".join(f"- {item.summary}" for item in analysis.plan.requirements) or "- (없음)"
            services_text = ", ".join(analysis.plan.target_services) if analysis.plan.target_services else "(추론 실패)"
            tools_text = (
                "\n".join(f"- {tool}" for tool in analysis.plan.selected_tools)
                if analysis.plan.selected_tools
                else "- (선정된 API 없음)"
            )
            workflow_text = "\n".join(f"{idx}. {step}" for idx, step in enumerate(analysis.plan.workflow_steps, start=1))
            execution_steps_text = ""
            execution_message = analysis.result_summary
            execution_error_code = None
            execution_mode = "rule"
            autonomous_fallback_reason = None
            verification_reason = None
            llm_provider = None
            llm_model = None
            for note in analysis.plan.notes:
                if note.startswith("autonomous_error="):
                    autonomous_fallback_reason = note.split("=", 1)[1]
                if note.startswith("llm_provider="):
                    llm_provider = note.split("=", 1)[1]
                if note.startswith("llm_model="):
                    llm_model = note.split("=", 1)[1]
            if analysis.execution:
                execution_steps_text = (
                    "\n".join(f"- {step.name}: {step.status} ({step.detail})" for step in analysis.execution.steps)
                    or "- (실행 단계 없음)"
                )
                execution_message = analysis.execution.user_message
                execution_error_code = analysis.execution.artifacts.get("error_code")
                verification_reason = analysis.execution.artifacts.get("verification_reason")
                if not llm_provider:
                    llm_provider = analysis.execution.artifacts.get("llm_provider")
                if not llm_model:
                    llm_model = analysis.execution.artifacts.get("llm_model")
                if not verification_reason:
                    for step in analysis.execution.steps:
                        if step.name.endswith("_verify") and step.status == "error":
                            verification_reason = step.detail
                            break
                if analysis.execution.artifacts.get("autonomous") == "true":
                    execution_mode = "autonomous"
                if execution_error_code == "verification_failed" and verification_reason:
                    autonomous_fallback_reason = verification_reason
                if not autonomous_fallback_reason and execution_error_code:
                    autonomous_fallback_reason = execution_error_code
                if execution_error_code:
                    execution_message += _agent_error_guide(execution_error_code, verification_reason)
            mode_extra = ""
            if execution_mode == "rule" and autonomous_fallback_reason:
                hint = _autonomous_fallback_hint(autonomous_fallback_reason)
                mode_extra = f"\n- autonomous_fallback_reason: {autonomous_fallback_reason}"
                if hint:
                    mode_extra += f"\n- fallback_hint: {hint}"

            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command="agent_plan",
                status="success" if analysis.ok else "error",
                error_code=None if analysis.ok else (execution_error_code or "execution_failed"),
                detail=f"services={services_text}",
                plan_source=analysis.plan_source,
                execution_mode=execution_mode,
                autonomous_fallback_reason=autonomous_fallback_reason,
                llm_provider=llm_provider,
                llm_model=llm_model,
                verification_reason=verification_reason,
            )

            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": (
                        "에이전트 실행 결과\n\n"
                        f"[1] 작업 요구사항\n{requirements_text}\n\n"
                        f"[2-3] 타겟 서비스 및 필요 API\n"
                        f"- 서비스: {services_text}\n"
                        f"- API/Tool:\n{tools_text}\n\n"
                        f"[4] 생성된 워크플로우\n{workflow_text}\n\n"
                        f"[실행 모드]\n- plan_source: {analysis.plan_source}\n- execution_mode: {execution_mode}{mode_extra}\n\n"
                        f"[5-6] 실행/결과 정리\n{execution_message}\n\n"
                        f"[실행 단계 로그]\n{execution_steps_text}"
                    ),
                    "disable_web_page_preview": True,
                },
            )
            return {"ok": True}

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
