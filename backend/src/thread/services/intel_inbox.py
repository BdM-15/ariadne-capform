"""Intel inbox — Pulse morning briefing for gated candidates (12g).

GovDash-style triage: recent review-gate candidates with source-lane labels
and suggested actions. Complements global /review — preview only, not duplicate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import CapabilityRun, ReviewRecord
from thread.ui.review_display import ReviewQueueItem, build_global_review_queue

INBOX_PREVIEW_LIMIT = 8

SOURCE_LANE_LABELS: dict[str, str] = {
    "packet": "Packet",
    "research": "Research",
    "skill": "Skill",
    "mcp_sam": "SAM.gov",
    "mcp_usaspending": "USAspending",
    "mcp": "Federal MCP",
    "insights": "Data Insights",
}

INSIGHTS_SKILLS = frozenset({"clew_intel"})


@dataclass(frozen=True)
class IntelInboxItem:
    review_id: uuid.UUID
    entity_type: str
    title: str
    subtitle: str
    excerpt: str
    source_lane: str
    source_label: str
    suggested_action: str
    chain_hint: str | None
    trust_level: str = "candidate"
    opportunity_id: uuid.UUID | None = None
    opportunity_name: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class IntelInboxWidget:
    count: int
    items: tuple[IntelInboxItem, ...]
    needs_attention: bool
    lane_counts: dict[str, int]
    lane_summary: str


def _skill_id_from_item(item: ReviewQueueItem) -> str | None:
    if item.entity_type != "skill_run":
        return None
    if item.title.startswith("Skill: "):
        return item.title[len("Skill: ") :].strip()
    return None


def _mcp_server_from_run(transcript: dict[str, Any] | None) -> str | None:
    if not isinstance(transcript, dict):
        return None
    payload = transcript.get("input")
    if isinstance(payload, dict) and payload.get("server"):
        return str(payload["server"]).lower()
    output = transcript.get("output")
    if isinstance(output, dict) and output.get("server"):
        return str(output["server"]).lower()
    return None


def _lane_from_mcp_server(server: str | None) -> str:
    if not server:
        return "mcp"
    if "sam" in server:
        return "mcp_sam"
    if "usaspending" in server or "spending" in server:
        return "mcp_usaspending"
    return "mcp"


def _resolve_source_lane(
    item: ReviewQueueItem,
    *,
    skill_id: str | None = None,
    mcp_server: str | None = None,
) -> tuple[str, str, str | None]:
    """Return (lane_key, label, chain_hint)."""
    if item.entity_type == "packet_field_answer":
        return (
            "packet",
            SOURCE_LANE_LABELS["packet"],
            "Promotes to trusted packet field after approve.",
        )

    if item.entity_type in ("research_finding", "research_interpretation"):
        hint = None
        if item.opportunity_id:
            hint = "Chain (future): incumbent → SAM.gov MCP → pin to packet."
        return ("research", SOURCE_LANE_LABELS["research"], hint)

    if item.entity_type == "skill_run":
        sid = skill_id or _skill_id_from_item(item) or ""
        if sid in INSIGHTS_SKILLS:
            return (
                "insights",
                SOURCE_LANE_LABELS["insights"],
                "Relationship analytics — deep trends live on Data Insights; approve to trust this run.",
            )
        if sid == "mcp_federal_tools":
            lane = _lane_from_mcp_server(mcp_server)
            hints = {
                "mcp_sam": "SAM notice metadata → opportunity record (12i).",
                "mcp_usaspending": "Award drill-down — pair with PG radar on Pulse.",
                "mcp": "Federal MCP output — attach provenance to packet after approve.",
            }
            return (lane, SOURCE_LANE_LABELS.get(lane, SOURCE_LANE_LABELS["mcp"]), hints.get(lane))
        return ("skill", SOURCE_LANE_LABELS["skill"], "Skill output stays candidate until you approve.")

    return ("skill", item.entity_type.replace("_", " ").title(), None)


def _suggested_action(
    item: ReviewQueueItem,
    *,
    source_lane: str,
    skill_id: str | None = None,
) -> str:
    if item.entity_type == "packet_field_answer":
        return "Approve → trusted field"
    if item.entity_type == "research_interpretation":
        return "Approve → trusted synthesis"
    if item.entity_type == "research_finding":
        return "Approve → trusted finding"
    if source_lane == "insights":
        return "Approve or open Insights"
    if source_lane in ("mcp_sam", "mcp_usaspending", "mcp"):
        return "Approve → attach evidence"
    if item.entity_type == "skill_run" and skill_id:
        return f"Approve skill: {skill_id}"
    return "Approve → promote"


def _to_inbox_item(
    item: ReviewQueueItem,
    *,
    skill_id: str | None = None,
    mcp_server: str | None = None,
) -> IntelInboxItem:
    lane, label, chain_hint = _resolve_source_lane(
        item,
        skill_id=skill_id,
        mcp_server=mcp_server,
    )
    return IntelInboxItem(
        review_id=item.review_id,
        entity_type=item.entity_type,
        title=item.title,
        subtitle=item.subtitle,
        excerpt=item.excerpt,
        source_lane=lane,
        source_label=label,
        suggested_action=_suggested_action(item, source_lane=lane, skill_id=skill_id),
        chain_hint=chain_hint,
        trust_level=item.trust_level,
        opportunity_id=item.opportunity_id,
        opportunity_name=item.opportunity_name,
        source_ref=item.source_ref,
    )


async def _skill_context(
    session: AsyncSession,
    item: ReviewQueueItem,
) -> tuple[str | None, str | None]:
    if item.entity_type != "skill_run":
        return None, None

    skill_id = _skill_id_from_item(item)
    mcp_server: str | None = None
    record = await session.get(ReviewRecord, item.review_id)
    if record is None or ":" not in record.entity_id:
        return skill_id, mcp_server

    run_key, _, sid = record.entity_id.partition(":")
    skill_id = skill_id or sid or None
    try:
        cap_run = await session.get(CapabilityRun, uuid.UUID(run_key))
    except ValueError:
        return skill_id, mcp_server

    if cap_run:
        skill_id = skill_id or cap_run.skill_id
        transcript = cap_run.transcript if isinstance(cap_run.transcript, dict) else None
        mcp_server = _mcp_server_from_run(transcript)
    return skill_id, mcp_server


async def build_intel_inbox_widget(
    session: AsyncSession,
    settings: Settings,
    *,
    preview_limit: int = INBOX_PREVIEW_LIMIT,
) -> IntelInboxWidget:
    queue = await build_global_review_queue(session, settings)
    items: list[IntelInboxItem] = []
    lane_counts: dict[str, int] = {}

    for raw in queue[:preview_limit]:
        skill_id, mcp_server = await _skill_context(session, raw)
        inbox_item = _to_inbox_item(raw, skill_id=skill_id, mcp_server=mcp_server)
        items.append(inbox_item)
        lane_counts[inbox_item.source_lane] = lane_counts.get(inbox_item.source_lane, 0) + 1

    count = len(queue)
    summary_parts = [
        f"{SOURCE_LANE_LABELS.get(lane, lane)} ×{n}"
        for lane, n in sorted(lane_counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    return IntelInboxWidget(
        count=count,
        items=tuple(items),
        needs_attention=count > 0,
        lane_counts=lane_counts,
        lane_summary=" · ".join(summary_parts),
    )