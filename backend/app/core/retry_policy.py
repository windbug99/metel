from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException


AsyncOperation = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class RetryResult:
    data: dict[str, Any]
    retry_count: int


def _extract_status_code(detail: str) -> int | None:
    match = re.search(r"\|status=(\d{3})", detail)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def should_retry_http_exception(exc: HTTPException) -> bool:
    detail = str(exc.detail or "")
    if ":VALIDATION_" in detail:
        return False
    if detail.endswith("_not_connected"):
        return False
    if ":RATE_LIMITED" in detail:
        return True
    status = _extract_status_code(detail)
    return status in {429, 500, 502, 503, 504}


async def run_with_retry(
    *,
    operation: AsyncOperation,
    max_retries: int,
    backoff_ms: int,
) -> RetryResult:
    retries = 0
    while True:
        try:
            data = await operation()
            return RetryResult(data=data, retry_count=retries)
        except HTTPException as exc:
            if retries >= max_retries or not should_retry_http_exception(exc):
                raise
            retries += 1
            if backoff_ms > 0:
                await asyncio.sleep((backoff_ms * retries) / 1000.0)
