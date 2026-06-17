"""Human-readable review queue — titles, excerpts, opp-scoped."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import CapabilityRun, PacketFieldAnswer, PacketFieldDefinition, ReviewRecord
from thread.services.review_gate import list_pending_reviews


@dataclass(frozen=True)
class ReviewQueueItem:
    review_id: uuid.UUID
    entity_type: str
    title: str
    subtitle: str
    excerpt: str
    source_ref: str | None = None
    trust_level: str = "candidate"


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


def _run_for_opportunity(run: dict[str, Any], opp_id: uuid.UUID) -> bool:
    opp_str = str(opp_id)
    for src in run.get("sources", []):
        if isinstance(src, dict) and src.get("meta") == "opportunity_id" and src.get("value") == opp_str:
            return True
    return False


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
    return {
        "packet_field_answer": "Packet field",
        "research_finding": "Research finding",
        "research_interpretation": "Research synthesis",
        "skill_run": "Skill output",
    }.get(entity_type, entity_type.replace("_", " ").title())


async def build_review_queue(
    session: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
) -> list[ReviewQueueItem]:
    pending = await list_pending_reviews(session)
    field_labels = {
        row.key: row.label
        for row in (await session.execute(select(PacketFieldDefinition))).scalars().all()
    }
    items: list[ReviewQueueItem] = []

    for record in pending:
        item = await _enrich_review(session, settings, opp_id, record, field_labels)
        if item:
            items.append(item)

    return sorted(items, key=lambda i: (i.entity_type, i.title))


async def _enrich_review(
    session: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
    record: ReviewRecord,
    field_labels: dict[str, str],
) -> ReviewQueueItem | None:
    prov_ref, prov_excerpt = _provenance_excerpt(record.provenance)
    type_label = _entity_type_label(record.entity_type)

    if record.entity_type == "packet_field_answer":
        try:
            answer_id = uuid.UUID(record.entity_id)
        except ValueError:
            return None
        answer = await session.get(PacketFieldAnswer, answer_id)
        if not answer or answer.opportunity_id != opp_id:
            return None
        label = field_labels.get(answer.field_key, answer.field_key.replace("_", " ").title())
        return ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=label,
            subtitle=f"{type_label} · {answer.field_key}",
            excerpt=_clip(answer.value) or "(empty value)",
            source_ref=prov_ref or "manual edit",
            trust_level=record.trust_level,
        )

    if record.entity_type in ("research_finding", "research_interpretation"):
        run_id, kind, idx = _parse_research_entity(record.entity_id)
        if not run_id:
            return None
        run = _load_research_run(settings, run_id)
        if not run or not _run_for_opportunity(run, opp_id):
            return None
        lens = str(run.get("lens", "research")).replace("_", " ")
        query = str(run.get("query", ""))

        if kind == "interpretation":
            text = str(run.get("interpretation") or prov_excerpt or "")
            return ReviewQueueItem(
                review_id=record.id,
                entity_type=record.entity_type,
                title=f"Synthesis: {query[:80]}",
                subtitle=f"{type_label} · {lens}",
                excerpt=_clip(text) or "(no interpretation text)",
                source_ref=prov_ref or f"research run {run_id[:8]}",
                trust_level=record.trust_level,
            )

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
        return ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=title,
            subtitle=f"{type_label} · {lens} · “{query[:60]}”",
            excerpt=_clip(summary) or "(no excerpt)",
            source_ref=url or prov_ref,
            trust_level=record.trust_level,
        )

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
        return ReviewQueueItem(
            review_id=record.id,
            entity_type=record.entity_type,
            title=f"Skill: {skill_id}",
            subtitle=type_label,
            excerpt=excerpt or prov_excerpt or "(no output preview)",
            source_ref=prov_ref,
            trust_level=record.trust_level,
        )

    return None