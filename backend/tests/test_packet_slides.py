"""Phase 14c–14e — MS gate slide applicability and packet progression."""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from thread.domain.enums import MilestoneGate
from thread.domain.packet_slides import (
    REFERENCE_SLIDE_IDS,
    SLIDE_PRESENTATION_TITLES,
    slide_applicability,
    slide_visible,
)
from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.packet_workspace import build_packet_workspace

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="THREAD_SKIP_PG_TESTS set",
)


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_slide_applicability_markers():
    assert slide_applicability("slide_10_pricing", MilestoneGate.MILESTONE_1.value, fields_for_gate=0) == "optional"
    assert slide_applicability("slide_10_pricing", MilestoneGate.MILESTONE_3.value, fields_for_gate=1) == "required"
    assert slide_applicability("slide_8_swot", MilestoneGate.MILESTONE_1.value, fields_for_gate=4) == "required"
    assert slide_applicability("slide_8_swot", MilestoneGate.MILESTONE_4.value, fields_for_gate=0) == "optional"
    assert slide_applicability("slide_7_evaluation", MilestoneGate.MILESTONE_1.value, fields_for_gate=0) == "optional"
    assert slide_applicability("slide_ref_faq", MilestoneGate.MILESTONE_1.value, fields_for_gate=0) == "reference"
    assert slide_visible("omitted") is False
    assert slide_visible("reference") is True
    assert SLIDE_PRESENTATION_TITLES["slide_6_team"] == "Opportunity Team Assignments (1 Min)"
    assert len(REFERENCE_SLIDE_IDS) == 4


@pytest.mark.asyncio
async def test_ms1_includes_swot_and_team_bp_fields(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="MS1 SWOT Team"),
    )
    await db_session.commit()

    view = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_1.value,
        active_slide="slide_8_swot",
    )
    keys = {f["field_key"] for f in view["fields"]}
    assert "swot_strengths" in keys
    assert "swot_threats" in keys

    team = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_1.value,
        active_slide="slide_6_team",
    )
    team_keys = {f["field_key"] for f in team["fields"]}
    assert "bp_funding_request_amount" in team_keys
    assert "bp_notes" in team_keys
    assert "operating_unit" in team_keys


@pytest.mark.asyncio
async def test_ms1_hides_pricing_slide_from_nav(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="MS1 Gate Test"),
    )
    await db_session.commit()

    view = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_1.value,
    )
    nav_ids = [s["id"] for s in view["slide_nav"]]
    assert "slide_ref_process_bluf" in nav_ids
    assert "slide_8_swot" in nav_ids
    assert "slide_8_swot" in nav_ids
    swot = next(s for s in view["slide_nav"] if s["id"] == "slide_8_swot")
    assert swot["applicability"] == "required"
    pricing = next((s for s in view["slide_nav"] if s["id"] == "slide_10_pricing"), None)
    assert pricing is None or pricing["applicability"] == "optional"
    assert "slide_17_approval" in nav_ids
    assert "slide_18_approval" not in nav_ids
    assert view["progress"]["total"] > 0


@pytest.mark.asyncio
async def test_ms3_includes_pricing_and_approval_18(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="MS3 Gate Test"),
    )
    await db_session.commit()

    view = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_3.value,
        active_slide="slide_18_approval",
    )
    nav_ids = [s["id"] for s in view["slide_nav"]]
    assert "slide_10_pricing" in nav_ids
    assert "slide_18_approval" in nav_ids
    assert view["active_slide"] == "slide_18_approval"
    keys = {f["field_key"] for f in view["fields"]}
    assert "ms3_win_strategy_validated" in keys


@pytest.mark.asyncio
async def test_packet_progress_pending_review(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="Progress Test"),
    )
    await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "customer_name",
        "Army CIO",
        as_candidate=True,
    )
    await db_session.commit()

    view = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_1.value,
    )
    assert view["progress"]["pending_review"] >= 1
    assert view["progress"]["filled"] >= 1


@pytest.mark.asyncio
async def test_approval_slide_renders_in_ui():
    app = create_app()
    tag = uuid.uuid4().hex[:8]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/opportunities",
            json={"name": f"Approval UI {tag}", "entry_reason": "manual"},
        )
        assert created.status_code == 200
        opp_id = created.json()["id"]

        res = await client.get(
            f"/capture/{opp_id}?tab=packet&slide=slide_17_approval"
        )
        assert res.status_code == 200
        assert "MS1 &amp; MS2 Approval" in res.text or "MS1 &amp; MS2 approval" in res.text
        assert "Strategic fit confirmed?" in res.text
        assert "packet-slide-canvas" in res.text
        assert "Evidence Inspector" in res.text