"""Phase 20 — route-driven packet fill."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from thread.db.models import PacketFieldAnswer
from thread.domain.packet_answer_sources import CLEW, PG_INTEL
from thread.domain.schemas import OpportunityCreate
from thread.services import opportunities as opp_svc
from thread.services.packet_route_fill import apply_route_fill, build_data_needs, run_packet_route_fill
from thread.services.packet_workflows import workflow_actions_for_field


def test_build_data_needs_counts_open_fields():
    needs = build_data_needs(
        [
            {"field_key": "a", "label": "Prime", "value": "", "status": "unanswered", "reference_slide": "slide_4_synopsis", "route_kind": "source_profile_lookup", "deterministic": True},
            {"field_key": "b", "label": "Done", "value": "filled", "status": "answered", "reference_slide": "slide_4_synopsis", "route_kind": "source_backed_answer", "deterministic": False},
        ]
    )
    assert needs["count"] == 1
    assert needs["gaps"][0]["field_key"] == "a"


def test_workflow_pg_intel_executable_for_prime_name():
    actions = workflow_actions_for_field(
        {
            "field_key": "prime_name",
            "answer_sources": [PG_INTEL],
            "route_kind": "source_backed_answer",
            "deterministic": True,
        },
        opp_id="abc",
    )
    pg = next(a for a in actions if a["id"] == PG_INTEL)
    assert pg["executable"] is True


@pytest.mark.asyncio
async def test_apply_route_fill_without_award_key(db_session, settings):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Fill {uuid.uuid4().hex[:6]}", lifecycle_state="pursuing"),
    )
    result = await apply_route_fill(db_session, settings, opp.id, "prime_name", PG_INTEL)
    assert result.ok is False
    assert "award_key" in result.message


@pytest.mark.asyncio
async def test_apply_route_fill_from_pg_intel(db_session, settings):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(
            name=f"Award {uuid.uuid4().hex[:6]}",
            lifecycle_state="pursuing",
            award_key="TEST_AWARD_KEY",
        ),
    )
    profile = {
        "award_key": "TEST_AWARD_KEY",
        "recipient": "Amentum Services Inc.",
        "agency": "Department of the Army",
        "obligation": 1_500_000.0,
        "pricing": "FIRM FIXED PRICE",
        "end_date": "2027-06-30",
    }
    with patch("thread.services.packet_route_fill.get_award_profile", new_callable=AsyncMock, return_value=profile):
        result = await apply_route_fill(db_session, settings, opp.id, "prime_name", PG_INTEL)
    assert result.ok is True
    assert "Amentum" in result.value
    await db_session.commit()

    row = (
        await db_session.execute(
            select(PacketFieldAnswer).where(
                PacketFieldAnswer.opportunity_id == opp.id,
                PacketFieldAnswer.field_key == "prime_name",
            )
        )
    ).scalar_one()
    assert "Amentum" in (row.value or "")


@pytest.mark.asyncio
async def test_run_packet_route_fill_clew_redirects(db_session, settings):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Clew {uuid.uuid4().hex[:6]}"),
    )
    result = await run_packet_route_fill(db_session, settings, opp.id, "prime_name", CLEW)
    assert result.ok is True
    assert result.redirect_url and "/clew" in result.redirect_url