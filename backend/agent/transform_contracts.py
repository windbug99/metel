from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _event_title(event: dict[str, Any]) -> str:
    return str(event.get("title") or event.get("summary") or "").strip()


def _event_description(event: dict[str, Any]) -> str:
    return str(event.get("description") or "").strip()


def _is_meeting_event(event: dict[str, Any], include: list[str], exclude: list[str]) -> bool:
    title = _event_title(event).lower()
    description = _event_description(event).lower()
    merged = f"{title} {description}".strip()
    if include:
        include_ok = any(token.lower() in merged for token in include if str(token).strip())
        if not include_ok:
            return False
    if exclude:
        exclude_hit = any(token.lower() in merged for token in exclude if str(token).strip())
        if exclude_hit:
            return False
    return True


def _normalize_event_for_transform(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(event.get("id") or "").strip(),
        "title": _event_title(event),
        "description": _event_description(event),
        "start": _as_dict(event.get("start")),
        "end": _as_dict(event.get("end")),
        "attendees": _as_list(event.get("attendees")),
    }


def transform_filter_meeting_events(payload: dict[str, Any]) -> dict[str, Any]:
    events = _as_list(payload.get("events"))
    include = [str(item).strip() for item in _as_list(payload.get("keyword_include")) if str(item).strip()]
    exclude = [str(item).strip() for item in _as_list(payload.get("keyword_exclude")) if str(item).strip()]
    if not include:
        include = ["회의", "meeting"]

    normalized_events = [_normalize_event_for_transform(event) for event in events if isinstance(event, dict)]
    meeting_events = [event for event in normalized_events if _is_meeting_event(event, include=include, exclude=exclude)]
    return {
        "meeting_events": meeting_events,
        "meeting_count": len(meeting_events),
        "source_count": len(normalized_events),
    }


def transform_format_detailed_minutes(payload: dict[str, Any]) -> dict[str, Any]:
    event = _as_dict(payload.get("event"))
    if not event:
        event = _normalize_event_for_transform(payload)
    else:
        event = _normalize_event_for_transform(event)

    title = event.get("title") or "제목 없음 회의"
    start_text = str(_as_dict(event.get("start")).get("dateTime") or _as_dict(event.get("start")).get("date") or "-").strip()
    end_text = str(_as_dict(event.get("end")).get("dateTime") or _as_dict(event.get("end")).get("date") or "-").strip()
    attendees = [str(_as_dict(item).get("email") or "").strip() for item in _as_list(event.get("attendees")) if str(_as_dict(item).get("email") or "").strip()]
    attendees_text = ", ".join(attendees) if attendees else "-"
    description = event.get("description") or "-"

    lines = [
        f"회의명: {title}",
        f"시작: {start_text}",
        f"종료: {end_text}",
        f"참석자: {attendees_text}",
        "",
        "회의 목적:",
        "- ",
        "논의 내용:",
        "- ",
        "결정 사항:",
        "- ",
        "액션 아이템:",
        "- [ ] ",
        "",
        f"원본 설명: {description[:1200]}",
    ]
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": line[:1800]},
                    }
                ]
            },
        }
        for line in lines
        if line.strip()
    ][:80]

    return {
        "title": f"회의록 초안 - {title}"[:100],
        "children": children,
        "source_event_id": str(event.get("id") or "").strip(),
    }


def transform_format_linear_meeting_issue(payload: dict[str, Any]) -> dict[str, Any]:
    event = _as_dict(payload.get("event"))
    if not event:
        event = _normalize_event_for_transform(payload)
    else:
        event = _normalize_event_for_transform(event)

    title = event.get("title") or "제목 없음 회의"
    start_text = str(_as_dict(event.get("start")).get("dateTime") or _as_dict(event.get("start")).get("date") or "-").strip()
    end_text = str(_as_dict(event.get("end")).get("dateTime") or _as_dict(event.get("end")).get("date") or "-").strip()
    attendees = [str(_as_dict(item).get("email") or "").strip() for item in _as_list(event.get("attendees")) if str(_as_dict(item).get("email") or "").strip()]
    attendees_text = ", ".join(attendees) if attendees else "-"
    description = event.get("description") or "-"

    lines = [
        "Google Calendar 회의에서 자동 생성된 이슈입니다.",
        f"- 회의명: {title}",
        f"- 시작: {start_text}",
        f"- 종료: {end_text}",
        f"- 참석자: {attendees_text}",
        "",
        "회의 목적:",
        "- ",
        "논의 내용:",
        "- ",
        "결정 사항:",
        "- ",
        "액션 아이템:",
        "- [ ] ",
        "",
        f"원본 설명: {description[:3000]}",
    ]
    merged_description = "\n".join(lines)[:7800]
    return {
        "title": f"[회의] {title}"[:200],
        "description": merged_description,
        "source_event_id": str(event.get("id") or "").strip(),
    }


def run_transform_contract(transform_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(transform_name or "").strip()
    if name == "filter_meeting_events":
        return transform_filter_meeting_events(payload)
    if name == "format_detailed_minutes":
        return transform_format_detailed_minutes(payload)
    if name == "format_linear_meeting_issue":
        return transform_format_linear_meeting_issue(payload)
    return dict(payload or {})
