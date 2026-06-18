from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.models import ActionMatrixItem, Opportunity, PacketFieldAnswer, PacketFieldDefinition, ReviewRecord
from thread.domain.enums import MilestoneGate, PacketFieldAnswerStatus, ReviewState, TrustLevel
from thread.domain.packet_field_seed import PACKET_FIELD_SEEDS
from thread.domain.schemas import OpportunityCreate
from thread.services.review_gate import create_review_record


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "opportunity"


async def seed_packet_definitions(session: AsyncSession) -> None:
    """Initial seed when table is empty (legacy)."""
    count = await session.scalar(select(func.count()).select_from(PacketFieldDefinition))
    if count and count > 0:
        return
    await ensure_packet_definitions(session)


async def ensure_packet_definitions(session: AsyncSession) -> None:
    """Upsert packet field definitions from PACKET_FIELD_SEEDS."""
    existing = {
        row.key
        for row in (await session.execute(select(PacketFieldDefinition))).scalars().all()
    }
    for seed in PACKET_FIELD_SEEDS:
        if seed.key in existing:
            continue
        session.add(
            PacketFieldDefinition(
                key=seed.key,
                label=seed.label,
                question=seed.question,
                section=seed.section.value,
                value_kind=seed.value_kind.value,
                required_gates=[g.value for g in seed.required_gates],
                route_kind=seed.route_kind.value,
                reference_slide=seed.reference_slide,
            )
        )
    await session.flush()


async def ensure_packet_answers(session: AsyncSession, opp_id: uuid.UUID) -> None:
    """Ensure every definition has an answer row for this opportunity."""
    await ensure_packet_definitions(session)
    existing = {
        row.field_key
        for row in (
            await session.execute(
                select(PacketFieldAnswer.field_key).where(PacketFieldAnswer.opportunity_id == opp_id)
            )
        ).all()
    }
    defs = (await session.execute(select(PacketFieldDefinition))).scalars().all()
    for definition in defs:
        if definition.key in existing:
            continue
        session.add(
            PacketFieldAnswer(
                opportunity_id=opp_id,
                field_key=definition.key,
                status=PacketFieldAnswerStatus.UNANSWERED.value,
                trust_level=TrustLevel.INTAKE.value,
            )
        )
    await session.flush()


async def create_opportunity(session: AsyncSession, payload: OpportunityCreate) -> Opportunity:
    await seed_packet_definitions(session)
    provenance = None
    if payload.sam_notice_id:
        provenance = {
            "source": "sam_gov",
            "notice_id": payload.sam_notice_id,
            "solicitation_number": payload.solicitation_number,
            "notice_type": payload.notice_type,
            "naics_code": payload.naics_code,
        }
    elif payload.award_key:
        provenance = {
            "award_key": payload.award_key,
            "naics_code": payload.naics_code,
            "source": "intel_signal",
        }
    opp = Opportunity(
        name=payload.name,
        slug=slugify(payload.name),
        capture_phase_band=payload.capture_phase_band.value,
        entry_reason=payload.entry_reason,
        intel_provenance=provenance,
        freshness_at=datetime.now(timezone.utc),
    )
    session.add(opp)
    await session.flush()

    await ensure_packet_answers(session, opp.id)
    return opp


async def list_opportunities(session: AsyncSession) -> list[Opportunity]:
    result = await session.execute(select(Opportunity).order_by(Opportunity.freshness_at.desc()))
    return list(result.scalars().all())


async def get_opportunity(session: AsyncSession, opp_id: uuid.UUID) -> Opportunity | None:
    return await session.get(Opportunity, opp_id)


async def update_packet_field(
    session: AsyncSession,
    opp_id: uuid.UUID,
    field_key: str,
    value: str,
    *,
    as_candidate: bool = True,
) -> PacketFieldAnswer:
    result = await session.execute(
        select(PacketFieldAnswer).where(
            PacketFieldAnswer.opportunity_id == opp_id,
            PacketFieldAnswer.field_key == field_key,
        )
    )
    answer = result.scalar_one()
    answer.value = value
    answer.status = PacketFieldAnswerStatus.NEEDS_REVIEW.value if as_candidate else PacketFieldAnswerStatus.ANSWERED.value
    answer.trust_level = TrustLevel.CANDIDATE.value if as_candidate else TrustLevel.TRUSTED.value
    answer.review_state = ReviewState.PENDING_REVIEW.value if as_candidate else ReviewState.ACCEPTED.value

    if as_candidate:
        await create_review_record(
            session,
            entity_type="packet_field_answer",
            entity_id=str(answer.id),
            provenance=[{"kind": "manual", "ref": "user_edit"}],
        )
    await session.flush()
    return answer


async def pending_review_count(session: AsyncSession, opp_id: uuid.UUID) -> int:
    answers = (
        await session.execute(
            select(PacketFieldAnswer.id).where(
                PacketFieldAnswer.opportunity_id == opp_id,
                PacketFieldAnswer.review_state == ReviewState.PENDING_REVIEW.value,
            )
        )
    ).scalars().all()
    return len(answers)


async def add_action_item(
    session: AsyncSession,
    opp_id: uuid.UUID,
    action: str,
    owner: str | None,
    due_date,
    linked_field_keys: list[str],
) -> ActionMatrixItem:
    item = ActionMatrixItem(
        opportunity_id=opp_id,
        action=action,
        owner=owner,
        due_date=due_date,
        linked_field_keys=linked_field_keys,
    )
    session.add(item)
    await session.flush()
    return item