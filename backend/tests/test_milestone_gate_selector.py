"""Phase 14 — MS gate selector on opportunity workspace."""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from thread.domain.enums import MilestoneGate
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


@pytest.mark.asyncio
async def test_update_milestone_gate_persists(db_session):
    opp = await opp_svc.create_opportunity(db_session, OpportunityCreate(name="Gate Persist"))
    await db_session.commit()

    updated = await opp_svc.update_milestone_gate(
        db_session, opp.id, MilestoneGate.MILESTONE_3.value
    )
    await db_session.commit()
    assert updated is not None
    assert updated.current_milestone_gate == MilestoneGate.MILESTONE_3.value


@pytest.mark.asyncio
async def test_ms3_gate_shows_pricing_slide_in_workspace(db_session):
    opp = await opp_svc.create_opportunity(db_session, OpportunityCreate(name="Gate Nav"))
    await opp_svc.update_milestone_gate(db_session, opp.id, MilestoneGate.MILESTONE_3.value)
    await db_session.commit()

    view = await build_packet_workspace(
        db_session,
        opp.id,
        milestone_gate=MilestoneGate.MILESTONE_3.value,
    )
    nav_ids = [s["id"] for s in view["slide_nav"]]
    assert "slide_10_pricing" in nav_ids
    assert "slide_18_approval" in nav_ids


@pytest.mark.asyncio
async def test_ms_gate_selector_in_workspace_ui():
    app = create_app()
    tag = uuid.uuid4().hex[:8]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/opportunities",
            json={"name": f"Gate UI {tag}", "entry_reason": "manual"},
        )
        opp_id = created.json()["id"]

        page = await client.get(f"/capture/{opp_id}?tab=packet")
        assert page.status_code == 200
        assert "ms-gate-btn" in page.text
        assert "ms-gate-btn-active" in page.text
        assert 'hx-post="/opportunities/' in page.text

        switched = await client.post(
            f"/opportunities/{opp_id}/milestone-gate",
            data={"milestone_gate": "milestone_3", "tab": "packet", "slide": ""},
        )
        assert switched.status_code == 200
        assert "slide_10_pricing" in switched.text
        assert "ms-gate-btn-active" in switched.text