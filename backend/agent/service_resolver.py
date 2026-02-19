from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from agent.registry import load_registry


SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "notion": ("notion", "노션", "페이지", "문서", "데이터베이스", "회의록"),
    "spotify": ("spotify", "스포티파이", "플레이리스트", "노래", "음악", "트랙"),
    "google": ("google", "구글", "gmail", "캘린더", "드라이브"),
    "github": ("github", "깃허브", "repo", "pull request", "이슈"),
    "slack": ("slack", "슬랙", "채널", "메시지"),
}


def _build_dynamic_keywords(connected: set[str]) -> dict[str, set[str]]:
    keyword_map: dict[str, set[str]] = {
        service: set(keywords) for service, keywords in SERVICE_KEYWORDS.items()
    }

    try:
        registry = load_registry()
    except Exception:
        return keyword_map

    for service in connected:
        if not service:
            continue
        terms = keyword_map.setdefault(service, set())
        terms.add(service)
        for token in service.replace("-", " ").replace("_", " ").split():
            if len(token) >= 2:
                terms.add(token)

        for tool in registry.list_tools(service):
            tool_tokens = (
                f"{tool.tool_name} {tool.description}"
                .lower()
                .replace("-", " ")
                .replace("_", " ")
                .split()
            )
            for token in tool_tokens:
                if len(token) >= 3 and token not in {"tool", "api", "call"}:
                    terms.add(token)

    return keyword_map


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
    keyword_map = _build_dynamic_keywords(connected or set(SERVICE_KEYWORDS.keys()))

    for service, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in normalized:
                scores[service] += 1

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
