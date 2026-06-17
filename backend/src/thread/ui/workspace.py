"""Workspace panel data — packet, actions, research, review."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import ActionMatrixItem, ReviewRecord
from thread.domain.enums import ResearchLens
from thread.services.review_gate import list_pending_reviews


def valid_tabs() -> tuple[str, ...]:
    return ("packet", "actions", "review", "research")


def normalize_tab(tab: str | None) -> str:
    if tab in valid_tabs():
        return tab
    return "packet"


def list_research_runs(settings: Settings, opp_id: uuid.UUID, *, limit: int = 8) -> list[dict[str, Any]]:
    runs_dir = settings.resolve(settings.thread_state_dir) / "research"
    if not runs_dir.is_dir():
        return []
    opp_str = str(opp_id)
    out: list[dict[str, Any]] = []
    paths = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tagged = any(
            s.get("meta") == "opportunity_id" and s.get("value") == opp_str
            for s in data.get("sources", [])
            if isinstance(s, dict)
        )
        if not tagged:
            continue
        out.append(data)
        if len(out) >= limit:
            break
    return out


async def load_actions(session: AsyncSession, opp_id: uuid.UUID) -> list[ActionMatrixItem]:
    rows = (
        await session.execute(
            select(ActionMatrixItem)
            .where(ActionMatrixItem.opportunity_id == opp_id)
            .order_by(ActionMatrixItem.due_date.asc().nulls_last())
        )
    ).scalars().all()
    return list(rows)


async def load_workspace_reviews(session: AsyncSession, opp_id: uuid.UUID) -> list[ReviewRecord]:
    pending = await list_pending_reviews(session)
    allowed = {"packet_field_answer", "research_finding", "research_interpretation", "skill_run"}
    return [r for r in pending if r.entity_type in allowed]


def research_lenses() -> list[tuple[str, str]]:
    labels = {
        ResearchLens.CUSTOMER_RESEARCH: "Customer research",
        ResearchLens.COMPETITIVE_POSITIONING: "Competitive positioning",
        ResearchLens.PRODUCT_POSITIONING: "Product positioning",
        ResearchLens.PRICE_TO_WIN: "Price to win",
        ResearchLens.CALL_PLAN_CRO: "Call plan / CRO",
    }
    return [(lens.value, labels.get(lens, lens.value)) for lens in ResearchLens]