"""Vault research stubs — compounding knowledge from watchlist research."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings


@dataclass(frozen=True)
class ResearchStubResult:
    agency_path: str | None
    competitor_path: str | None
    created: tuple[str, ...]


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"
    return base[:72]


def _write_stub(path: Path, content: str) -> bool:
    if path.is_file():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _stub_note(
    *,
    page_type: str,
    name: str,
    page_id: str,
    context_lines: list[str],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ctx = "\n".join(f"- {line}" for line in context_lines if line.strip())
    citations = " • ".join(line for line in context_lines if line.strip())[:240]
    return f"""---
name: "{name.replace('"', "'")}"
type: "{page_type}"
id: "{page_id}"
trust: candidate
added: "{now}"
last_updated: "{today}"
citations: "{citations}"
source: thread_watchlist_research
tags: watchlist, stub
---

# {name}

> Research stub from Pulse watchlist. Promote via review gate after enrichment.

## Context
{ctx}

## Next steps
- [[capture-llm-wiki]]
- USAspending incumbent spend patterns
- Web research (review-gated)
"""


def ensure_watchlist_research_stubs(
    settings: Settings,
    *,
    title: str,
    agency: str,
    award_key: str | None = None,
    notice_id: str | None = None,
) -> ResearchStubResult:
    vault = settings.resolve(settings.knowledge_vault_path)
    created: list[str] = []
    agency_path: str | None = None
    competitor_path: str | None = None

    context = [
        f"Recipient/incumbent: {title}" if title else "",
        f"Agency: {agency}" if agency else "",
        f"Award key: {award_key}" if award_key else "",
        f"SAM notice: {notice_id}" if notice_id else "",
    ]

    if agency.strip():
        rel_agency = Path("entities/agencies") / f"{_slug(agency)}.md"
        if _write_stub(
            vault / rel_agency,
            _stub_note(
                page_type="agency",
                name=agency.strip(),
                page_id=f"entity-agency-{_slug(agency)}",
                context_lines=context,
            ),
        ):
            created.append(str(rel_agency).replace("\\", "/"))
        agency_path = str(rel_agency).replace("\\", "/")

    if title.strip():
        rel_comp = Path("entities/competitors") / f"{_slug(title)}.md"
        if _write_stub(
            vault / rel_comp,
            _stub_note(
                page_type="competitor",
                name=title.strip(),
                page_id=f"entity-competitor-{_slug(title)}",
                context_lines=context,
            ),
        ):
            created.append(str(rel_comp).replace("\\", "/"))
        competitor_path = str(rel_comp).replace("\\", "/")

    return ResearchStubResult(
        agency_path=agency_path,
        competitor_path=competitor_path,
        created=tuple(created),
    )