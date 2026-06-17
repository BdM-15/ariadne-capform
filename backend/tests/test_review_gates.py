"""Review gate contract — nothing auto-promotes to trusted."""

from __future__ import annotations

import uuid

import pytest

from thread.domain.enums import ReviewState, TrustLevel
from thread.domain.schemas import OpportunityCreate
from thread.services import opportunities as opp_svc
from thread.services.review_gate import (
    ReviewGateError,
    approve_review,
    create_review_record,
    list_pending_reviews,
)


@pytest.mark.asyncio
async def test_create_review_record_stays_candidate_pending(db_session):
    record = await create_review_record(
        db_session,
        entity_type="research_finding",
        entity_id="run-1:finding:0",
        provenance=[{"kind": "url", "ref": "https://example.com"}],
    )

    assert record.trust_level == TrustLevel.CANDIDATE.value
    assert record.review_state == ReviewState.PENDING_REVIEW.value


@pytest.mark.asyncio
async def test_approve_review_promotes_to_trusted(db_session):
    record = await create_review_record(
        db_session,
        entity_type="research_interpretation",
        entity_id="run-1:interpretation",
    )
    approved = await approve_review(db_session, record.id, note="looks good")

    assert approved.trust_level == TrustLevel.TRUSTED.value
    assert approved.review_state == ReviewState.ACCEPTED.value
    assert approved.reviewer_note == "looks good"


@pytest.mark.asyncio
async def test_double_approve_raises(db_session):
    record = await create_review_record(
        db_session,
        entity_type="research_finding",
        entity_id="run-2:finding:0",
    )
    await approve_review(db_session, record.id)

    with pytest.raises(ReviewGateError, match="not pending"):
        await approve_review(db_session, record.id)


@pytest.mark.asyncio
async def test_packet_field_edit_stays_candidate_until_approved(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Review Gate Test {uuid.uuid4().hex[:8]}"),
    )
    answer = await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "DHS Cyber Recompete",
        as_candidate=True,
    )

    assert answer.trust_level == TrustLevel.CANDIDATE.value
    assert answer.review_state == ReviewState.PENDING_REVIEW.value

    pending = await list_pending_reviews(db_session)
    packet_reviews = [r for r in pending if r.entity_type == "packet_field_answer"]
    assert any(r.entity_id == str(answer.id) for r in packet_reviews)

    review = next(r for r in packet_reviews if r.entity_id == str(answer.id))
    await approve_review(db_session, review.id, edited_value="DHS Cyber Recompete (trusted)")

    await db_session.refresh(answer)
    assert answer.trust_level == TrustLevel.TRUSTED.value
    assert answer.review_state == ReviewState.ACCEPTED.value
    assert answer.value == "DHS Cyber Recompete (trusted)"


@pytest.mark.asyncio
async def test_packet_field_direct_edit_can_skip_review(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Direct Edit {uuid.uuid4().hex[:8]}"),
    )
    answer = await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "Trusted immediately",
        as_candidate=False,
    )

    assert answer.trust_level == TrustLevel.TRUSTED.value
    assert answer.review_state == ReviewState.ACCEPTED.value

    pending = await list_pending_reviews(db_session)
    assert not any(r.entity_id == str(answer.id) for r in pending)