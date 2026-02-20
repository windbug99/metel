from __future__ import annotations

import re
from typing import Iterable


CREATE_KEYWORDS = (
    "생성",
    "만들",
    "작성",
    "작성해",
    "작성해줘",
    "등록",
    "등록해",
    "등록해줘",
    "발행",
    "올려",
    "올려줘",
    "기입",
    "저장",
    "create",
    "save",
)
READ_KEYWORDS = (
    "조회",
    "검색",
    "찾",
    "목록",
    "보여",
    "불러",
    "가져와",
    "가져와줘",
    "확인",
    "읽어",
    "알려줘",
    "list",
    "search",
    "show",
)
SUMMARY_KEYWORDS = ("요약", "summary", "정리", "핵심 정리", "압축", "한줄요약")
UPDATE_KEYWORDS = ("수정", "변경", "갱신", "바꿔", "고쳐", "편집", "반영", "update")
DELETE_KEYWORDS = ("삭제", "지워", "아카이브", "휴지통", "제거", "없애", "archive", "remove", "delete")
APPEND_KEYWORDS = ("추가", "append", "덧붙여", "붙여", "넣어", "본문에")
DATA_SOURCE_KEYWORDS = ("데이터소스", "data source", "data_source", "데이터베이스", "database", "db")
LINEAR_ISSUE_KEYWORDS = ("이슈", "issue", "ticket", "티켓")
LINEAR_SERVICE_KEYWORDS = ("linear", "리니어")


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    lower = (text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def is_create_intent(text: str) -> bool:
    return contains_any(text, CREATE_KEYWORDS)


def is_read_intent(text: str) -> bool:
    return contains_any(text, READ_KEYWORDS)


def is_summary_intent(text: str) -> bool:
    return contains_any(text, SUMMARY_KEYWORDS)


def is_update_intent(text: str) -> bool:
    return contains_any(text, UPDATE_KEYWORDS)


def is_delete_intent(text: str) -> bool:
    return contains_any(text, DELETE_KEYWORDS)


def is_append_intent(text: str) -> bool:
    return contains_any(text, APPEND_KEYWORDS)


def is_data_source_intent(text: str) -> bool:
    return contains_any(text, DATA_SOURCE_KEYWORDS)


def is_linear_issue_create_intent(text: str) -> bool:
    if not (is_create_intent(text) and contains_any(text, LINEAR_ISSUE_KEYWORDS)):
        return False
    lower = (text or "").lower()
    if contains_any(lower, ("등록", "발행", "올려", "기입")) and contains_any(lower, LINEAR_ISSUE_KEYWORDS):
        return True
    return bool(
        re.search(r"(?:이슈|issue|티켓|ticket)\s*(?:생성|create|만들|작성)", lower)
        or re.search(r"(?:생성|create|만들|작성)\s*(?:이슈|issue|티켓|ticket)", lower)
    )
