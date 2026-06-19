"""Human-readable review queue — titles, excerpts, opp-scoped and global."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import CapabilityRun, Opportunity, PacketFieldAnswer, PacketFieldDefinition, ReviewRecord
from thread.services.review_gate import list_pending_reviews
from thread.services.vault_review_context import resolve_review_vault_context


@dataclass(frozen=True)
class ReviewQueueItem:
    review_id: uuid.UUID
    entity_type: str
    title: str
    subtitle: str
    excerpt: str
    source_ref: str | None = None
    trust_level: str = "candidate"
    opportunity_id: uuid.UUID | None = None
    opportunity_name: str | None = None


@dataclass(frozen=True)
class PendingReviewsWidget:
    count: int
    preview: tuple[ReviewQueueItem, ...]
    needs_attention: bool


def _clip(text: str | None, limit: int = 320) -> str:
    if not text:
        return ""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _provenance_excerpt(provenance: list | None) -> tuple[str | None, str | None]:
    if not provenance:
        return None, None
    for item in provenance:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        excerpt = item.get("excerpt")
        if ref and str(ref).startswith("http"):
            return str(ref), _clip(str(excerpt) if excerpt else None, 200)
        if excerpt:
            return str(ref) if ref else None, _clip(str(excerpt), 200)
    first = provenance[0] if provenance else {}
    if isinstance(first, dict):
        return (
            str(first.get("ref")) if first.get("ref") else None,
            _clip(str(first.get("excerpt") or ""), 200) or None,
        )
    return None, None


def _load_research_run(settings: Settings, run_id: str) -> dict[str, Any] | None:
    path = settings.resolve(settings.thread_state_dir) / "research" / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _opportunity_id_from_run(run: dict[str, Any]) -> uuid.UUID | None:
    for src in run.get("sources", []):
        if not isinstance(src, dict):
            continue
        if src.get("meta") == "opportunity_id" and src.get("value"):
            try:
                return uuid.UUID(str(src["value"]))
            except ValueError:
                continue
    return None


def _run_for_opportunity(run: dict[str, Any], opp_id: uuid.UUID) -> bool:
    resolved = _opportunity_id_from_run(run)
    return resolved == opp_id


def _parse_research_entity(entity_id: str) -> tuple[str | None, str | None, int | None]:
    if ":finding:" in entity_id:
        run_id, _, idx = entity_id.partition(":finding:")
        try:
            return run_id, "finding", int(idx)
        except ValueError:
            return run_id, "finding", None
    if entity_id.endswith(":interpretation"):
        return entity_id[: -len(":interpretation")], "interpretation", None
    return None, None, None


def _entity_type_label(entity_type: str) -> str:
    if entity_type == "vault_candidate":
        return "Vault candidate"
    return {
        "packet_field_answer": "Packet field",
        "research_finding": "Research finding",
        "research_interpretation": "Research synthesis",
        "skill_run": "Skill output",
    }.get(entity_type, entity_type.replace("_", " ").title())


async def _field_labels(session: AsyncSession) -> dict[str, str]:
    return {
        row.key: row.label
        for row in (await session.execute(select(PacketFieldDefinition))).scalars().all()
    }


async def _attach_opportunity(
    session: AsyncSession,
    item: ReviewQueueItem,
    opportunity_id: uuid.UUID | None,
) -> ReviewQueueItem:
    if opportunity_id is None:
        return item
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        return item
    return ReviewQueueItem(
        review_id=item.review_id,
        entity_type=item.entity_type,
        title=item.title,
        subtitle=item.subtitle,
        excerpt=item.excerpt,
        source_ref=item.source_ref,
        trust_level=item.trust_level,
        opportunity_id=opportunity_id,
        opportunity_name=opp.name,
    )


async def _resolve_opportunity_id(
    session: AsyncSession,
    settings: Settings,
    record: ReviewRecord,
) -> uuid.UUID | None:
    ctx = await resolve_review_vault_context(session, settings, record)
    return ctx.opportunity_id


async def build_review_queue(
    session: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
) -> list[ReviewQueueItem]:
    field_labels = await _field_labels(session)
    items: list[ReviewQueueItem] = []

    for record in await list_pending_reviews(session):
        item = await _enrich_review(
            session,
            settings,
            record,
            field_labels,
            scoped_opp_id=opp_id,
        )
        if item:
            items.append(item)

    return sorted(items, key=lambda i: (i.entity_type, i.title))


async def build_global_review_queue(
    session: AsyncSession,
    settings: Settings,
) -> list[ReviewQueueItem]:
    field_labels = await _field_labels(session)
    pending = await list_pending_reviews(session)
    pending.sort(key=lambda r: r.created_at, reverse=True)
    items: list[ReviewQueueItem] = []

    for record in pending:
        if record.entity_type == "vault_candidate":
            continue
        item = await _enrich_review(session, settings, record, field_labels)
        if item:
            items.append(item)

    return items


async def build_pending_reviews_widget(
    session: AsyncSession,
    settings: Settings,
    *,
    preview_limit: int = 3,
) -> PendingReviewsWidget:
    items = await build_global_review_queue(session, settings)
    count = len(items)
    return PendingReviewsWidget(
        count=count,
        preview=tuple(items[:preview_limit]),
        needs_attention=count > 0,
    )


async def _enrich_review(
    session: AsyncSession,
    settings: Settings,
    record: ReviewRecord,
    field_labels: dict[str, str],
    *,
    scoped_opp_id: uuid.UUID | None = None,
) -> ReviewQueueItem | None:
    prov_ref, prov_excerpt = _provenance_excerpt(record.provenance)
    type_label = _entity_type_label(record.entity_type)
    resolved_opp = await _resolve_opportunity_id(session, settings, record)

    if scoped_opp_id is not None:
        if record.entity_type == "packet_field_answer":
            if resolved_opp != scoped_opp_id:
                return None
        elif record.entity_type in ("research_finding", "research_interpretation"):
            run_id, _, _ = _parse_research_entity(record.entity_id)
            if not run_id:
                return None
            run = _load_research_run(settings, run_id)
            if not run or not _run_for_opportunity(run, scoped_opp_id):
                return None
        elif record.entity_type == "skill_run":
            if resolved_opp is not None and resolved_opp != scoped_opp_id:
                return None

    if record.entity_type == "packet_field_answer":
        try:
            answer_id = uuid.UUID(record.entity_id)
        except ValueError:
            return None
        answer = await session.get(PacketFieldAnswer, answer_id)
        if not answer:
            return None
        label = field_labels.get(answer.field_key, answer.field_key.replace("_", " ").title())
        item = ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=label,
            subtitle=f"{type_label} · {answer.field_key}",
            excerpt=_clip(answer.value) or "(empty value)",
            source_ref=prov_ref or "manual edit",
            trust_level=record.trust_level,
        )
        return await _attach_opportunity(session, item, answer.opportunity_id)

    if record.entity_type in ("research_finding", "research_interpretation"):
        run_id, kind, idx = _parse_research_entity(record.entity_id)
        if not run_id:
            return None
        run = _load_research_run(settings, run_id)
        if not run:
            return None
        if scoped_opp_id is not None and not _run_for_opportunity(run, scoped_opp_id):
            return None
        lens = str(run.get("lens", "research")).replace("_", " ")
        query = str(run.get("query", ""))
        opp_id = _opportunity_id_from_run(run)

        if kind == "interpretation":
            text = str(run.get("interpretation") or prov_excerpt or "")
            item = ReviewQueueItem(
                review_id=record.id,
                entity_type=record.entity_type,
                title=f"Synthesis: {query[:80]}",
                subtitle=f"{type_label} · {lens}",
                excerpt=_clip(text) or "(no interpretation text)",
                source_ref=prov_ref or f"research run {run_id[:8]}",
                trust_level=record.trust_level,
            )
            return await _attach_opportunity(session, item, opp_id)

        findings = run.get("findings") or []
        finding: dict[str, Any] = {}
        if idx is not None and 0 <= idx < len(findings) and isinstance(findings[idx], dict):
            finding = findings[idx]
        title = str(finding.get("title") or f"Finding {idx}")
        summary = str(finding.get("summary") or prov_excerpt or "")
        url = None
        for link in finding.get("provenance") or []:
            if isinstance(link, dict) and str(link.get("ref", "")).startswith("http"):
                url = str(link["ref"])
                break
        item = ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=title,
            subtitle=f"{type_label} · {lens} · “{query[:60]}”",
            excerpt=_clip(summary) or "(no excerpt)",
            source_ref=url or prov_ref,
            trust_level=record.trust_level,
        )
        return await _attach_opportunity(session, item, opp_id)

    if record.entity_type == "vault_candidate":
        target = None
        for prov in record.provenance or []:
            if isinstance(prov, dict) and prov.get("target"):
                target = str(prov["target"])
        item = ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=f"Vault: {Path(record.entity_id).name}",
            subtitle=f"{type_label} → {target or 'auto-merge'}",
            excerpt=_clip(record.entity_id) or "(candidate page)",
            source_ref=target or prov_ref,
            trust_level=record.trust_level,
        )
        return await _attach_opportunity(session, item, resolved_opp)

    if record.entity_type == "skill_run":
        run_key, _, skill_id = record.entity_id.partition(":")
        if not skill_id:
            skill_id = run_key
        try:
            cap_id = uuid.UUID(run_key)
            cap_run = await session.get(CapabilityRun, cap_id)
        except ValueError:
            cap_run = None
        skill_id = cap_run.skill_id if cap_run else skill_id
        transcript = (cap_run.transcript or {}) if cap_run else {}
        output = transcript.get("output") if isinstance(transcript, dict) else {}
        excerpt = ""
        if isinstance(output, dict):
            if output.get("output"):
                excerpt = _clip(str(output["output"]))
            elif output.get("contracts"):
                excerpt = f"{len(output['contracts'])} contracts returned"
            elif output.get("message"):
                excerpt = _clip(str(output["message"]))
            else:
                excerpt = _clip(str(output))
        item = ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=f"Skill: {skill_id}",
            subtitle=type_label,
            excerpt=excerpt or prov_excerpt or "(no output preview)",
            source_ref=prov_ref,
            trust_level=record.trust_level,
        )
        return await _attach_opportunity(session, item, resolved_opp)

    item = ReviewQueueItem(
        review_id=record.id,
        entity_type=record.entity_type,
        title=type_label,
        subtitle=record.entity_id[:48],
        excerpt=prov_excerpt or "(no preview)",
        source_ref=prov_ref,
        trust_level=record.trust_level,
    )
    return await _attach_opportunity(session, item, resolved_opp)