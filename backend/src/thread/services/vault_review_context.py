"""Resolve opportunity context for review → vault ingest."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import Opportunity, PacketFieldAnswer, ReviewRecord


@dataclass(frozen=True)
class ReviewVaultContext:
    opportunity_id: uuid.UUID | None
    pursuit_slug: str | None
    opportunity_name: str | None


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


def _opportunity_id_from_provenance(provenance: list | None) -> uuid.UUID | None:
    if not provenance:
        return None
    for item in provenance:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "opportunity" and item.get("ref"):
            try:
                return uuid.UUID(str(item["ref"]))
            except ValueError:
                continue
    return None


async def resolve_review_vault_context(
    session: AsyncSession,
    settings: Settings,
    record: ReviewRecord,
) -> ReviewVaultContext:
    opp_id: uuid.UUID | None = None

    if record.entity_type == "packet_field_answer":
        try:
            answer = await session.get(PacketFieldAnswer, uuid.UUID(record.entity_id))
        except ValueError:
            answer = None
        if answer:
            opp_id = answer.opportunity_id

    elif record.entity_type in ("research_finding", "research_interpretation"):
        run_id = record.entity_id.split(":", 1)[0]
        run = _load_research_run(settings, run_id)
        if run:
            opp_id = _opportunity_id_from_run(run)

    elif record.entity_type == "vault_candidate":
        opp_id = _opportunity_id_from_provenance(record.provenance)

    if opp_id is None:
        return ReviewVaultContext(None, None, None)

    opp = await session.get(Opportunity, opp_id)
    if not opp:
        return ReviewVaultContext(opp_id, None, None)
    return ReviewVaultContext(opp_id, opp.slug, opp.name)