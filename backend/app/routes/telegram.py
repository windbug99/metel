import logging
import base64
import hashlib
import hmac
import re
import time
import uuid
import json
from json import JSONDecodeError
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from supabase import create_client

from agent.loop import _should_run_atomic_overhaul, run_agent_analysis
from agent.registry import load_registry
from agent.runtime_api_profile import build_runtime_api_profile
from agent.service_resolver import resolve_primary_service
from app.core.auth import get_authenticated_user_id
from app.core.config import get_settings
from app.routes.telegram_response_helpers import (
    _agent_error_guide,
    _autonomous_fallback_hint,
    _build_user_facing_message,
    _build_user_preface_template,
    _clip_log_detail,
    _compose_telegram_response_text,
    _should_use_preface_llm,
    _slot_input_example,
    _slot_loop_metrics_from_notes,
    _truncate_telegram_message,
)
from app.security.token_vault import TokenVault

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

_HELP_FEATURES: dict[str, list[dict[str, object]]] = {
    "linear": [
        {"name": "최근 이슈 조회", "tools": ["linear_list_issues"], "examples": ["linear 최근 이슈 5개 검색해줘"]},
        {"name": "이슈 검색", "tools": ["linear_search_issues"], "examples": ['linear에서 "로그인 오류" 이슈 검색해줘']},
        {
            "name": "이슈 생성",
            "tools": ["linear_create_issue", "linear_list_teams"],
            "examples": ['linear에서 팀: operate, 제목: 결제 오류 대응 이슈 생성해줘'],
        },
        {
            "name": "이슈 설명 추가/수정",
            "tools": ["linear_update_issue"],
            "examples": [
                'linear에서 OPT-283 이슈의 설명에 "추가 메모"를 추가해줘',
                'linear에서 OPT-283 이슈의 설명을 "수정 메모"로 수정해줘',
            ],
        },
        {"name": "이슈 상태 변경", "tools": ["linear_update_issue", "linear_list_workflow_states"], "examples": ["linear에서 OPT-283 이슈의 상태를 Todo로 변경"]},
        {"name": "댓글 작성", "tools": ["linear_create_comment"], "examples": ['linear에서 OPT-283 이슈에 댓글로 "재현 확인 필요"를 남겨줘']},
    ],
    "notion": [
        {"name": "페이지 생성", "tools": ["notion_create_page"], "examples": ['notion에 "스프린트 회고" 페이지 생성해줘']},
        {"name": "페이지 조회", "tools": ["notion_search"], "examples": ['notion에서 "서비스 기획서" 페이지 조회해줘']},
        {
            "name": "본문 업데이트/추가",
            "tools": ["notion_update_page", "notion_append_block_children"],
            "examples": ['notion에서 "서비스 기획서" 페이지 본문에 "다음 액션"을 추가해줘'],
        },
    ],
    "google": [
        {"name": "캘린더 목록 조회", "tools": ["google_calendar_list_calendars"], "examples": ["구글 캘린더 목록 보여줘"]},
        {"name": "일정 조회", "tools": ["google_calendar_list_events"], "examples": ["오늘 구글 캘린더 일정 5개 조회해줘"]},
    ],
    "spotify": [
        {"name": "내 프로필 조회", "tools": ["spotify_get_me"], "examples": ["spotify 내 계정 정보 보여줘"]},
        {"name": "최근 재생 조회", "tools": ["spotify_get_recent_tracks"], "examples": ["spotify 최근 들은 곡 10개 보여줘"]},
        {"name": "플레이리스트 생성", "tools": ["spotify_create_playlist"], "examples": ['spotify에 "출근용 플레이리스트" 생성해줘']},
    ],
    "web": [
        {"name": "URL 본문 추출", "tools": ["http_fetch_url_text"], "examples": ["https://example.com 본문을 가져와 요약해줘"]},
    ],
}


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
        .order("updated_at", desc=True)
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
        .order("updated_at", desc=True)
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


def _get_granted_scopes_for_user(user_id: str) -> dict[str, set[str]]:
    settings = get_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        supabase.table("oauth_tokens")
        .select("provider,granted_scopes")
        .eq("user_id", user_id)
        .execute()
    )
    rows = result.data or []
    scope_map: dict[str, set[str]] = {}
    for row in rows:
        provider = (row.get("provider") or "").strip().lower()
        if not provider:
            continue
        raw = row.get("granted_scopes")
        scopes: set[str] = set()
        if isinstance(raw, list):
            scopes = {str(item).strip() for item in raw if str(item).strip()}
        elif isinstance(raw, str) and raw.strip():
            scopes = {item.strip() for item in raw.replace(",", " ").split() if item.strip()}
        scope_map[provider] = scopes
    return scope_map


def _normalize_help_target(target_text: str, connected_services: list[str]) -> str | None:
    raw = (target_text or "").strip().lower()
    if not raw:
        return None
    alias = {
        "리니어": "linear",
        "노션": "notion",
        "구글": "google",
        "캘린더": "google",
        "스포티파이": "spotify",
        "웹": "web",
        "api": "",
        "apis": "",
    }
    if raw in alias:
        mapped = alias[raw]
        return mapped or None
    token = raw.split()[0].strip()
    if token in alias:
        mapped = alias[token]
        return mapped or None
    registry = load_registry()
    available = set(registry.list_services())
    if token in available:
        return token
    inferred = resolve_primary_service(raw, connected_services=connected_services)
    if inferred in available:
        return inferred
    return None


def _build_service_help_message(service: str, enabled_api_ids: set[str]) -> str:
    svc = service.strip().lower()
    features = _HELP_FEATURES.get(svc, [])
    lines = [f"[{svc}] 사용 가능한 기능/예시"]
    available_count = 0
    for feature in features:
        required_tools = [str(item) for item in (feature.get("tools") or [])]
        if required_tools and not all(tool in enabled_api_ids for tool in required_tools):
            continue
        available_count += 1
        lines.append(f"- 기능: {feature.get('name')}")
        for example in feature.get("examples") or []:
            lines.append(f"  예시: {example}")
    if available_count == 0:
        lines.append("- 현재 권한/연결 상태로 바로 실행 가능한 기능이 없습니다.")
        lines.append(f"- OAuth 권한을 다시 승인한 뒤 /help {svc} 로 재확인하세요.")
    return "\n".join(lines)


def _build_status_message(connected_services: list[str]) -> str:
    connected = [item.strip().lower() for item in (connected_services or []) if item and item.strip()]
    connected = list(dict.fromkeys(connected))
    registry = load_registry()
    known_services = registry.list_services()

    lines = ["현재 연동 상태입니다.", "- Telegram: 연결됨"]
    for service in connected:
        lines.append(f"- {service}: 연결됨")
    for service in known_services:
        if service not in connected:
            lines.append(f"- {service}: 미연결")
    return "\n".join(lines)


async def _rewrite_user_preface_with_llm(
    *,
    settings,
    user_text: str,
    base_preface: str,
    execution_message: str,
    error_code: str | None,
) -> str:
    provider = (settings.llm_planner_provider or "openai").strip().lower()
    model = (settings.llm_planner_model or "gpt-4o-mini").strip()
    timeout_sec = max(5, int(getattr(settings, "llm_request_timeout_sec", 20)))
    max_chars = max(80, int(getattr(settings, "telegram_user_preface_max_chars", 240)))
    prompt = (
        "다음 실행 결과를 사용자에게 전달할 짧은 한국어 문장(1~2문장)으로 바꿔주세요.\n"
        "규칙:\n"
        "- 사실 추가/삭제 금지\n"
        "- ID/링크/수치/에러코드 임의 변경 금지\n"
        "- 친근하지만 업무용 톤\n"
        f"- {max_chars}자 이내\n\n"
        f"[원문 요청]\n{user_text}\n\n"
        f"[기본 안내문]\n{base_preface}\n\n"
        f"[실행 결과 요약]\n{execution_message}\n\n"
        f"[error_code]\n{error_code or '-'}"
    )
    try:
        if provider == "openai":
            if not settings.openai_api_key:
                return base_preface
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.post(
                    OPENAI_CHAT_COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "messages": [
                            {"role": "system", "content": "당신은 한국어 제품 어시스턴트입니다."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
            if response.status_code >= 400:
                return base_preface
            payload = response.json()
            text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            if text:
                return text[:max_chars]
            return base_preface

        if provider == "google":
            if not settings.google_api_key:
                return base_preface
            url = GEMINI_GENERATE_CONTENT_URL.format(model=model, api_key=settings.google_api_key)
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                )
            if response.status_code >= 400:
                return base_preface
            payload = response.json()
            candidates = payload.get("candidates") or []
            parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
            text = " ".join(str(part.get("text") or "") for part in parts).strip()
            if text:
                return text[:max_chars]
            return base_preface
    except Exception:
        return base_preface
    return base_preface


def _map_natural_text_to_command(text: str) -> tuple[str, str]:
    raw = text.strip()
    lower = raw.lower()

    help_match = re.fullmatch(r"(?i)(?:/help|/menu|/apis|/capabilities|help|menu|도움말|메뉴|명령어)\s*(.*)", raw)
    if help_match:
        return "/help", str(help_match.group(1) or "").strip()

    if re.fullmatch(r"(?i)(?:/status|status|상태|연결상태)(?:\s*(?:확인|조회|알려줘|보여줘))?", raw):
        return "/status", ""

    # 자연어 요청은 가능한 한 자율 에이전트 경로로 전달한다.
    # (/notion_pages, /notion_create 등 단축 명령은 사용자가 명시적으로 입력한 경우에만 처리)
    return "", ""


def _is_capabilities_query(text: str) -> bool:
    lower = (text or "").strip().lower()
    capability_tokens = (
        "할 수 있는 작업",
        "할수있는작업",
        "가능한 작업",
        "지원 기능",
        "무슨 기능",
        "무엇을 할 수",
        "뭐 할 수",
        "what can",
        "capability",
        "capabilities",
    )
    return any(token in lower for token in capability_tokens)


def _format_tools_for_service(service: str) -> list[str]:
    registry = load_registry()
    tools = registry.list_tools(service)
    if not tools:
        return []
    lines = [f"[{service}] 지원 API/기능"]
    for tool in tools:
        lines.append(f"- {tool.tool_name}: {tool.description}")
    return lines


def _build_capabilities_message(text: str, connected_services: list[str]) -> tuple[str, str | None]:
    connected = [service.strip().lower() for service in connected_services if service.strip()]
    target = resolve_primary_service(text, connected_services=connected)
    registry = load_registry()

    if target:
        lines = _format_tools_for_service(target)
        if not lines:
            return f"{target} 서비스의 지원 API 정보를 찾지 못했습니다.", target
        return "\n".join(lines), target

    services = connected or registry.list_services()
    if not services:
        return "현재 사용 가능한 서비스 정보가 없습니다.", None

    chunks: list[str] = []
    for service in services:
        lines = _format_tools_for_service(service)
        if lines:
            chunks.append("\n".join(lines))
    if not chunks:
        return "현재 조회 가능한 지원 API 정보가 없습니다.", None

    return "\n\n".join(chunks), None


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
    run_id: str | None = None,
    request_id: str | None = None,
    catalog_id: str | None = None,
    final_status: str | None = None,
    failed_task_id: str | None = None,
    failure_reason: str | None = None,
    missing_required_fields: list[str] | None = None,
    atomic_tool_name: str | None = None,
    atomic_verified: bool | None = None,
    atomic_verification_reason: str | None = None,
    atomic_verification_retry_attempted: bool | None = None,
    atomic_verification_checks: dict | None = None,
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
            "run_id": run_id,
            "request_id": request_id,
            "catalog_id": catalog_id,
            "final_status": final_status,
            "failed_task_id": failed_task_id,
            "failure_reason": failure_reason,
            "missing_required_fields": missing_required_fields or [],
            "atomic_tool_name": atomic_tool_name,
            "atomic_verified": atomic_verified,
            "atomic_verification_reason": atomic_verification_reason,
            "atomic_verification_retry_attempted": atomic_verification_retry_attempted,
            "atomic_verification_checks": atomic_verification_checks or {},
        }
        supabase.table("command_logs").insert(payload).execute()
    except Exception as exc:
        logger.exception("failed to record command log: %s", exc)


def _record_pipeline_step_logs(
    *,
    user_id: str | None,
    request_id: str,
    execution,
):
    if execution is None:
        return
    artifacts = execution.artifacts or {}
    router_mode = str(artifacts.get("router_mode") or "").strip()
    run_id = str(artifacts.get("pipeline_run_id") or request_id).strip() or request_id
    if not run_id:
        return

    rows: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    def _parse_missing(raw: str | None) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return []

    def _parse_checks(raw: str | None) -> dict:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    # DAG node runs -> step logs
    dag_node_runs_json = str(artifacts.get("dag_node_runs_json") or "").strip()
    if dag_node_runs_json:
        try:
            parsed = json.loads(dag_node_runs_json)
        except Exception:
            parsed = []
        if isinstance(parsed, list):
            for idx, row in enumerate(parsed, start=1):
                if not isinstance(row, dict):
                    continue
                node_id = str(row.get("node_id") or f"node_{idx}").strip()
                status = str(row.get("status") or "").strip().lower()
                node_type = str(row.get("node_type") or "").strip().lower()
                validation_status = "passed" if status == "success" else "failed"
                call_status = "succeeded" if status == "success" else ("failed" if status == "error" else "skipped")
                rows.append(
                    {
                        "run_id": run_id,
                        "request_id": request_id,
                        "user_id": user_id,
                        "task_index": idx,
                        "task_id": node_id,
                        "sentence": f"{node_type}:{node_id}",
                        "service": None,
                        "api": None,
                        "catalog_id": str(artifacts.get("catalog_id") or "").strip() or None,
                        "contract_version": "v1",
                        "llm_status": "success" if (node_type == "llm_transform" and status == "success") else ("failed" if node_type == "llm_transform" else "success"),
                        "validation_status": validation_status,
                        "call_status": call_status,
                        "missing_required_fields": [],
                        "validation_error_code": str(row.get("error_code") or "").strip() or None,
                        "failure_reason": str(row.get("error_code") or "").strip() or None,
                        "request_payload": None,
                        "normalized_response": None,
                        "raw_response": None,
                        "created_at": now_iso,
                    }
                )

    # STEPWISE results -> step logs
    stepwise_results_json = str(artifacts.get("stepwise_results_json") or "").strip()
    if stepwise_results_json:
        try:
            parsed = json.loads(stepwise_results_json)
        except Exception:
            parsed = []
        if isinstance(parsed, list):
            for idx, row in enumerate(parsed, start=1):
                if not isinstance(row, dict):
                    continue
                rows.append(
                    {
                        "run_id": run_id,
                        "request_id": request_id,
                        "user_id": user_id,
                        "task_index": idx,
                        "task_id": str(row.get("task_id") or f"step_{idx}").strip(),
                        "sentence": str(row.get("task_id") or f"step_{idx}").strip(),
                        "service": str(row.get("service") or "").strip() or _infer_service_from_api(str(row.get("tool_name") or "").strip()),
                        "api": str(row.get("tool_name") or "").strip() or None,
                        "catalog_id": str(artifacts.get("catalog_id") or "").strip() or None,
                        "contract_version": "v1",
                        "llm_status": "success",
                        "validation_status": "passed",
                        "call_status": "succeeded",
                        "missing_required_fields": [],
                        "validation_error_code": None,
                        "failure_reason": None,
                        "request_payload": row.get("request_payload"),
                        "normalized_response": row.get("result"),
                        "raw_response": None,
                        "created_at": now_iso,
                    }
                )

    # Failure-only fallback row for stepwise when no stepwise_results_json is present.
    if not rows and router_mode == "STEPWISE_PIPELINE":
        missing_raw = str(artifacts.get("missing_required_fields") or "[]").strip() or "[]"
        failed_request_payload = artifacts.get("failed_request_payload")
        parsed_failed_request_payload = None
        if isinstance(failed_request_payload, dict):
            parsed_failed_request_payload = failed_request_payload
        elif isinstance(failed_request_payload, str) and failed_request_payload.strip():
            try:
                maybe_payload = json.loads(failed_request_payload)
                if isinstance(maybe_payload, dict):
                    parsed_failed_request_payload = maybe_payload
            except Exception:
                parsed_failed_request_payload = None
        failed_api = str(artifacts.get("failed_api") or "").strip() or None
        failed_service = str(artifacts.get("failed_service") or "").strip() or _infer_service_from_api(failed_api)
        rows.append(
            {
                "run_id": run_id,
                "request_id": request_id,
                "user_id": user_id,
                "task_index": 1,
                "task_id": str(artifacts.get("failed_task_id") or "step_1"),
                "sentence": str(artifacts.get("failed_task_id") or "step_1"),
                "service": failed_service,
                "api": failed_api,
                "catalog_id": str(artifacts.get("catalog_id") or "").strip() or None,
                "contract_version": "v1",
                "llm_status": "failed",
                "validation_status": "failed",
                "call_status": "skipped",
                "missing_required_fields": _parse_missing(missing_raw),
                "validation_error_code": str(artifacts.get("error_code") or "").strip() or None,
                "failure_reason": str(artifacts.get("failure_reason") or artifacts.get("reason") or "").strip() or None,
                "request_payload": parsed_failed_request_payload,
                "normalized_response": None,
                "raw_response": None,
                "created_at": now_iso,
            }
        )

    # Atomic overhaul fallback rows (single-tool pipeline) when DAG/stepwise rows are absent.
    if not rows:
        tool_name = str(artifacts.get("tool_name") or "").strip()
        verified = str(artifacts.get("verified") or "").strip()
        verification_reason = str(artifacts.get("verification_reason") or "").strip() or None
        verification_checks = _parse_checks(str(artifacts.get("verification_checks") or "").strip())
        error_code = str(artifacts.get("error_code") or "").strip() or None
        missing_slot = str(artifacts.get("missing_slot") or "").strip()
        service = _infer_service_from_api(tool_name) if tool_name else None
        if tool_name:
            call_status = "succeeded"
            if error_code == "tool_failed":
                call_status = "failed"
            elif error_code in {"validation_error", "clarification_needed", "risk_gate_blocked"}:
                call_status = "skipped"
            rows.append(
                {
                    "run_id": run_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "task_index": 1,
                    "task_id": f"tool:{tool_name}",
                    "sentence": tool_name,
                    "service": service,
                    "api": tool_name,
                    "catalog_id": str(artifacts.get("catalog_id") or "").strip() or None,
                    "contract_version": "v1",
                    "llm_status": "success",
                    "validation_status": "failed" if error_code in {"validation_error", "clarification_needed", "risk_gate_blocked"} else "passed",
                    "call_status": call_status,
                    "missing_required_fields": [missing_slot] if missing_slot else [],
                    "validation_error_code": error_code,
                    "failure_reason": verification_reason or error_code,
                    "request_payload": None,
                    "normalized_response": {"verification_checks": verification_checks} if verification_checks else None,
                    "raw_response": None,
                    "created_at": now_iso,
                }
            )

            rows.append(
                {
                    "run_id": run_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "task_index": 2,
                    "task_id": "expectation_verification",
                    "sentence": "expectation_verification",
                    "service": service,
                    "api": "expectation_verification",
                    "catalog_id": str(artifacts.get("catalog_id") or "").strip() or None,
                    "contract_version": "v1",
                    "llm_status": "success",
                    "validation_status": "passed" if verified == "1" else "failed",
                    "call_status": "succeeded" if verified == "1" else "failed",
                    "missing_required_fields": [],
                    "validation_error_code": error_code if verified != "1" else None,
                    "failure_reason": verification_reason if verified != "1" else None,
                    "request_payload": None,
                    "normalized_response": {"checks": verification_checks, "reason": verification_reason},
                    "raw_response": None,
                    "created_at": now_iso,
                }
            )

    if not rows:
        return

    try:
        settings = get_settings()
        supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        supabase.table("pipeline_step_logs").insert(rows).execute()
    except Exception as exc:
        # Table may not exist before migration rollout; keep runtime non-blocking.
        logger.warning("pipeline_step_logs best-effort insert skipped: %s", exc)


def _parse_detail_pairs(detail: str | None) -> dict[str, str]:
    raw = str(detail or "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for token in raw.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _parse_missing_required_fields(value: object) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _parse_atomic_verification_checks(value: object) -> dict:
    if isinstance(value, dict):
        return value
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_service_from_api(api: str | None) -> str | None:
    name = str(api or "").strip().lower()
    if not name or "_" not in name:
        return None
    prefix = name.split("_", 1)[0].strip()
    return prefix or None


def _note_value(notes: list[str], prefix: str) -> str:
    for note in notes:
        text = str(note or "").strip()
        if text.startswith(prefix):
            return text.split("=", 1)[1].strip()
    return ""


def _build_structured_intent_log(*, notes: list[str], missing_slot: str | None, slot_action: str | None) -> dict:
    include_raw = _note_value(notes, "event_filter_include=")
    exclude_raw = _note_value(notes, "event_filter_exclude=")
    include = [item.strip() for item in include_raw.split(",") if item.strip()] if include_raw else []
    exclude = [item.strip() for item in exclude_raw.split(",") if item.strip()] if exclude_raw else []
    target_scope = _note_value(notes, "target_scope=")
    time_scope = _note_value(notes, "time_scope=")
    result_limit_raw = _note_value(notes, "result_limit=")
    result_limit = None
    if result_limit_raw:
        try:
            result_limit = int(result_limit_raw)
        except Exception:
            result_limit = None
    payload = {
        "time_scope": time_scope or None,
        "target_scope": target_scope or None,
        "filter_include": include,
        "filter_exclude": exclude,
        "result_limit": result_limit,
        "missing_slot": str(missing_slot or "").strip() or None,
        "slot_action": str(slot_action or "").strip() or None,
    }
    return payload


def _build_structured_autonomous_log(
    *,
    notes: list[str],
    execution_mode: str,
    autonomous_fallback_reason: str | None,
    analysis_ok: bool,
) -> dict:
    shadow_executed = any(str(note).strip() == "autonomous_shadow_executed=1" for note in notes)
    shadow_ok = any(str(note).strip() == "autonomous_shadow_ok=1" for note in notes)
    retry_count = 1 if any(str(note).strip() == "autonomous_retry=1" for note in notes) else 0
    replan_hist: dict[str, int] = {}
    tuning_rule = _note_value(notes, "autonomous_retry_tuning_rule=")
    if tuning_rule:
        replan_hist[tuning_rule] = replan_hist.get(tuning_rule, 0) + 1
    fallback_reason = str(autonomous_fallback_reason or "").strip()
    if fallback_reason:
        replan_hist[fallback_reason] = replan_hist.get(fallback_reason, 0) + 1
    attempted = (
        execution_mode == "autonomous"
        or shadow_executed
        or bool(fallback_reason)
        or any(str(note).strip().startswith("autonomous_error=") for note in notes)
    )
    success = (execution_mode == "autonomous" and bool(analysis_ok)) or (shadow_executed and shadow_ok)
    fallback = execution_mode == "rule" and bool(fallback_reason)
    return {
        "attempted": bool(attempted),
        "success": bool(success),
        "fallback": bool(fallback),
        "shadow_executed": bool(shadow_executed),
        "shadow_ok": bool(shadow_ok),
        "replan_reason_histogram": replan_hist,
        "retry_count": retry_count,
    }


def _build_structured_verifier_log(
    *,
    execution_error_code: str | None,
    verification_reason: str | None,
    verifier_failed_rule: str | None,
    verifier_remediation_type: str | None,
) -> dict:
    failed_rule = str(verifier_failed_rule or "").strip() or str(verification_reason or "").strip() or None
    remediation_type = str(verifier_remediation_type or "").strip() or None
    if not remediation_type and (execution_error_code or "") == "verification_failed":
        remediation_type = "retry_with_constraints"
    return {
        "failed_rule": failed_rule,
        "remediation_type": remediation_type,
    }


def _build_structured_pipeline_log(
    *,
    execution,
    dag_pipeline: bool,
) -> dict:
    if execution is None:
        return {
            "composed_pipeline": bool(dag_pipeline),
            "pipeline_run_id": None,
            "created_count": 0,
            "transform_success_count": 0,
            "transform_error_count": 0,
            "verify_error_count": 0,
            "verify_fail_before_write": False,
        }
    artifacts = execution.artifacts or {}
    router_mode = str(artifacts.get("router_mode") or "").strip()
    node_runs_raw = str(artifacts.get("dag_node_runs_json") or "").strip()
    node_runs: list[dict] = []
    if node_runs_raw:
        try:
            parsed = json.loads(node_runs_raw)
            if isinstance(parsed, list):
                node_runs = [item for item in parsed if isinstance(item, dict)]
        except Exception:
            node_runs = []

    transform_success_count = sum(
        1 for row in node_runs if row.get("node_type") == "llm_transform" and row.get("status") == "success"
    )
    transform_error_count = sum(
        1 for row in node_runs if row.get("node_type") == "llm_transform" and row.get("status") == "error"
    )
    verify_error_count = sum(1 for row in node_runs if row.get("node_type") == "verify" and row.get("status") == "error")
    write_success_count = sum(
        1
        for row in node_runs
        if row.get("node_type") == "skill" and row.get("status") == "success"
    )

    created_count_raw = str(artifacts.get("processed_count") or "").strip()
    created_count = 0
    if created_count_raw:
        try:
            created_count = int(created_count_raw)
        except Exception:
            created_count = 0

    base_payload = {
        "composed_pipeline": bool(dag_pipeline),
        "router_mode": router_mode or None,
        "pipeline_run_id": str(artifacts.get("pipeline_run_id") or "").strip() or None,
        "created_count": created_count,
        "transform_success_count": transform_success_count,
        "transform_error_count": transform_error_count,
        "verify_error_count": verify_error_count,
        "verify_fail_before_write": bool(verify_error_count > 0 and write_success_count == 0),
        "atomic_tool_name": str(artifacts.get("tool_name") or "").strip() or None,
        "atomic_verified": str(artifacts.get("verified") or "").strip() == "1",
        "atomic_verification_reason": str(artifacts.get("verification_reason") or "").strip() or None,
        "atomic_verification_retry_attempted": str(artifacts.get("verification_retry_attempted") or "").strip() == "1",
    }
    if router_mode != "STEPWISE_PIPELINE":
        return base_payload

    stepwise_results_raw = str(artifacts.get("stepwise_results_json") or "").strip()
    stepwise_results: list[dict] = []
    if stepwise_results_raw:
        try:
            parsed = json.loads(stepwise_results_raw)
            if isinstance(parsed, list):
                stepwise_results = [item for item in parsed if isinstance(item, dict)]
        except Exception:
            stepwise_results = []

    step_count = len(stepwise_results)
    retry_total = 0
    retry_step_count = 0
    for item in stepwise_results:
        attempts_raw = item.get("attempts")
        attempts = 1
        try:
            attempts = max(1, int(attempts_raw))
        except Exception:
            attempts = 1
        if attempts > 1:
            retry_step_count += 1
            retry_total += attempts - 1

    error_code = str(artifacts.get("error_code") or "").strip()
    failed_task_id = str(artifacts.get("failed_task_id") or "").strip()
    validation_fail_count = 1 if error_code in {"validation_error", "missing_required_fields"} else 0
    successful_steps = sum(1 for step in (execution.steps or []) if getattr(step, "status", "") == "success")
    failed_steps = sum(1 for step in (execution.steps or []) if getattr(step, "status", "") == "error")

    base_payload.update(
        {
            "stepwise_step_count": step_count,
            "stepwise_success_step_count": successful_steps,
            "stepwise_failed_step_count": failed_steps,
            "stepwise_retry_total": retry_total,
            "stepwise_retry_step_count": retry_step_count,
            "stepwise_validation_fail_count": validation_fail_count,
            "stepwise_failed_task_id": failed_task_id or None,
        }
    )
    return base_payload


def _append_structured_log_detail(
    *,
    base_detail: str,
    request_id: str,
    intent_payload: dict,
    autonomous_payload: dict,
    verifier_payload: dict,
    pipeline_payload: dict,
) -> str:
    pairs = _parse_detail_pairs(base_detail)
    pairs["request_id"] = request_id
    pairs["intent_json"] = json.dumps(intent_payload, ensure_ascii=False, separators=(",", ":"))
    pairs["autonomous_json"] = json.dumps(autonomous_payload, ensure_ascii=False, separators=(",", ":"))
    pairs["verifier_json"] = json.dumps(verifier_payload, ensure_ascii=False, separators=(",", ":"))
    pairs["pipeline_json"] = json.dumps(pipeline_payload, ensure_ascii=False, separators=(",", ":"))
    return ";".join(f"{key}={value}" for key, value in pairs.items())


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
    logger.info(
        "telegram webhook ingress update_id=%s has_message=%s secret_header=%s",
        update.get("update_id"),
        bool(update.get("message") or update.get("edited_message")),
        1 if x_telegram_bot_api_secret_token else 0,
    )

    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            logger.warning(
                "telegram webhook secret mismatch update_id=%s header_present=%s",
                update.get("update_id"),
                1 if x_telegram_bot_api_secret_token else 0,
            )
            raise HTTPException(status_code=401, detail="유효하지 않은 webhook secret입니다.")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    update_id = update.get("update_id")

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
    connected_services = _get_connected_services_for_user(user_id)
    if not command.startswith("/"):
        mapped_command, mapped_rest = _map_natural_text_to_command(text)
        if mapped_command:
            command = mapped_command
            rest = mapped_rest
        else:
            if _is_capabilities_query(text):
                capabilities_message, target_service = _build_capabilities_message(text, connected_services)
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command="capabilities",
                    status="success",
                    detail=f"target_service={target_service or 'all'}",
                )
                await _telegram_api(
                    "sendMessage",
                    {"chat_id": chat_id, "text": capabilities_message, "disable_web_page_preview": True},
                )
                return {"ok": True}
            analysis_started_at = time.perf_counter()
            try:
                analysis = await run_agent_analysis(text, connected_services, user_id)
            except Exception as exc:
                logger.exception("telegram agent analysis failed chat_id=%s user_id=%s", chat_id, user_id)
                _record_command_log(
                    user_id=user_id,
                    chat_id=chat_id,
                    command="agent_plan",
                    status="error",
                    error_code="agent_analysis_exception",
                    detail=f"exception={exc.__class__.__name__}",
                )
                await _telegram_api(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                    },
                )
                return {"ok": True}
            analysis_latency_ms = int((time.perf_counter() - analysis_started_at) * 1000)

            requirements_text = "\n".join(f"- {item.summary}" for item in analysis.plan.requirements) or "- (없음)"
            services_text = ", ".join(analysis.plan.target_services) if analysis.plan.target_services else "(추론 실패)"
            tools_text = (
                "\n".join(f"- {tool}" for tool in analysis.plan.selected_tools)
                if analysis.plan.selected_tools
                else "- (선정된 API 없음)"
            )
            workflow_text = "\n".join(f"{idx}. {step}" for idx, step in enumerate(analysis.plan.workflow_steps, start=1))
            tasks_text = (
                "\n".join(
                    f"- [{task.task_type}] {task.id}: {task.title}"
                    + (f" | service={task.service}" if task.service else "")
                    + (f" | tool={task.tool_name}" if task.tool_name else "")
                    + (f" | depends_on={','.join(task.depends_on)}" if task.depends_on else "")
                    for task in analysis.plan.tasks
                )
                if analysis.plan.tasks
                else "- (분해된 작업 없음)"
            )
            execution_steps_text = ""
            execution_message = analysis.result_summary
            execution_error_code = None
            execution_mode = "rule"
            autonomous_fallback_reason = None
            verification_reason = None
            llm_provider = None
            llm_model = None
            guardrail_degrade_reason = None
            v2_rollout_reason = None
            v2_shadow_mode = None
            v2_shadow_executed = None
            v2_shadow_ok = None
            atomic_overhaul_rollout = None
            atomic_overhaul_shadow_mode = None
            skill_llm_transform_rollout = None
            skill_llm_transform_shadow_mode = None
            skill_llm_transform_shadow_executed = None
            skill_llm_transform_shadow_ok = None
            router_source = None
            missing_slot = None
            slot_action = None
            for note in analysis.plan.notes:
                if note.startswith("autonomous_error="):
                    autonomous_fallback_reason = note.split("=", 1)[1]
                if note.startswith("autonomous_guardrail_degrade:"):
                    guardrail_degrade_reason = note.split(":", 1)[1]
                if note.startswith("llm_provider="):
                    llm_provider = note.split("=", 1)[1]
                if note.startswith("llm_model="):
                    llm_model = note.split("=", 1)[1]
                if note.startswith("skill_v2_rollout="):
                    v2_rollout_reason = note.split("=", 1)[1]
                if note.startswith("skill_v2_shadow_mode="):
                    v2_shadow_mode = note.split("=", 1)[1]
                if note.startswith("skill_v2_shadow_executed="):
                    v2_shadow_executed = note.split("=", 1)[1]
                if note.startswith("skill_v2_shadow_ok="):
                    v2_shadow_ok = note.split("=", 1)[1]
                if note.startswith("atomic_overhaul_rollout="):
                    atomic_overhaul_rollout = note.split("=", 1)[1]
                if note.startswith("atomic_overhaul_shadow_mode="):
                    atomic_overhaul_shadow_mode = note.split("=", 1)[1]
                if note.startswith("skill_llm_transform_rollout="):
                    skill_llm_transform_rollout = note.split("=", 1)[1]
                if note.startswith("skill_llm_transform_shadow_mode="):
                    skill_llm_transform_shadow_mode = note.split("=", 1)[1]
                if note.startswith("skill_llm_transform_shadow_executed="):
                    skill_llm_transform_shadow_executed = note.split("=", 1)[1]
                if note.startswith("skill_llm_transform_shadow_ok="):
                    skill_llm_transform_shadow_ok = note.split("=", 1)[1]
                if note.startswith("router_source="):
                    router_source = note.split("=", 1)[1]
            if atomic_overhaul_rollout is None or atomic_overhaul_shadow_mode is None:
                try:
                    atomic_serve, atomic_shadow, atomic_reason = _should_run_atomic_overhaul(
                        settings=settings,
                        user_id=str(user_id or ""),
                    )
                    if atomic_overhaul_rollout is None:
                        atomic_overhaul_rollout = atomic_reason
                    if atomic_overhaul_shadow_mode is None:
                        atomic_overhaul_shadow_mode = "1" if atomic_shadow and not atomic_serve else "0"
                except Exception:
                    pass
            if analysis.execution:
                execution_steps_text = (
                    "\n".join(f"- {step.name}: {step.status} ({step.detail})" for step in analysis.execution.steps)
                    or "- (실행 단계 없음)"
                )
                execution_message = analysis.execution.user_message
                execution_error_code = analysis.execution.artifacts.get("error_code")
                missing_slot = analysis.execution.artifacts.get("missing_slot")
                slot_action = analysis.execution.artifacts.get("slot_action")
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
                elif analysis.plan_source == "router_v2":
                    execution_mode = "router_v2"
                if execution_error_code == "verification_failed" and verification_reason:
                    autonomous_fallback_reason = verification_reason
                if not autonomous_fallback_reason and execution_error_code:
                    autonomous_fallback_reason = execution_error_code
                if execution_error_code:
                    execution_message += _agent_error_guide(execution_error_code, verification_reason)
                if execution_error_code == "validation_error" and missing_slot:
                    example = _slot_input_example(str(slot_action or ""), str(missing_slot))
                    execution_message += (
                        "\n\n[입력 보완]\n"
                        f"- 누락 항목: {missing_slot}\n"
                        f"- 입력 예시: {example}"
                    )
            if execution_mode == "rule" and guardrail_degrade_reason:
                autonomous_fallback_reason = guardrail_degrade_reason
            mode_extra = ""
            if execution_mode == "rule" and autonomous_fallback_reason:
                hint = _autonomous_fallback_hint(autonomous_fallback_reason)
                mode_extra = f"\n- autonomous_fallback_reason: {autonomous_fallback_reason}"
                if hint:
                    mode_extra += f"\n- fallback_hint: {hint}"
            if v2_rollout_reason:
                mode_extra += f"\n- skill_v2_rollout: {v2_rollout_reason}"
            if v2_shadow_mode is not None:
                mode_extra += f"\n- skill_v2_shadow_mode: {v2_shadow_mode}"
            if v2_shadow_executed is not None:
                mode_extra += f"\n- skill_v2_shadow_executed: {v2_shadow_executed}"
            if v2_shadow_ok is not None:
                mode_extra += f"\n- skill_v2_shadow_ok: {v2_shadow_ok}"
            if skill_llm_transform_rollout:
                mode_extra += f"\n- skill_llm_transform_rollout: {skill_llm_transform_rollout}"
            if skill_llm_transform_shadow_mode is not None:
                mode_extra += f"\n- skill_llm_transform_shadow_mode: {skill_llm_transform_shadow_mode}"
            if skill_llm_transform_shadow_executed is not None:
                mode_extra += f"\n- skill_llm_transform_shadow_executed: {skill_llm_transform_shadow_executed}"
            if skill_llm_transform_shadow_ok is not None:
                mode_extra += f"\n- skill_llm_transform_shadow_ok: {skill_llm_transform_shadow_ok}"
            if router_source:
                mode_extra += f"\n- router_source: {router_source}"
            mode_extra += f"\n- analysis_latency_ms: {analysis_latency_ms}"
            notes = analysis.plan.notes or []
            slot_loop_started, slot_loop_completed, slot_loop_turns = _slot_loop_metrics_from_notes(notes)
            slot_loop_enabled = 1 if any(note == "slot_loop_enabled=1" for note in notes) else 0
            metrics_enabled = bool(getattr(settings, "slot_loop_metrics_enabled", True))
            if metrics_enabled:
                mode_extra += (
                    f"\n- slot_loop_enabled: {slot_loop_enabled}"
                    f"\n- slot_loop_started: {slot_loop_started}"
                    f"\n- slot_loop_completed: {slot_loop_completed}"
                    f"\n- slot_loop_turns: {slot_loop_turns}"
                )
            exec_artifacts = analysis.execution.artifacts if analysis.execution else {}
            pipeline_run_id = str(exec_artifacts.get("pipeline_run_id") or "").strip()
            dag_idempotent_reuse = str(exec_artifacts.get("idempotent_success_reuse_count") or "").strip()
            dag_mode = str(exec_artifacts.get("router_mode") or "").strip() == "PIPELINE_DAG"
            dag_pipeline = dag_mode or bool(pipeline_run_id) or analysis.plan_source == "dag_template"
            dag_failed_step = str(exec_artifacts.get("failed_step") or "").strip()
            dag_reason = str(exec_artifacts.get("reason") or "").strip()
            verifier_failed_rule = str(exec_artifacts.get("verifier_failed_rule") or "").strip() or None
            verifier_remediation_type = str(exec_artifacts.get("verifier_remediation_type") or "").strip() or None

            request_id = ""
            if update_id is not None:
                request_id = f"tg_update:{update_id}"
            elif chat_id is not None and message_id is not None:
                request_id = f"tg_message:{chat_id}:{message_id}"
            elif chat_id is not None:
                request_id = f"tg_chat:{chat_id}:{int(time.time())}"

            base_detail = (
                (
                    f"services={services_text}"
                    if not metrics_enabled
                    else (
                        f"services={services_text};"
                        f"slot_loop_enabled={slot_loop_enabled};"
                        f"slot_loop_started={slot_loop_started};"
                        f"slot_loop_completed={slot_loop_completed};"
                        f"slot_loop_turns={slot_loop_turns}"
                    )
                )
                + (
                    f";missing_slot={missing_slot};slot_action={slot_action}"
                    if missing_slot and slot_action
                    else ""
                )
                + (
                    f";validation_error={analysis.execution.artifacts.get('validation_error')}"
                    if analysis.execution and analysis.execution.artifacts.get("validation_error")
                    else ""
                )
                + (
                    f";validated_payloads={analysis.execution.artifacts.get('validated_payloads_json')}"
                    if analysis.execution and analysis.execution.artifacts.get("validated_payloads_json")
                    else ""
                )
                + (f";skill_v2_rollout={v2_rollout_reason}" if v2_rollout_reason else "")
                + (f";skill_v2_shadow_mode={v2_shadow_mode}" if v2_shadow_mode is not None else "")
                + (f";skill_v2_shadow_executed={v2_shadow_executed}" if v2_shadow_executed is not None else "")
                + (f";skill_v2_shadow_ok={v2_shadow_ok}" if v2_shadow_ok is not None else "")
                + (f";atomic_overhaul_rollout={atomic_overhaul_rollout}" if atomic_overhaul_rollout else "")
                + (
                    f";atomic_overhaul_shadow_mode={atomic_overhaul_shadow_mode}"
                    if atomic_overhaul_shadow_mode is not None
                    else ""
                )
                + (f";skill_llm_transform_rollout={skill_llm_transform_rollout}" if skill_llm_transform_rollout else "")
                + (
                    f";skill_llm_transform_shadow_mode={skill_llm_transform_shadow_mode}"
                    if skill_llm_transform_shadow_mode is not None
                    else ""
                )
                + (
                    f";skill_llm_transform_shadow_executed={skill_llm_transform_shadow_executed}"
                    if skill_llm_transform_shadow_executed is not None
                    else ""
                )
                + (
                    f";skill_llm_transform_shadow_ok={skill_llm_transform_shadow_ok}"
                    if skill_llm_transform_shadow_ok is not None
                    else ""
                )
                + (f";router_source={router_source}" if router_source else "")
                + (f";dag_pipeline=1" if dag_pipeline else "")
                + (f";pipeline_run_id={pipeline_run_id}" if pipeline_run_id else "")
                + (f";dag_failed_step={dag_failed_step}" if dag_failed_step else "")
                + (f";dag_reason={dag_reason}" if dag_reason else "")
                + (f";idempotent_success_reuse_count={dag_idempotent_reuse}" if dag_idempotent_reuse else "")
                + f";analysis_latency_ms={analysis_latency_ms}"
            )
            structured_intent = _build_structured_intent_log(
                notes=notes,
                missing_slot=missing_slot,
                slot_action=slot_action,
            )
            structured_autonomous = _build_structured_autonomous_log(
                notes=notes,
                execution_mode=execution_mode,
                autonomous_fallback_reason=autonomous_fallback_reason,
                analysis_ok=analysis.ok,
            )
            structured_verifier = _build_structured_verifier_log(
                execution_error_code=execution_error_code,
                verification_reason=verification_reason,
                verifier_failed_rule=verifier_failed_rule,
                verifier_remediation_type=verifier_remediation_type,
            )
            structured_pipeline = _build_structured_pipeline_log(
                execution=analysis.execution,
                dag_pipeline=dag_pipeline,
            )
            structured_detail = _append_structured_log_detail(
                base_detail=base_detail,
                request_id=request_id,
                intent_payload=structured_intent,
                autonomous_payload=structured_autonomous,
                verifier_payload=structured_verifier,
                pipeline_payload=structured_pipeline,
            )

            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command="agent_plan",
                status="success" if analysis.ok else "error",
                error_code=None if analysis.ok else (execution_error_code or "execution_failed"),
                detail=_clip_log_detail(structured_detail),
                plan_source=analysis.plan_source,
                execution_mode=execution_mode,
                autonomous_fallback_reason=autonomous_fallback_reason,
                llm_provider=llm_provider,
                llm_model=llm_model,
                verification_reason=verification_reason,
                run_id=str(exec_artifacts.get("pipeline_run_id") or request_id or ""),
                request_id=request_id,
                catalog_id=str(exec_artifacts.get("catalog_id") or "").strip() or None,
                final_status="success" if analysis.ok else "error",
                failed_task_id=str(exec_artifacts.get("failed_task_id") or exec_artifacts.get("failed_step") or "").strip() or None,
                failure_reason=str(exec_artifacts.get("failure_reason") or exec_artifacts.get("reason") or "").strip() or None,
                missing_required_fields=_parse_missing_required_fields(exec_artifacts.get("missing_required_fields")),
                atomic_tool_name=str(exec_artifacts.get("tool_name") or "").strip() or None,
                atomic_verified=(str(exec_artifacts.get("verified") or "").strip() == "1") if exec_artifacts.get("verified") is not None else None,
                atomic_verification_reason=str(exec_artifacts.get("verification_reason") or "").strip() or None,
                atomic_verification_retry_attempted=(
                    str(exec_artifacts.get("verification_retry_attempted") or "").strip() == "1"
                    if exec_artifacts.get("verification_retry_attempted") is not None
                    else None
                ),
                atomic_verification_checks=_parse_atomic_verification_checks(exec_artifacts.get("verification_checks")),
            )
            _record_pipeline_step_logs(
                user_id=user_id,
                request_id=request_id,
                execution=analysis.execution,
            )

            report_text = (
                "에이전트 실행 결과\n\n"
                f"[1] 작업 요구사항\n{requirements_text}\n\n"
                f"[2-3] 타겟 서비스 및 필요 API\n"
                f"- 서비스: {services_text}\n"
                f"- API/Tool:\n{tools_text}\n\n"
                f"[3.5] 작업 분해(TOOL/LLM)\n{tasks_text}\n\n"
                f"[4] 생성된 워크플로우\n{workflow_text}\n\n"
                f"[실행 모드]\n- plan_source: {analysis.plan_source}\n- execution_mode: {execution_mode}{mode_extra}\n\n"
                f"[5-6] 실행/결과 정리\n{execution_message}\n\n"
                f"[실행 단계 로그]\n{execution_steps_text}"
            )

            user_message = _build_user_facing_message(
                ok=analysis.ok,
                execution_message=execution_message,
                error_code=execution_error_code,
                slot_action=slot_action,
                missing_slot=missing_slot,
            )
            debug_report_enabled = bool(getattr(settings, "telegram_debug_report_enabled", False))
            max_chars = max(200, int(getattr(settings, "telegram_message_max_chars", 3500)))
            final_text = _compose_telegram_response_text(
                debug_report_enabled=debug_report_enabled,
                user_message=user_message,
                report_text=report_text,
            )
            final_text = _truncate_telegram_message(final_text, max_chars=max_chars)

            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": final_text,
                    "disable_web_page_preview": True,
                },
            )
            return {"ok": True}

    if command in {"/status", "/my_status"}:
        status_connected_services = _get_connected_services_for_user(str(user_id))
        _record_command_log(
            user_id=user_id,
            chat_id=chat_id,
            command=command,
            status="success",
            detail=f"connected_services={','.join(status_connected_services) if status_connected_services else '(none)'}",
        )
        await _telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": _build_status_message(status_connected_services),
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

    if command in {"/help", "/menu", "/apis", "/capabilities"}:
        help_target = _normalize_help_target(rest, connected_services)
        if rest.strip() and not help_target:
            available = ", ".join(connected_services) if connected_services else "(없음)"
            await _telegram_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": (
                        f"지원하지 않는 서비스입니다: {rest.strip()}\n"
                        f"연결된 서비스: {available}\n"
                        "예: /help linear"
                    ),
                },
            )
            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command=command,
                status="error",
                error_code="invalid_help_target",
                detail=f"target={rest.strip()}",
            )
            return {"ok": True}

        if help_target:
            granted_scopes = _get_granted_scopes_for_user(str(user_id))
            settings = get_settings()
            profile = build_runtime_api_profile(
                connected_services=connected_services,
                granted_scopes=granted_scopes,
                risk_policy={"allow_high_risk": bool(settings.delete_operations_enabled)},
            )
            enabled_api_ids = {str(item) for item in (profile.get("enabled_api_ids") or [])}
            text_out = _build_service_help_message(help_target, enabled_api_ids)
            _record_command_log(
                user_id=user_id,
                chat_id=chat_id,
                command=command,
                status="success",
                detail=f"target_service={help_target}",
            )
            await _telegram_api(
                "sendMessage",
                {"chat_id": chat_id, "text": text_out, "disable_web_page_preview": True},
            )
            return {"ok": True}

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
                    "- /help linear | /help notion | /help google | /help spotify\n"
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
