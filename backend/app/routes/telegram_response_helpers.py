import re

from agent.slot_schema import get_action_slot_schema


def _agent_error_guide(error_code: str | None, verification_reason: str | None = None) -> str:
    if not error_code:
        return ""

    guides = {
        "notion_not_connected": "Notion 미연결 상태입니다. 대시보드에서 Notion 연동 후 다시 시도해주세요.",
        "service_not_connected": "요청한 서비스가 연결되어 있지 않습니다. 대시보드에서 연동 후 다시 시도해주세요.",
        "token_missing": "연동 토큰이 없거나 손상되었습니다. 연동을 해제 후 다시 연결해주세요.",
        "auth_error": "권한이 부족하거나 만료되었습니다. 해당 서비스 권한을 다시 승인해주세요.",
        "rate_limited": "외부 API 호출 한도를 초과했습니다. 1~2분 후 다시 시도해주세요.",
        "validation_error": "요청 형식을 확인해주세요. 페이지 제목/데이터소스 ID/개수 형식을 점검해주세요.",
        "not_found": "요청한 페이지 또는 데이터를 찾지 못했습니다. 제목/ID를 다시 확인해주세요.",
        "upstream_error": "외부 서비스 응답 처리에 실패했습니다. 잠시 후 다시 시도해주세요.",
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


def _slot_input_example(action: str, slot_name: str) -> str:
    schema = get_action_slot_schema(action)
    if not schema:
        return f"{slot_name}: <값>"
    aliases = schema.aliases.get(slot_name) or ()
    key = aliases[0] if aliases else slot_name
    rule = schema.validation_rules.get(slot_name) or {}
    value_type = str(rule.get("type", "")).strip().lower()
    if value_type == "integer":
        return f"{key}: 5"
    if value_type == "boolean":
        return f"{key}: true"
    return f'{key}: "값"'


def _autonomous_fallback_hint(reason: str | None) -> str:
    if not reason:
        return ""
    guides = {
        "turn_limit": "자율 루프 turn 한도에 도달했습니다. 요청 범위를 더 좁혀서 다시 시도해주세요.",
        "tool_call_limit": "자율 루프 도구 호출 한도에 도달했습니다. 대상 페이지/개수를 명시해보세요.",
        "timeout": "자율 실행 시간 제한에 도달했습니다. 더 짧은 요청으로 재시도해주세요.",
        "replan_limit": "재계획 한도를 초과했습니다. 요청을 두 단계로 나눠서 시도해주세요.",
        "cross_service_blocks": "서비스 범위를 벗어난 도구 호출이 차단되어 안정 모드로 전환되었습니다. 대상 서비스를 명확히 지정해주세요.",
        "tool_error_rate": "도구 오류율이 높아 안정 모드로 전환되었습니다. 입력 파라미터를 더 구체화해주세요.",
        "replan_ratio": "재계획 비율이 높아 안정 모드로 전환되었습니다. 요청을 더 단순한 단계로 나눠주세요.",
        "verification_failed": "실행은 되었지만 요청 조건 충족 검증에 실패했습니다. 결과 조건을 더 구체화해주세요.",
        "move_requires_update_page": "이동 요청의 핵심 단계(update_page)가 실행되지 않았습니다. 원본/상위 페이지를 명확히 지정해주세요.",
        "append_requires_append_block_children": "추가 요청의 핵심 단계(append_block_children)가 실행되지 않았습니다. 대상 페이지 제목을 명시해주세요.",
        "append_requires_multiple_targets": "각각 추가 요청으로 인식되었지만 일부 페이지만 갱신되었습니다. 대상 페이지 수를 명시해 다시 시도해주세요.",
        "rename_requires_update_page": "제목 변경의 핵심 단계(update_page)가 실행되지 않았습니다. 기존/새 제목을 따옴표로 명시해주세요.",
        "archive_requires_archive_tool": "삭제/아카이브 도구 호출이 누락되었습니다. 페이지 삭제 요청임을 명시해주세요.",
    }
    return guides.get(reason, "")


def _slot_loop_metrics_from_notes(notes: list[str]) -> tuple[int, int, int]:
    started = 1 if any(note == "slot_loop_started" for note in (notes or [])) else 0
    completed = 1 if any(note == "slot_loop_completed" for note in (notes or [])) else 0
    turn_count = sum(1 for note in (notes or []) if note.startswith("slot_loop_turn:"))
    return started, completed, turn_count


def _build_user_preface_template(*, ok: bool, error_code: str | None, execution_message: str) -> str:
    if not ok:
        if error_code == "validation_error":
            return "입력값이 아직 부족해서 바로 실행하지 못했어요. 아래 보완 안내대로 한 번만 더 입력해 주세요."
        return "요청을 처리하는 중 문제가 있어요. 아래 실행 결과와 오류 안내를 먼저 확인해 주세요."
    summary = (execution_message or "").strip().splitlines()[0] if execution_message else ""
    if summary:
        return f"요청하신 작업 처리를 완료했습니다. 핵심 결과는 `{summary}` 입니다."
    return "요청하신 작업 처리를 완료했습니다. 아래 실행 결과를 확인해 주세요."


def _display_slot_name(action: str, slot_name: str) -> str:
    schema = get_action_slot_schema(action)
    if not schema:
        return slot_name
    aliases = schema.aliases.get(slot_name) or ()
    for alias in aliases:
        candidate = str(alias or "").strip()
        if not candidate:
            continue
        if re.search(r"[가-힣]", candidate):
            return candidate
    return aliases[0] if aliases else slot_name


def _first_non_empty_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _extract_first_url(text: str) -> str:
    match = re.search(r"https?://\S+", text or "")
    return match.group(0).strip() if match else ""


def _clip_log_detail(text: str, max_chars: int = 700) -> str:
    compact = (text or "").strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max(80, max_chars - 3)].rstrip() + "..."


def _truncate_telegram_message(text: str, max_chars: int) -> str:
    max_chars = max(120, max_chars)
    compact = (text or "").strip()
    if len(compact) <= max_chars:
        return compact
    keep = max_chars - len("\n\n(메시지가 길어 일부만 표시했어요.)")
    return f"{compact[:max(20, keep)].rstrip()}\n\n(메시지가 길어 일부만 표시했어요.)"


def _compose_telegram_response_text(
    *,
    debug_report_enabled: bool,
    user_message: str,
    report_text: str,
) -> str:
    if debug_report_enabled:
        return f"{user_message}\n\n{report_text}"
    return user_message


def _build_user_facing_message(
    *,
    ok: bool,
    execution_message: str,
    error_code: str | None,
    slot_action: str | None,
    missing_slot: str | None,
) -> str:
    if error_code == "validation_error" and missing_slot:
        display_slot = _display_slot_name(str(slot_action or ""), str(missing_slot))
        example = _slot_input_example(str(slot_action or ""), str(missing_slot))
        return (
            f"작업을 이어가려면 `{display_slot}` 값을 알려주세요. "
            f"예: {example} "
            "취소하려면 `취소`라고 입력해주세요."
        )

    if not ok:
        lines = [line.strip() for line in (execution_message or "").splitlines() if line.strip()]
        if not lines:
            return "요청 처리 중 문제가 발생했습니다. 다시 시도해 주세요."
        lead = lines[0]
        # Keep one extra line for actionable upstream detail (e.g. GraphQL error message).
        detail = lines[1] if len(lines) > 1 else ""
        if detail:
            return f"{lead}\n{detail}\n다시 시도해 주세요."
        return f"{lead} 다시 시도해 주세요."

    lead = _first_non_empty_line(execution_message) or "요청하신 작업을 완료했습니다."
    url = _extract_first_url(execution_message)
    if url and url not in lead:
        return f"{lead}\n{url}"
    return lead


def _should_use_preface_llm(*, ok: bool, error_code: str | None, execution_message: str) -> bool:
    if error_code == "validation_error":
        # Slot question/failure recovery should keep deterministic wording.
        return False
    if error_code:
        return True
    if not ok:
        return True
    return len((execution_message or "").strip()) >= 80
