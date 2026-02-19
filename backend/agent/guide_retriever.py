from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GUIDES_DIR = ROOT_DIR / "docs" / "api_guides"

# Keep section names in Korean to match current guide documents.
DEFAULT_PLANNING_SECTIONS = (
    "목적",
    "인증",
    "권한",
    "핵심 엔드포인트",
    "제한 사항",
    "에러 처리",
    "권장 워크플로우",
)


class GuideNotFoundError(FileNotFoundError):
    pass


def list_guide_services() -> list[str]:
    if not GUIDES_DIR.exists():
        return []
    services: list[str] = []
    for path in GUIDES_DIR.glob("*.md"):
        name = path.stem
        if name.startswith("_"):
            continue
        services.append(name)
    return sorted(services)


def load_guide(service: str) -> str:
    path = GUIDES_DIR / f"{service.lower()}.md"
    if not path.exists():
        raise GuideNotFoundError(f"API guide not found for service '{service}'")
    return path.read_text(encoding="utf-8")


def extract_sections(markdown: str, section_titles: tuple[str, ...]) -> dict[str, str]:
    """Extract heading sections from markdown.

    The parser is intentionally simple and only relies on markdown headings.
    """
    lines = markdown.splitlines()
    result: dict[str, list[str]] = {title: [] for title in section_titles}

    current_title: str | None = None
    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            heading = line.lstrip("#").strip()
            current_title = next((title for title in section_titles if title in heading), None)
            continue
        if current_title is not None:
            result[current_title].append(line)

    return {title: "\n".join(content).strip() for title, content in result.items() if any(content)}


def get_planning_context(
    service: str,
    *,
    max_chars: int = 5000,
    section_titles: tuple[str, ...] = DEFAULT_PLANNING_SECTIONS,
) -> str:
    guide = load_guide(service)
    sections = extract_sections(guide, section_titles)
    if not sections:
        context = guide.strip()
    else:
        chunks: list[str] = []
        for title in section_titles:
            body = sections.get(title)
            if not body:
                continue
            chunks.append(f"[{title}]\n{body}")
        context = "\n\n".join(chunks).strip()
    if len(context) > max_chars:
        return context[:max_chars].rstrip() + "\n..."
    return context

