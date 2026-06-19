"""idea_capturer skill — fleeting thought → vault candidate + maintainer gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.services.capture_fab import (
    CaptureContext,
    build_capture_citations,
    build_capture_context,
    parse_opp_id,
)
from thread.services.capture_title import infer_capture_title
from thread.services.vault_candidate_polish import ingest_polish_candidate
from thread.services.vault_write import (
    VaultWriteError,
    load_candidate_note,
    queue_vault_candidate_review,
    write_candidate_note,
)


class IdeaCaptureError(Exception):
    pass


@dataclass(frozen=True)
class VaultMaintainerGate:
    ok: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class IdeaCaptureResult:
    candidate_path: str
    title: str
    review_id: uuid.UUID | None
    gate: VaultMaintainerGate
    title_provider: str
    polish_provider: str
    inbox_href: str


def vault_maintainer_gate(loaded: dict) -> VaultMaintainerGate:
    """Minimal ingest checklist from vault_maintainer SKILL — single candidate."""
    issues: list[str] = []
    if not str(loaded.get("name") or "").strip():
        issues.append("missing frontmatter name")
    if not str(loaded.get("page_type") or "").strip():
        issues.append("missing page_type")
    body = str(loaded.get("body") or "").strip()
    if not body:
        issues.append("empty body after polish")
    related = loaded.get("related") or []
    if "capture-llm-wiki" not in related:
        issues.append("Related missing capture-llm-wiki hub")
    citations = str(loaded.get("citations") or "")
    if "source:" not in citations:
        issues.append("citations missing source: provenance")
    return VaultMaintainerGate(ok=not issues, issues=tuple(issues))


def _parse_tags(raw: str) -> tuple[str, ...]:
    tags: list[str] = []
    for part in (raw or "").replace(";", ",").split(","):
        token = part.strip().lstrip("#")
        if token and token not in tags:
            tags.append(token)
    return tuple(tags)


def structure_fleeting_body(
    *,
    idea_text: str,
    context: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    """Zettelkasten Tier 1 sections — vault_maintainer friendly."""
    lines = ["> [!note] Fleeting capture — Tier 1", "", "## Idea", idea_text.strip()]
    if context.strip():
        lines.extend(["", "## Context", context.strip()])
    if tags:
        lines.extend(["", "## Tags", ", ".join(f"`{tag}`" for tag in tags)])
    lines.extend(["", "## Next action", "Review in Vault Inbox — develop, merge, or reject."])
    return "\n".join(lines)


async def capture_idea_to_vault(
    settings: Settings,
    session: AsyncSession,
    *,
    dump: str,
    tags: str = "",
    context_note: str = "",
    capture_context: CaptureContext | None = None,
) -> IdeaCaptureResult:
    raw = (dump or "").strip()
    if not raw:
        raise IdeaCaptureError("Dump required — fleeting thought, bullet, or paragraph")

    ctx = capture_context or build_capture_context()
    tag_tuple = _parse_tags(tags)

    inferred = await infer_capture_title(
        settings,
        raw,
        page_type="synthesis",
    )
    polished_idea, polish_provider = await ingest_polish_candidate(
        settings,
        {
            "name": inferred.title,
            "page_type": inferred.page_type or "synthesis",
            "body": raw,
            "related": [],
        },
    )
    idea_body = structure_fleeting_body(
        idea_text=polished_idea.body or raw,
        context=context_note.strip() or ctx.context_label,
        tags=tag_tuple,
    )
    citations = build_capture_citations(
        opp_id=ctx.opp_id,
        award_key=ctx.award_key,
        entity=ctx.entity,
    )
    if "source:idea_capturer" not in citations:
        citations = f"{citations},source:idea_capturer" if citations else "source:idea_capturer"

    try:
        write_result = write_candidate_note(
            settings,
            name=inferred.title,
            body=idea_body,
            page_type=inferred.page_type or "synthesis",
            citations=citations,
            related=["capture-llm-wiki"],
            source="idea_capturer",
        )
    except VaultWriteError as exc:
        raise IdeaCaptureError(str(exc)) from exc

    loaded = load_candidate_note(settings, write_result.path)
    gate = vault_maintainer_gate(loaded)

    review_id: uuid.UUID | None = None
    if gate.ok:
        record = await queue_vault_candidate_review(
            session,
            candidate_path=write_result.path,
            target_path=None,
            opportunity_id=parse_opp_id(ctx.opp_id),
        )
        await session.flush()
        review_id = record.id

    inbox_href = "/knowledge#knowledge-vault-inbox"
    if review_id:
        inbox_href = f"/knowledge?inbox={review_id}#knowledge-vault-inbox"

    return IdeaCaptureResult(
        candidate_path=write_result.path,
        title=loaded["name"],
        review_id=review_id,
        gate=gate,
        title_provider=inferred.provider,
        polish_provider=polish_provider or ingest_provider,
        inbox_href=inbox_href,
    )