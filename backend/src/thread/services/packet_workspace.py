"""Phase 14 — Living Briefing Packet workspace (slide navigator + field cards)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.models import PacketFieldAnswer, PacketFieldDefinition
from thread.domain.enums import ReviewState
from thread.domain.packet_slides import (
    PACKET_SLIDE_ORDER,
    SLIDE_MS_MARKERS,
    field_applicable_for_gate,
    gate_number,
    normalize_milestone_gate,
    normalize_packet_slide,
    slide_applicability,
    slide_visible,
)
from thread.services.opportunities import ensure_packet_definitions, ensure_packet_answers


@dataclass(frozen=True)
class PacketFieldCard:
    field_key: str
    label: str
    question: str
    route_kind: str
    reference_slide: str
    section: str
    value: str | None
    status: str
    trust_level: str
    review_state: str | None
    required_gates: tuple[str, ...]

    def as_template_dict(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "label": self.label,
            "question": self.question,
            "route_kind": self.route_kind,
            "reference_slide": self.reference_slide,
            "section": self.section,
            "value": self.value,
            "status": self.status,
            "trust_level": self.trust_level,
            "review_state": self.review_state,
            "required_gates": list(self.required_gates),
        }


def _filled(card: PacketFieldCard) -> bool:
    return bool(card.value and str(card.value).strip())


async def build_packet_workspace(
    session: AsyncSession,
    opp_id: uuid.UUID,
    *,
    active_slide: str | None = None,
    milestone_gate: str | None = None,
) -> dict[str, Any]:
    await ensure_packet_definitions(session)
    await ensure_packet_answers(session, opp_id)

    gate = normalize_milestone_gate(milestone_gate)
    slide_id = normalize_packet_slide(active_slide)
    gn = gate_number(gate)

    definitions = {
        row.key: row
        for row in (await session.execute(select(PacketFieldDefinition))).scalars().all()
    }
    answers = (
        await session.execute(
            select(PacketFieldAnswer).where(PacketFieldAnswer.opportunity_id == opp_id)
        )
    ).scalars().all()

    cards: list[PacketFieldCard] = []
    counts_by_slide_gate: dict[str, int] = {sid: 0 for sid, _ in PACKET_SLIDE_ORDER}
    answered_by_slide_gate: dict[str, int] = {sid: 0 for sid, _ in PACKET_SLIDE_ORDER}

    ms_critical_total = 0
    ms_critical_filled = 0
    ms_critical_trusted = 0
    pending_review = 0

    for answer in answers:
        defn = definitions.get(answer.field_key)
        if not defn:
            continue
        req_gates = tuple(defn.required_gates or [])
        if not field_applicable_for_gate(req_gates, gate):
            continue

        ref_slide = defn.reference_slide or PACKET_SLIDE_ORDER[0][0]
        card = PacketFieldCard(
            field_key=answer.field_key,
            label=defn.label,
            question=defn.question,
            route_kind=defn.route_kind,
            reference_slide=ref_slide,
            section=defn.section,
            value=answer.value,
            status=answer.status,
            trust_level=answer.trust_level,
            review_state=answer.review_state,
            required_gates=req_gates,
        )
        cards.append(card)

        ms_critical_total += 1
        if _filled(card):
            ms_critical_filled += 1
        if answer.trust_level == "trusted":
            ms_critical_trusted += 1
        if answer.review_state == ReviewState.PENDING_REVIEW.value:
            pending_review += 1

        counts_by_slide_gate[ref_slide] = counts_by_slide_gate.get(ref_slide, 0) + 1
        if _filled(card):
            answered_by_slide_gate[ref_slide] = answered_by_slide_gate.get(ref_slide, 0) + 1

    slide_nav: list[dict[str, Any]] = []
    for sid, title in PACKET_SLIDE_ORDER:
        field_count = counts_by_slide_gate.get(sid, 0)
        applicability = slide_applicability(sid, gate, fields_for_gate=field_count)
        if not slide_visible(applicability):
            continue
        slide_nav.append(
            {
                "id": sid,
                "title": title,
                "field_count": field_count,
                "answered_count": answered_by_slide_gate.get(sid, 0),
                "active": sid == slide_id,
                "applicability": applicability,
                "ms_markers": sorted(SLIDE_MS_MARKERS.get(sid, frozenset())),
            }
        )

    # If active slide omitted for this gate, jump to first visible slide.
    if not any(s["id"] == slide_id and s["active"] for s in slide_nav):
        slide_id = slide_nav[0]["id"] if slide_nav else normalize_packet_slide(None)
        for row in slide_nav:
            row["active"] = row["id"] == slide_id

    active_fields = [c.as_template_dict() for c in cards if c.reference_slide == slide_id]
    active_title = next((t for sid, t in PACKET_SLIDE_ORDER if sid == slide_id), slide_id)

    return {
        "milestone_gate": gate,
        "milestone_gate_label": f"MS{gn}",
        "active_slide": slide_id,
        "active_slide_title": active_title,
        "slide_nav": slide_nav,
        "fields": active_fields,
        "progress": {
            "filled": ms_critical_filled,
            "total": ms_critical_total,
            "trusted": ms_critical_trusted,
            "pct": round(100.0 * ms_critical_filled / ms_critical_total, 1) if ms_critical_total else 0.0,
            "pending_review": pending_review,
        },
    }


async def enrich_packet_field_card(
    session: AsyncSession,
    answer: PacketFieldAnswer,
) -> dict[str, Any]:
    defn = await session.get(PacketFieldDefinition, answer.field_key)
    card = PacketFieldCard(
        field_key=answer.field_key,
        label=defn.label if defn else answer.field_key.replace("_", " ").title(),
        question=defn.question if defn else "",
        route_kind=defn.route_kind if defn else "source_backed_answer",
        reference_slide=defn.reference_slide if defn else PACKET_SLIDE_ORDER[0][0],
        section=defn.section if defn else "",
        value=answer.value,
        status=answer.status,
        trust_level=answer.trust_level,
        review_state=answer.review_state,
        required_gates=tuple(defn.required_gates or []) if defn else (),
    )
    return card.as_template_dict()