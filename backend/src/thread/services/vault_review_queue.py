"""Vault candidate review queue — Knowledge page ingest lane."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import ReviewRecord
from thread.services.review_gate import list_pending_reviews
from thread.services.vault_sandbox import is_test_marked
from thread.services.vault_candidate_enrich import AutoEnrichPlan, infer_auto_enrich
from thread.services.vault_dedup import (
    DedupHint,
    MergeTargetOption,
    build_merge_target_options,
    find_dedup_hints,
    resolve_auto_promote_target,
)
from thread.services.mineru_reparse import (
    ingest_id_from_citations,
    mineru_parse_failed_in_body,
)
from thread.services.vault_inbox_display import (
    build_intent_line,
    display_title,
    extract_dump_snippet,
    promote_destination_label,
)
from thread.services.vault_link_index import VaultStemOption, build_vault_stem_options
from thread.services.vault_write import (
    VaultWriteError,
    _extract_candidate_parts,
    _infer_promote_target,
    _parse_frontmatter,
    _provenance_target,
    _vault_root,
    load_candidate_note,
)

_PREVIEW_LIMIT = 480
_STALE_VAULT_HOURS = 72
_CANDIDATE_QUOTE_RE = re.compile(r"^>\s*Candidate.*$", re.MULTILINE)


@dataclass(frozen=True)
class VaultReviewItem:
    review_id: uuid.UUID
    candidate_path: str
    title: str
    page_type: str
    promote_target: str
    body_preview: str
    snippet: str
    intent_line: str
    destination_label: str
    queue_position: int
    is_test: bool
    created_at: datetime | None
    is_highlighted: bool = False
    dedup_hints: tuple[DedupHint, ...] = ()
    merge_targets: tuple[MergeTargetOption, ...] = ()
    auto_promote_target: str = ""
    auto_promote_summary: str = ""
    auto_enrich: AutoEnrichPlan | None = None
    mineru_reparse_ingest_id: str = ""
    mineru_parse_failed: bool = False


@dataclass(frozen=True)
class CandidateEditForm:
    review_id: uuid.UUID
    candidate_path: str
    name: str
    page_type: str
    body: str
    related: tuple[str, ...]
    promote_target: str
    merge_targets: tuple[MergeTargetOption, ...] = ()
    stem_options: tuple[VaultStemOption, ...] = ()
    related_custom: str = ""


@dataclass(frozen=True)
class VaultReviewWidget:
    count: int
    production_count: int
    test_count: int
    production_items: tuple[VaultReviewItem, ...]
    test_items: tuple[VaultReviewItem, ...]
    needs_attention: bool

    @property
    def items(self) -> tuple[VaultReviewItem, ...]:
        return self.production_items + self.test_items


@dataclass(frozen=True)
class StaleVaultReviewWidget:
    count: int
    preview: tuple[VaultReviewItem, ...]
    needs_attention: bool
    stale_hours: int = _STALE_VAULT_HOURS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hours_waiting(created_at: datetime | None, *, now: datetime | None = None) -> float:
    if created_at is None:
        return 0.0
    anchor = now or _utc_now()
    return max(0.0, (anchor - _as_utc(created_at)).total_seconds() / 3600.0)


def _is_stale_vault_record(record: ReviewRecord, *, stale_hours: int, now: datetime) -> bool:
    if record.entity_type != "vault_candidate" or record.created_at is None:
        return False
    return _hours_waiting(record.created_at, now=now) >= stale_hours


def _clip_body(text: str, limit: int = _PREVIEW_LIMIT) -> str:
    clean = _CANDIDATE_QUOTE_RE.sub("", text).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _load_candidate_preview(
    settings: Settings,
    record: ReviewRecord,
    *,
    queue_position: int = 1,
    highlight_review_id: uuid.UUID | None = None,
) -> VaultReviewItem | None:
    candidate_rel = record.entity_id.replace("\\", "/")
    vault = _vault_root(settings)
    path = vault / candidate_rel
    meta: dict[str, str] = {}
    body = ""
    if path.is_file():
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))

    target = _provenance_target(record.provenance) or _infer_promote_target(candidate_rel, meta)
    raw_name = meta.get("name") or Path(candidate_rel).stem
    title = display_title(raw_name, candidate_path=candidate_rel)
    page_type = meta.get("type") or "synthesis"
    is_test = is_test_marked(
        meta=meta,
        rel_path=candidate_rel,
        citations=meta.get("citations", ""),
        page_id=meta.get("id", ""),
    )

    dedup = find_dedup_hints(
        settings,
        candidate_rel=candidate_rel,
        meta=meta,
        body=body,
        default_target=target,
    )
    merge_targets = build_merge_target_options(target, dedup, meta=meta, candidate_rel=candidate_rel)
    auto_target, auto_summary = resolve_auto_promote_target(target, dedup, merge_targets)

    editable_body, _ = _extract_candidate_parts(body)
    snippet = (
        extract_dump_snippet(editable_body or body)
        or _clip_body(editable_body or body)
        or "(no preview — open Advanced to edit)"
    )
    citations = meta.get("citations", "")
    ingest_id = ingest_id_from_citations(citations)
    parse_failed = mineru_parse_failed_in_body(body)
    return VaultReviewItem(
        review_id=record.id,
        candidate_path=candidate_rel,
        title=title,
        page_type=page_type,
        promote_target=target,
        body_preview=_clip_body(body) or snippet,
        snippet=snippet,
        intent_line=build_intent_line(
            page_type=page_type,
            title=title,
            promote_summary=auto_summary,
        ),
        destination_label=promote_destination_label(auto_target),
        queue_position=queue_position,
        is_test=is_test,
        created_at=record.created_at,
        is_highlighted=highlight_review_id is not None and record.id == highlight_review_id,
        dedup_hints=dedup,
        merge_targets=merge_targets,
        auto_promote_target=auto_target,
        auto_promote_summary=auto_summary,
        auto_enrich=infer_auto_enrich(page_type=page_type, title=title),
        mineru_reparse_ingest_id=ingest_id if parse_failed else "",
        mineru_parse_failed=parse_failed and bool(ingest_id),
    )


def load_candidate_edit_form(settings: Settings, record: ReviewRecord) -> CandidateEditForm | None:
    if record.entity_type != "vault_candidate":
        return None
    try:
        loaded = load_candidate_note(settings, record.entity_id)
    except VaultWriteError:
        return None
    meta: dict[str, str] = {}
    vault = _vault_root(settings)
    path = vault / record.entity_id.replace("\\", "/")
    if path.is_file():
        meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
    target = _provenance_target(record.provenance) or _infer_promote_target(
        record.entity_id.replace("\\", "/"),
        meta,
    )
    dedup = find_dedup_hints(
        settings,
        candidate_rel=loaded["candidate_path"],
        meta=meta,
        body=loaded["body"],
        default_target=target,
    )
    merge_targets = build_merge_target_options(
        target,
        dedup,
        meta=meta,
        candidate_rel=loaded["candidate_path"],
    )
    stem_options = build_vault_stem_options(vault)
    known_stems = {option.stem for option in stem_options}
    related_custom = ", ".join(
        link for link in loaded["related"] if link not in known_stems
    )
    return CandidateEditForm(
        review_id=record.id,
        candidate_path=loaded["candidate_path"],
        name=loaded["name"],
        page_type=loaded["page_type"],
        body=loaded["body"],
        related=tuple(loaded["related"]),
        promote_target=target,
        merge_targets=merge_targets,
        stem_options=stem_options,
        related_custom=related_custom,
    )


def reject_vault_candidate(settings: Settings, candidate_rel: str) -> bool:
    """Move a rejected candidate note to generated-projections/rejected/."""
    rel = candidate_rel.replace("\\", "/")
    vault = _vault_root(settings)
    source = vault / rel
    if not source.is_file():
        return False
    rejected_dir = vault / "generated-projections" / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)
    dest = rejected_dir / source.name
    if dest.exists():
        dest = rejected_dir / f"{source.stem}-rejected{source.suffix}"
    source.rename(dest)
    return True


async def build_vault_review_widget(
    session: AsyncSession,
    settings: Settings,
    *,
    highlight_review_id: uuid.UUID | None = None,
) -> VaultReviewWidget:
    pending = await list_pending_reviews(session)
    vault_records = [r for r in pending if r.entity_type == "vault_candidate"]
    vault_records.sort(key=lambda r: r.created_at, reverse=True)

    all_items: list[VaultReviewItem] = []
    for record in vault_records:
        item = _load_candidate_preview(
            settings,
            record,
            highlight_review_id=highlight_review_id,
        )
        if item:
            all_items.append(item)

    production_raw = [item for item in all_items if not item.is_test]
    test_raw = [item for item in all_items if item.is_test]

    def _renumber(rows: list[VaultReviewItem]) -> tuple[VaultReviewItem, ...]:
        out: list[VaultReviewItem] = []
        for index, item in enumerate(rows, start=1):
            out.append(
                VaultReviewItem(
                    review_id=item.review_id,
                    candidate_path=item.candidate_path,
                    title=item.title,
                    page_type=item.page_type,
                    promote_target=item.promote_target,
                    body_preview=item.body_preview,
                    snippet=item.snippet,
                    intent_line=item.intent_line,
                    destination_label=item.destination_label,
                    queue_position=index,
                    is_test=item.is_test,
                    created_at=item.created_at,
                    is_highlighted=item.is_highlighted,
                    dedup_hints=item.dedup_hints,
                    merge_targets=item.merge_targets,
                    auto_promote_target=item.auto_promote_target,
                    auto_promote_summary=item.auto_promote_summary,
                    auto_enrich=item.auto_enrich,
                )
            )
        return tuple(out)

    production_items = _renumber(production_raw)
    test_items = _renumber(test_raw)
    count = len(production_items) + len(test_items)
    return VaultReviewWidget(
        count=count,
        production_count=len(production_items),
        test_count=len(test_items),
        production_items=production_items,
        test_items=test_items,
        needs_attention=count > 0,
    )


async def build_stale_vault_review_widget(
    session: AsyncSession,
    settings: Settings,
    *,
    stale_hours: int = _STALE_VAULT_HOURS,
    preview_limit: int = 3,
) -> StaleVaultReviewWidget:
    pending = await list_pending_reviews(session)
    now = _utc_now()
    stale_records = [
        r
        for r in pending
        if _is_stale_vault_record(r, stale_hours=stale_hours, now=now)
    ]
    stale_records.sort(key=lambda r: r.created_at or now)

    items: list[VaultReviewItem] = []
    for record in stale_records:
        item = _load_candidate_preview(settings, record)
        if item:
            items.append(item)

    count = len(items)
    return StaleVaultReviewWidget(
        count=count,
        preview=tuple(items[:preview_limit]),
        needs_attention=count > 0,
        stale_hours=stale_hours,
    )