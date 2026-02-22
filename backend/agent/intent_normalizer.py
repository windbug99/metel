from __future__ import annotations

import re


def extract_linear_issue_reference(text: str) -> str | None:
    keyed = re.search(r"\b([A-Za-z]{2,10}-\d{1,6})\b", text or "")
    if keyed:
        return keyed.group(1)
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text or "")
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    return None


def extract_notion_page_title(text: str) -> str | None:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text or "")
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    pattern = re.search(r"(?i)(?:notion|노션)(?:에서|의)?\s*(.+?)\s*페이지", (text or "").strip())
    if pattern:
        candidate = pattern.group(1).strip(" \"'`")
        if candidate:
            return candidate
    return None


def _sanitize_title(candidate: str | None, *, max_len: int = 100) -> str | None:
    value = str(candidate or "").strip(" \"'`.,")
    if not value:
        return None
    lowered = value.lower()
    if value in {"에", "의", "에서"} or lowered in {"at", "in", "on"}:
        return None
    if len(value) < 2:
        return None
    return value[:max_len]


def extract_notion_page_title_for_create(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    labeled = re.search(
        r"(?i)(?:제목은|title is|제목|title)\s*[:：]?\s*['\"“”]?"
        r"(.+?)"
        r"(?=(?:\s*(?:이고|이며|,|\.)?\s*(?:내용|본문|설명|description)\s*[:：])|$)",
        normalized,
    )
    if labeled:
        candidate = _sanitize_title(labeled.group(1))
        if candidate:
            return candidate
    page_labeled = re.search(
        r"(?i)(?:페이지\s*제목|page\s*title)\s*[:：]?\s*['\"“”]?(.+?)['\"“”]?"
        r"(?=(?:\s*(?:이고|이며|,|\.)?\s*(?:내용|본문|설명|description)\s*[:：])|$)",
        normalized,
    )
    if page_labeled:
        candidate = _sanitize_title(page_labeled.group(1))
        if candidate:
            return candidate
    for pattern in [
        r'(?i)(?:notion|노션)(?:에서|에|의)?\s*["“]([^"”]+)["”]\s*페이지',
        r"(?i)(?:notion|노션)(?:에서|에|의)?\s*'([^']+)'\s*페이지",
        r'(?i)["“]([^"”]+)["”]\s*(?:페이지)\s*(?:생성|만들|작성|create)',
    ]:
        match = re.search(pattern, (text or "").strip())
        if match:
            candidate = _sanitize_title(match.group(1))
            if candidate:
                return candidate
    prefix_intent = re.search(
        r"(?i)^\s*(.+?)\s*(?:을|를)\s*(?:notion|노션)(?:에서|에|의)?.*(?:페이지).*(?:생성|만들|작성|create)",
        normalized,
    )
    if prefix_intent:
        candidate = re.sub(r"(?i)^(?:기사|문서|내용)\s*", "", prefix_intent.group(1)).strip()
        candidate = _sanitize_title(candidate)
        if candidate:
            return candidate
    return _sanitize_title(extract_notion_page_title(text))


def extract_notion_update_new_title(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    patterns = [
        r'(?i)(?:페이지\s*)?(?:제목|title)(?:을|를)?\s*["“]?([^"”]+?)["”]?\s*(?:로|으로)?\s*(?:업데이트|수정|변경|바꿔|rename)',
        r'(?i)(?:새\s*제목|new\s*title)\s*[:：]?\s*["“]?([^"”]+?)["”]?(?:\s|$)',
        r'(?i)(?:제목|title)\s*[:：]\s*["“]?([^"”]+?)["”]?(?:\s|$)',
    ]
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`.,")
        if candidate:
            return candidate[:100]
    return None


def extract_notion_update_body_text(text: str) -> str | None:
    raw = " ".join((text or "").strip().split())
    patterns = [
        r"(?i)(?:본문\s*업데이트|본문\s*수정|content\s*update|내용\s*업데이트)\s*[:：]\s*(.+)$",
        r"(?i)(?:본문|내용)\s*[:：]\s*(.+)$",
        r'(?i)(?:본문|내용)에\s*["“]?(.+?)["”]?\s*(?:추가|append|넣어|작성)',
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`")
        if candidate:
            return candidate[:1800]
    return None


def extract_linear_team_reference(text: str) -> str | None:
    keyed = re.search(r"(?i)(?:팀|team)\s*[:：]?\s*([^\s,]+)", (text or "").strip())
    if keyed:
        candidate = keyed.group(1).strip(" \"'`")
        if candidate:
            return candidate
    return None


def extract_linear_issue_title_for_create(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    labeled = re.search(
        r"(?i)(?:제목은|title is|제목|title)\s*[:：]?\s*['\"“”]?"
        r"(.+?)"
        r"(?=(?:\s+(?:설명|내용|description|본문|priority|우선순위|라벨|label|담당자|assignee)\s*[:：])|$)",
        normalized,
    )
    if labeled:
        candidate = labeled.group(1).strip(" \"'`.,")
        if candidate:
            return candidate[:120]
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text or "")
    for a, b in quoted:
        candidate = (a or b or "").strip()
        if candidate:
            return candidate
    service_first = re.search(
        r"(?i)(?:linear|리니어)(?:에서|에|의)?\s*(.+?)\s*(?:이슈)\s*(?:생성|만들|작성|create)",
        normalized,
    )
    if service_first:
        candidate = service_first.group(1).strip(" \"'`.,")
        candidate = re.sub(r"(?i)^(?:팀|team)\s*[:：]?\s*[^\s,]+\s*", "", candidate).strip()
        if candidate:
            return candidate[:120]
    pattern = re.search(r"(?i)(.+?)\s*(?:linear|리니어).*(?:이슈).*(?:생성|만들|작성|create)", (text or "").strip())
    if pattern:
        candidate = pattern.group(1).strip(" \"'`")
        candidate = re.sub(r"^(?:linear|리니어)(?:의|에서)?\s*", "", candidate, flags=re.IGNORECASE).strip()
        if candidate:
            return candidate[:120]
    return None


def extract_linear_update_new_title(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    patterns = [
        r'(?i)(?:이슈\s*)?(?:제목|title)(?:을|를)?\s*["“]?([^"”]+?)["”]?\s*(?:로|으로)?\s*(?:업데이트|수정|변경|바꿔|rename)',
        r"(?i)(?:새\s*제목|new\s*title)\s*[:：]?\s*['\"“”]?(.+?)['\"“”]?(?:\s|$)",
        r"(?i)(?:제목|title)\s*[:：]\s*['\"“”]?(.+?)['\"“”]?(?:\s|$)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, normalized)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`.,")
        if candidate:
            return candidate[:120]
    return None


def extract_linear_update_description_text(text: str) -> str | None:
    raw = " ".join((text or "").strip().split())
    patterns = [
        r"(?i)(?:설명|description|내용|본문)\s*(?:업데이트|수정|변경)?\s*[:：]\s*(.+)$",
        r'(?i)(?:설명|description|내용|본문)에\s*["“]?(.+?)["”]?\s*(?:추가|append|넣어|작성|반영)',
        r"(?i)(?:설명|description|내용|본문)(?:을|를)?\s*(.+?)\s*(?:으로|로)\s*(?:업데이트|수정|변경|바꿔|바꿔줘|수정해줘|업데이트해줘|수정하세요|변경해줘)",
    ]
    for pattern in patterns:
        matched = re.search(pattern, raw)
        if not matched:
            continue
        candidate = str(matched.group(1) or "").strip(" \"'`")
        if candidate:
            return candidate[:5000]
    return None


def extract_linear_update_state_id(text: str) -> str | None:
    normalized = " ".join((text or "").strip().split())
    matched = re.search(r"(?i)(?:state_id|state id|상태id|상태_id)\s*[:：]\s*([^\s,]+)", normalized)
    if not matched:
        return None
    candidate = str(matched.group(1) or "").strip(" \"'`.,")
    return candidate or None


def extract_linear_update_priority(text: str) -> int | None:
    normalized = " ".join((text or "").strip().split())
    matched = re.search(r"(?i)(?:priority|우선순위)\s*[:：]\s*([0-4])", normalized)
    if not matched:
        return None
    try:
        return int(matched.group(1))
    except Exception:
        return None


def extract_count_limit(text: str, *, default: int = 5, minimum: int = 1, maximum: int = 20) -> int:
    m = re.search(r"(\d{1,3})\s*(?:개|건|items?)", text or "", flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bfirst\s*[:=]?\s*(\d{1,3})\b", text or "", flags=re.IGNORECASE)
    if not m:
        return default
    value = int(m.group(1))
    return max(minimum, min(maximum, value))


def safe_int(value: object, *, default: int, minimum: int = 1, maximum: int = 20) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))
