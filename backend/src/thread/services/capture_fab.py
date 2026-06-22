"""Global capture FAB — dump thoughts; platform infers schema and polishes."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.services.mineru_stub import DocumentExtract, MineruIngestError, extract_document_for_capture
from thread.services.capture_title import infer_capture_title
from thread.services.vault_candidate_polish import (
    PolishedCandidate,
    apply_polished_candidate,
    ingest_polish_candidate,
    rules_polish_candidate,
)
from thread.services.vault_inbox_display import extract_dump_snippet
from thread.services.vault_review_queue import build_vault_review_widget
from thread.services.vault_sandbox import is_sandbox_path
from thread.services.vault_write import (
    VaultWriteError,
    VaultWriteResult,
    load_candidate_note,
    queue_vault_candidate_review,
    write_candidate_note,
)

_MAX_TITLE = 72


class CaptureFabError(Exception):
    pass


@dataclass(frozen=True)
class CaptureContext:
    context_label: str
    opp_id: str = ""
    opp_name: str = ""
    award_key: str = ""
    signal_title: str = ""
    agency: str = ""
    entity: str = ""
    entity_title: str = ""


@dataclass(frozen=True)
class QuickCaptureDraft:
    name: str
    body: str
    page_type: str
    related: tuple[str, ...]


@dataclass(frozen=True)
class QuickCaptureResult:
    write: VaultWriteResult
    polish_provider: str
    inferred_title: str
    review_id: uuid.UUID | None = None
    queue_position: int = 0
    queue_total: int = 0
    inbox_lane: str = "production"
    title_provider: str = "rules"
    dump_snippet: str = ""
    document_name: str = ""
    mineru_status: str = ""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _stem_from_entity(entity: str) -> str:
    return Path(entity.replace("\\", "/")).stem.replace("-", " ").title()


def _page_type_for_entity(entity: str) -> str:
    rel = entity.replace("\\", "/").lower()
    if "/agencies/" in rel or rel.startswith("entities/agencies/"):
        return "agency"
    if "/competitors/" in rel or rel.startswith("entities/competitors/"):
        return "competitor"
    if "/pursuits/" in rel:
        return "opportunity"
    return "synthesis"


def build_capture_context(
    *,
    opp_id: str = "",
    opp_name: str = "",
    award_key: str = "",
    signal_title: str = "",
    agency: str = "",
    entity: str = "",
    entity_title: str = "",
) -> CaptureContext:
    """Page context for hidden prefill — operator never edits this."""
    opp_id = _clean(opp_id)
    opp_name = _clean(opp_name)
    award_key = _clean(award_key)
    signal_title = _clean(signal_title)
    agency = _clean(agency)
    entity = _clean(entity).replace("\\", "/")
    entity_title = _clean(entity_title)

    if opp_id and opp_name:
        label = f"Pursuit · {opp_name[:48]}"
    elif award_key:
        title = signal_title or award_key[:32]
        label = f"Signal · {title[:48]}"
    elif entity:
        label = f"Vault · {(entity_title or _stem_from_entity(entity))[:48]}"
    else:
        label = "Any lane"

    return CaptureContext(
        context_label=label,
        opp_id=opp_id,
        opp_name=opp_name,
        award_key=award_key,
        signal_title=signal_title,
        agency=agency,
        entity=entity,
        entity_title=entity_title,
    )


# Back-compat alias for templates/tests migrating gradually
def build_capture_prefill(**kwargs: str) -> CaptureContext:
    return build_capture_context(**kwargs)


def infer_title_from_dump(dump: str, *, fallback: str = "") -> str:
    for line in dump.splitlines():
        clean = re.sub(r"^#+\s*", "", line.strip())
        clean = re.sub(r"^[-*]\s+", "", clean)
        if len(clean) >= 3:
            return clean[:_MAX_TITLE]
    if fallback:
        return fallback[:_MAX_TITLE]
    return f"Quick capture {date.today().isoformat()}"


def infer_page_type_from_dump(dump: str, *, context: CaptureContext) -> str:
    if context.entity:
        return _page_type_for_entity(context.entity)
    low = dump.lower()
    if any(token in low for token in ("competitor", "incumbent", "prime contractor")):
        return "competitor"
    if any(token in low for token in ("agency", "department of", "command", "corps")):
        return "agency"
    if any(token in low for token in ("pursuit", "opportunity", "capture plan", "idiq")):
        return "opportunity"
    if any(token in low for token in ("framework", "process", "playbook")):
        return "concept"
    return "synthesis"


def infer_related_links(context: CaptureContext) -> tuple[str, ...]:
    related: list[str] = []
    if context.entity:
        stem = Path(context.entity.replace("\\", "/")).stem
        if stem and stem not in related:
            related.append(stem)
    if context.opp_name:
        slug = re.sub(r"[^a-z0-9]+", "-", context.opp_name.lower()).strip("-")[:48]
        if slug and slug not in related:
            related.append(slug)
    return tuple(related)


def _context_footer(context: CaptureContext) -> str:
    lines: list[str] = []
    if context.opp_id and context.opp_name:
        lines.append(f"> Context · pursuit **{context.opp_name}** (`{context.opp_id}`)")
    elif context.award_key:
        title = context.signal_title or context.award_key
        lines.append(f"> Context · signal **{title}** (`{context.award_key}`)")
        if context.agency:
            lines.append(f"> Agency · {context.agency}")
    elif context.entity:
        label = context.entity_title or _stem_from_entity(context.entity)
        lines.append(f"> Context · vault **{label}** (`{context.entity}`)")
    if not lines:
        return ""
    return "\n".join(lines)


def prepare_quick_capture(
    raw_dump: str,
    *,
    context: CaptureContext,
    document: DocumentExtract | None = None,
) -> QuickCaptureDraft:
    dump = _clean(raw_dump)
    if not dump and not document:
        raise CaptureFabError("Dump a thought or drop a document — platform handles the rest")

    parts: list[str] = []
    if dump:
        parts.append(dump)
    if document:
        parts.append(document.markdown.strip())

    body = "\n\n".join(parts)
    footer = _context_footer(context)
    if footer:
        body = f"{body.rstrip()}\n\n{footer}\n"

    fallback_title = ""
    if context.opp_name:
        fallback_title = context.opp_name
    elif context.signal_title:
        fallback_title = context.signal_title
    elif context.entity_title:
        fallback_title = context.entity_title
    elif document:
        fallback_title = Path(document.filename).stem.replace("-", " ").replace("_", " ").title()

    infer_source = dump or (document.markdown if document else "")
    name = infer_title_from_dump(infer_source, fallback=fallback_title)
    page_type = infer_page_type_from_dump(infer_source, context=context)
    related = infer_related_links(context)

    return QuickCaptureDraft(
        name=name,
        body=body,
        page_type=page_type,
        related=related,
    )


def build_capture_citations(
    *,
    opp_id: str = "",
    award_key: str = "",
    entity: str = "",
    ingest_id: str = "",
    ingest_rel: str = "",
) -> str:
    parts = ["source:fabric"]
    if opp_id:
        parts.append(f"opp:{opp_id}")
    if award_key:
        parts.append(f"award_key:{award_key}")
    if entity:
        safe = re.sub(r"[^a-zA-Z0-9_./-]", "", entity.replace("\\", "/"))
        if safe:
            parts.append(f"entity:{safe}")
    if ingest_id:
        parts.append(f"ingest:{ingest_id}")
    if ingest_rel:
        safe_rel = re.sub(r"[^a-zA-Z0-9_./-]", "", ingest_rel.replace("\\", "/"))
        if safe_rel:
            parts.append(f"ingest_path:{safe_rel}")
    return ";".join(parts)


def format_document_status_note(*, filename: str, mineru_status: str) -> str:
    """Human-readable document line for capture FAB success flash."""
    name = filename or "document"
    status = (mineru_status or "").strip().lower()
    if status == "mineru":
        return f"{name} — parsed with MinerU (GPU). Full markdown on disk."
    if status in {"mineru_parsed", "parsed"}:
        return f"{name} — parsed with MinerU. Full markdown on disk."
    if status == "mineru_error":
        return f"{name} — staged; MinerU parse failed (file kept). Approve in Vault Inbox or re-upload."
    if status == "mineru_stub":
        return f"{name} — staged only (MinerU disabled)."
    if status == "inline_text":
        return f"{name} — text file attached."
    if status:
        return f"{name} — {status}."
    return f"{name} — attached."


def parse_opp_id(raw: str) -> uuid.UUID | None:
    clean = _clean(raw)
    if not clean:
        return None
    try:
        return uuid.UUID(clean)
    except ValueError:
        return None


async def ingest_quick_capture(
    settings: Settings,
    session: AsyncSession,
    *,
    raw_dump: str,
    context: CaptureContext,
    attachment_name: str = "",
    attachment_bytes: bytes = b"",
    queue_review: bool = True,
) -> QuickCaptureResult:
    """Write candidate, auto-polish, queue Capture Studio — operator approves later."""
    document: DocumentExtract | None = None
    if attachment_name and attachment_bytes:
        try:
            document = extract_document_for_capture(settings, attachment_name, attachment_bytes)
        except MineruIngestError as exc:
            raise CaptureFabError(str(exc)) from exc

    draft = prepare_quick_capture(raw_dump, context=context, document=document)
    infer_source = _clean(raw_dump) or (document.markdown if document else "")
    document_only = bool(document) and not _clean(raw_dump)
    inferred = await infer_capture_title(
        settings,
        infer_source,
        fallback=draft.name,
        page_type=draft.page_type,
        quick=document_only,
    )
    draft = QuickCaptureDraft(
        name=inferred.title,
        body=draft.body,
        page_type=inferred.page_type or draft.page_type,
        related=draft.related,
    )
    citations = build_capture_citations(
        opp_id=context.opp_id,
        award_key=context.award_key,
        entity=context.entity,
        ingest_id=document.ingest_id if document else "",
        ingest_rel=document.ingest_rel if document else "",
    )
    write_result = write_candidate_note(
        settings,
        name=draft.name,
        body=draft.body,
        page_type=draft.page_type,
        citations=citations,
        related=list(draft.related),
        source="fabric",
    )

    # Ingest polish — light typo/grammar cleanup (≤20s). Skip LLM on large MinerU bodies.
    loaded = load_candidate_note(settings, write_result.path)
    body_len = len(str(loaded.get("body") or ""))
    if body_len > 12_000:
        polished = rules_polish_candidate(loaded)
        polish_provider = "rules-large-doc"
    else:
        polished, polish_provider = await ingest_polish_candidate(settings, loaded)
    if not polished.name:
        polished = PolishedCandidate(
            name=draft.name,
            page_type=polished.page_type,
            body=polished.body,
            related=polished.related,
        )
    apply_polished_candidate(settings, write_result.path, polished)

    review_id: uuid.UUID | None = None
    queue_position = 0
    queue_total = 0
    inbox_lane = "test" if is_sandbox_path(write_result.path) else "production"
    if queue_review:
        record = await queue_vault_candidate_review(
            session,
            candidate_path=write_result.path,
            target_path=None,
            opportunity_id=parse_opp_id(context.opp_id),
        )
        await session.commit()
        review_id = record.id
        widget = await build_vault_review_widget(session, settings, highlight_review_id=review_id)
        lane_items = widget.test_items if is_sandbox_path(write_result.path) else widget.production_items
        lane_total = widget.test_count if is_sandbox_path(write_result.path) else widget.production_count
        queue_total = lane_total or widget.count
        queue_position = next(
            (item.queue_position for item in lane_items if item.review_id == review_id),
            1,
        )
    mineru_status = ""
    if document:
        mineru_status = "parsed" if document.mineru_ready and document.source_kind == "inline_text" else document.source_kind

    return QuickCaptureResult(
        write=write_result,
        polish_provider=polish_provider,
        inferred_title=polished.name or draft.name,
        review_id=review_id,
        queue_position=queue_position,
        queue_total=queue_total,
        inbox_lane=inbox_lane,
        title_provider=inferred.provider,
        dump_snippet=extract_dump_snippet(polished.body or draft.body),
        document_name=document.filename if document else "",
        mineru_status=mineru_status,
    )