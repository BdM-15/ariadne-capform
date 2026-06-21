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
    REFERENCE_SLIDE_SUMMARIES,
    SLIDE_DECK_NUMBERS,
    SLIDE_PRESENTATION_TITLES,
    SLIDE_MS_MARKERS,
    field_applicable_for_gate,
    gate_number,
    is_reference_slide,
    normalize_milestone_gate,
    normalize_packet_slide,
    slide_applicability,
    slide_visible,
)
from thread.domain.packet_field_seed import FIELD_SEED_BY_KEY
from thread.services.opportunities import ensure_packet_definitions, ensure_packet_answers, get_opportunity
from thread.services.packet_route_fill import build_data_needs
from thread.services.packet_workflows import build_slide_fill_workflows


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
    value_kind: str

    answer_sources: tuple[str, ...] = ()
    route_hint: str = ""
    deterministic: bool = False
    decision_impact: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()

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
            "value_kind": self.value_kind,
            "answer_sources": list(self.answer_sources),
            "route_hint": self.route_hint,
            "deterministic": self.deterministic,
            "decision_impact": list(self.decision_impact),
            "prerequisites": list(self.prerequisites),
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

    opp = await get_opportunity(session, opp_id)
    prov = (opp.intel_provenance or {}) if opp else {}
    data_needs_context = {
        "award_key": str(prov.get("award_key") or "").strip(),
        "notice_id": str(prov.get("notice_id") or "").strip(),
        "has_mineru": bool(prov.get("mineru_bundle_id") or prov.get("mineru_parsed")),
    }

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
        seed = FIELD_SEED_BY_KEY.get(answer.field_key)
        route = seed.answer_route if seed and seed.answer_route else None
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
            value_kind=defn.value_kind,
            answer_sources=route.sources if route else (),
            route_hint=route.hint if route else "",
            deterministic=route.deterministic if route else False,
            decision_impact=seed.decision_impact if seed else (),
            prerequisites=seed.prerequisites if seed else (),
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
    slide_ordinal = 0
    for sid, title in PACKET_SLIDE_ORDER:
        field_count = counts_by_slide_gate.get(sid, 0)
        applicability = slide_applicability(sid, gate, fields_for_gate=field_count)
        if not slide_visible(applicability):
            continue
        slide_ordinal += 1
        slide_nav.append(
            {
                "id": sid,
                "title": title,
                "presentation_title": SLIDE_PRESENTATION_TITLES.get(sid, title),
                "deck_number": SLIDE_DECK_NUMBERS.get(sid, ""),
                "number": f"{slide_ordinal:02d}",
                "field_count": field_count,
                "answered_count": answered_by_slide_gate.get(sid, 0),
                "active": sid == slide_id,
                "applicability": applicability,
                "is_reference": is_reference_slide(sid),
                "reference_summary": REFERENCE_SLIDE_SUMMARIES.get(sid, ""),
                "ms_markers": sorted(SLIDE_MS_MARKERS.get(sid, frozenset())),
            }
        )

    # If active slide omitted for this gate, jump to first visible slide.
    if not any(s["id"] == slide_id and s["active"] for s in slide_nav):
        slide_id = slide_nav[0]["id"] if slide_nav else normalize_packet_slide(None)
        for row in slide_nav:
            row["active"] = row["id"] == slide_id

    all_field_dicts = [c.as_template_dict() for c in cards]
    active_fields = [f for f in all_field_dicts if f["reference_slide"] == slide_id]
    active_title = next((t for sid, t in PACKET_SLIDE_ORDER if sid == slide_id), slide_id)
    active_nav = next((s for s in slide_nav if s["id"] == slide_id), None)
    active_presentation_title = (
        active_nav["presentation_title"] if active_nav else SLIDE_PRESENTATION_TITLES.get(slide_id, active_title)
    )
    active_slide_number = active_nav["number"] if active_nav else "01"
    active_applicability = active_nav["applicability"] if active_nav else "required"
    active_is_reference = active_nav["is_reference"] if active_nav else False
    active_reference_summary = active_nav["reference_summary"] if active_nav else ""
    active_deck_number = active_nav["deck_number"] if active_nav else ""
    active_slide_answered = active_nav["answered_count"] if active_nav else 0
    active_slide_field_count = active_nav["field_count"] if active_nav else 0

    pct = round(100.0 * ms_critical_filled / ms_critical_total, 1) if ms_critical_total else 0.0
    if pct >= 75:
        readiness_label = "Draft Ready"
    elif pct >= 35:
        readiness_label = "In Progress"
    else:
        readiness_label = "Drafting"

    return {
        "milestone_gate": gate,
        "milestone_gate_label": f"MS{gn}",
        "active_slide": slide_id,
        "active_slide_title": active_title,
        "active_presentation_title": active_presentation_title,
        "active_slide_number": active_slide_number,
        "active_applicability": active_applicability,
        "active_is_reference": active_is_reference,
        "active_reference_summary": active_reference_summary,
        "active_deck_number": active_deck_number,
        "active_slide_answered": active_slide_answered,
        "active_slide_field_count": active_slide_field_count,
        "readiness_label": readiness_label,
        "slide_nav": slide_nav,
        "slide_count": len(slide_nav),
        "fields": active_fields,
        "fill_workflows": build_slide_fill_workflows(active_fields, opp_id=opp_id),
        "data_needs": build_data_needs(all_field_dicts, context=data_needs_context),
        "open_field_count": sum(1 for f in active_fields if not (f.get("value") or "").strip()),
        "progress": {
            "filled": ms_critical_filled,
            "total": ms_critical_total,
            "trusted": ms_critical_trusted,
            "pct": pct,
            "pending_review": pending_review,
        },
    }


async def enrich_packet_field_card(
    session: AsyncSession,
    answer: PacketFieldAnswer,
) -> dict[str, Any]:
    defn = await session.get(PacketFieldDefinition, answer.field_key)
    seed = FIELD_SEED_BY_KEY.get(answer.field_key)
    route = seed.answer_route if seed and seed.answer_route else None
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
        value_kind=defn.value_kind if defn else "text",
        answer_sources=route.sources if route else (),
        route_hint=route.hint if route else "",
        deterministic=route.deterministic if route else False,
        decision_impact=seed.decision_impact if seed else (),
        prerequisites=seed.prerequisites if seed else (),
    )
    return card.as_template_dict()