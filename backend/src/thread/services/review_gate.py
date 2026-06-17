from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.models import PacketFieldAnswer, ReviewRecord
from thread.domain.enums import ReviewState, TrustLevel


class ReviewGateError(Exception):
    pass


async def create_review_record(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    trust_level: TrustLevel = TrustLevel.CANDIDATE,
    provenance: list | None = None,
) -> ReviewRecord:
    record = ReviewRecord(
        entity_type=entity_type,
        entity_id=entity_id,
        trust_level=trust_level.value,
        review_state=ReviewState.PENDING_REVIEW.value,
        provenance=provenance or [],
    )
    session.add(record)
    await session.flush()
    return record


async def approve_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    note: str | None = None,
    edited_value: str | None = None,
) -> ReviewRecord:
    record = await session.get(ReviewRecord, review_id)
    if record is None:
        raise ReviewGateError("Review record not found")
    if record.review_state != ReviewState.PENDING_REVIEW.value:
        raise ReviewGateError("Review is not pending")

    record.review_state = ReviewState.ACCEPTED.value
    record.trust_level = TrustLevel.TRUSTED.value
    record.reviewer_note = note

    if record.entity_type == "packet_field_answer":
        answer = await session.get(PacketFieldAnswer, uuid.UUID(record.entity_id))
        if answer:
            if edited_value is not None:
                answer.value = edited_value
            answer.trust_level = TrustLevel.TRUSTED.value
            answer.review_state = ReviewState.ACCEPTED.value
            answer.status = "answered"

    await session.flush()
    return record


async def list_pending_reviews(session: AsyncSession) -> list[ReviewRecord]:
    result = await session.execute(
        select(ReviewRecord).where(ReviewRecord.review_state == ReviewState.PENDING_REVIEW.value)
    )
    return list(result.scalars().all())