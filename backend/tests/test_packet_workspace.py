"""Phase 14 — Living Briefing Packet slide navigator."""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.packet_workspace import (
    PACKET_SLIDE_ORDER,
    build_packet_workspace,
    normalize_packet_slide,
)

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
async def test_build_packet_workspace_groups_by_slide(db_session):
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="Packet Test Opp"),
    )
    await db_session.commit()

    view = await build_packet_workspace(db_session, opp.id, active_slide="slide_5_bluf")
    assert view["active_slide"] == "slide_5_bluf"
    assert view["active_slide_title"] == "BLUF"
    assert len(view["slide_nav"]) >= 3
    assert all("field_count" in row for row in view["slide_nav"])
    assert view["progress"]["total"] >= 15
    bluf_keys = {f["field_key"] for f in view["fields"]}
    assert "opportunity_context" in bluf_keys or "recommendation" in bluf_keys


def test_normalize_packet_slide_defaults():
    assert normalize_packet_slide(None) == "slide_2_cover"
    assert normalize_packet_slide("not_a_slide") == "slide_2_cover"
    assert normalize_packet_slide("slide_8_swot") == "slide_8_swot"


@pytest.mark.asyncio
async def test_opportunity_packet_slide_nav_in_ui():
    app = create_app()
    tag = uuid.uuid4().hex[:8]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/opportunities",
            json={"name": f"Slide Nav {tag}", "entry_reason": "manual"},
        )
        assert created.status_code == 200, created.text
        opp_id = created.json()["id"]

        res = await client.get(f"/capture/{opp_id}?tab=packet&slide=slide_5_bluf")
        assert res.status_code == 200
        html = res.text
        assert "packet-slide-nav" in html
        assert "packet-slide-canvas" in html
        assert "packet-briefing-layout" in html
        assert "Evidence Inspector" in html
        assert "Briefing View" in html
        assert "Connected fill routes" in html
        assert "packet-fill-workflows" in html
        assert "BLUF" in html