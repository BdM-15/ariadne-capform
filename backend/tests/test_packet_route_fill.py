"""Phase 20 — route-driven packet fill."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from thread.db.models import PacketFieldAnswer
from thread.domain.packet_answer_sources import CLEW, GROK, PG_INTEL, SAM_MCP
from thread.llm.router import CompletionResult, LlmProvider
from thread.services.sam_monitor import SamNoticeLead
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
    assert needs["ready_count"] == 1
    assert needs["blocked_count"] == 0
    assert needs["gaps"][0]["field_key"] == "a"


def test_build_data_needs_ranks_deterministic_and_impact_tags():
    needs = build_data_needs(
        [
            {
                "field_key": "slow",
                "label": "Slow Field",
                "value": "",
                "status": "unanswered",
                "reference_slide": "slide_5_bluf",
                "route_kind": "model_synthesis",
                "deterministic": False,
                "decision_impact": ("recommend",),
            },
            {
                "field_key": "qualify_slow",
                "label": "Qualify Slow",
                "value": "",
                "status": "unanswered",
                "reference_slide": "slide_5_bluf",
                "route_kind": "model_synthesis",
                "deterministic": False,
                "decision_impact": ("qualify",),
            },
            {
                "field_key": "fast",
                "label": "Fast Field",
                "value": "",
                "status": "unanswered",
                "reference_slide": "slide_4_synopsis",
                "route_kind": "source_profile_lookup",
                "deterministic": True,
                "decision_impact": ("fund",),
            },
        ]
    )
    keys = [gap["field_key"] for gap in needs["gaps"]]
    assert keys == ["fast", "qualify_slow", "slow"]


def test_build_data_needs_defers_missing_prerequisites():
    needs = build_data_needs(
        [
            {
                "field_key": "prime_name",
                "label": "Prime Name",
                "value": "",
                "status": "unanswered",
                "reference_slide": "slide_4_synopsis",
                "route_kind": "source_backed_answer",
                "deterministic": True,
                "decision_impact": ("qualify", "team"),
                "prerequisites": ("award_key",),
            },
            {
                "field_key": "capture_manager",
                "label": "Capture Manager",
                "value": "",
                "status": "unanswered",
                "reference_slide": "slide_6_team",
                "route_kind": "source_backed_answer",
                "deterministic": False,
                "decision_impact": ("team",),
            },
        ],
        context={"award_key": "", "notice_id": ""},
    )
    assert needs["blocked_count"] == 1
    assert needs["ready_count"] == 1
    assert needs["gaps"][0]["field_key"] == "capture_manager"
    assert needs["gaps"][1]["field_key"] == "prime_name"
    assert needs["gaps"][1]["blocked"] is True
    assert "award link" in needs["gaps"][1]["blocked_reason"]


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
async def test_apply_route_fill_from_sam_mcp(db_session, settings, monkeypatch):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(
            name=f"SAM {uuid.uuid4().hex[:6]}",
            lifecycle_state="pursuing",
            sam_notice_id="abc123def456",
            solicitation_number="W912HQ-26-R-0001",
        ),
    )
    notice = SamNoticeLead(
        notice_id="abc123def456",
        title="Enterprise IT Support Services",
        agency="DEPT OF DEFENSE · DEPT OF THE ARMY",
        solicitation_number="W912HQ-26-R-0001",
        response_deadline="07/01/2026",
        posted_date="06/15/2026",
        notice_type="o",
        set_aside="SBA",
        naics_code="541512",
    )

    async def fake_notice(_settings, notice_id):
        assert notice_id == "abc123def456"
        return notice

    monkeypatch.setattr("thread.services.packet_route_fill._sam_configured", lambda _s: True)
    monkeypatch.setattr("thread.services.packet_route_fill._fetch_sam_notice", fake_notice)

    result = await apply_route_fill(db_session, settings, opp.id, "opportunity_name", SAM_MCP)
    assert result.ok is True
    assert "IT Support" in result.value
    await db_session.commit()


@pytest.mark.asyncio
async def test_apply_route_fill_from_grok(db_session, settings, monkeypatch):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Grok {uuid.uuid4().hex[:6]}", lifecycle_state="pursuing"),
    )

    async def fake_complete(_settings, **kwargs):
        return CompletionResult(
            text="Strong BLUF: pursue with teaming focus on set-aside compliance.",
            provider=LlmProvider.XAI,
            model="grok-test",
        )

    monkeypatch.setattr("thread.services.packet_route_fill.complete", fake_complete)
    monkeypatch.setattr(
        "thread.services.packet_route_fill._grok_context_bundle",
        AsyncMock(return_value={"field_label": "Opportunity Context", "field_key": "opportunity_context", "question": "Q?", "value_kind": "prose", "route_hint": ""}),
    )

    result = await apply_route_fill(db_session, settings, opp.id, "opportunity_context", GROK)
    assert result.ok is True
    assert "BLUF" in result.value
    await db_session.commit()


@pytest.mark.asyncio
async def test_apply_route_fill_sam_without_notice_id(db_session, settings):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"NoSAM {uuid.uuid4().hex[:6]}"),
    )
    result = await apply_route_fill(db_session, settings, opp.id, "opportunity_name", SAM_MCP)
    assert result.ok is False
    assert "notice_id" in result.message


@pytest.mark.asyncio
async def test_run_packet_route_fill_clew_redirects(db_session, settings):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Clew {uuid.uuid4().hex[:6]}"),
    )
    result = await run_packet_route_fill(db_session, settings, opp.id, "prime_name", CLEW)
    assert result.ok is True
    assert result.redirect_url and "/clew" in result.redirect_url