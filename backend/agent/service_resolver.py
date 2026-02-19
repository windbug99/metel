from __future__ import annotations

from collections import defaultdict
from typing import Iterable


SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "notion": (
        "notion",
        "노션",
        "페이지",
        "문서",
        "데이터베이스",
        "회의록",
    ),
    "spotify": (
        "spotify",
        "스포티파이",
        "플레이리스트",
        "노래",
        "음악",
        "트랙",
    ),
    "google": (
        "google",
        "구글",
        "gmail",
        "캘린더",
        "드라이브",
    ),
    "github": (
        "github",
        "깃허브",
        "repo",
        "pull request",
        "이슈",
    ),
    "slack": (
        "slack",
        "슬랙",
        "채널",
        "메시지",
    ),
}


def resolve_services(
    user_text: str,
    connected_services: Iterable[str] | None = None,
    *,
    max_services: int = 3,
) -> list[str]:
    """Infer relevant services from user text.

    Returns highest-scored services first. If no keyword matches and one connected
    service exists, falls back to that single service.
    """
    normalized = user_text.strip().lower()
    connected = {service.strip().lower() for service in (connected_services or []) if service.strip()}
    scores: dict[str, int] = defaultdict(int)

    for service, keywords in SERVICE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                scores[service] += 1

    # Bias toward connected services so the planner avoids unavailable providers.
    for service in list(scores):
        if service in connected:
            scores[service] += 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    resolved = [service for service, _score in ranked]

    if connected:
        resolved = [service for service in resolved if service in connected]

    if not resolved and len(connected) == 1:
        return list(connected)

    if max_services <= 0:
        return resolved
    return resolved[:max_services]


def resolve_primary_service(
    user_text: str,
    connected_services: Iterable[str] | None = None,
) -> str | None:
    services = resolve_services(user_text, connected_services, max_services=1)
    return services[0] if services else None

