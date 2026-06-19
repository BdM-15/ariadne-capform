"""Capture lane IA — home, lifecycle filter, workspace alias."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from thread.domain.enums import LifecycleState
from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.capture_display import build_capture_home
from thread.services.pursuits_display import build_capture_pursuits, is_capture_lane_pursuit


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_capture_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


@pytest.mark.asyncio
async def test_capture_lane_excludes_identified_only(db_session):
    pursuing = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Pursuing {uuid.uuid4().hex[:6]}", lifecycle_state=LifecycleState.PURSUING),
    )
    identified = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Identified {uuid.uuid4().hex[:6]}"),
    )
    all_opps = await opp_svc.list_opportunities(db_session)
    cards = await build_capture_pursuits(db_session, all_opps)
    ids = {c["id"] for c in cards}
    assert str(pursuing.id) in ids
    assert str(identified.id) not in ids
    assert is_capture_lane_pursuit(pursuing) is True
    assert is_capture_lane_pursuit(identified) is False


@pytest.mark.asyncio
async def test_build_capture_home_lists_pursuits(db_session, settings):
    await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Cap {uuid.uuid4().hex[:6]}", lifecycle_state=LifecycleState.PURSUING),
    )
    home = await build_capture_home(db_session, settings)
    assert home["pursuits"]
    assert home["phase_band_widget"].total >= 1


def test_capture_home_route_renders():
    client = TestClient(create_app())
    res = client.get("/capture")
    assert res.status_code == 200
    assert "Filament" in res.text
    assert 'href="/capture"' in res.text
    assert "connected milestone" in res.text.lower()


def test_track_commit_redirects_to_capture():
    client = TestClient(create_app())
    res = client.post(
        "/opportunities",
        data={"name": f"WS {uuid.uuid4().hex[:8]}"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/capture/")


def test_opportunities_get_redirects_to_capture():
    client = TestClient(create_app())
    create = client.post("/opportunities", data={"name": f"Alias {uuid.uuid4().hex[:8]}"}, follow_redirects=False)
    opp_id = create.headers["location"].split("/capture/")[1].split("?")[0]
    res = client.get(f"/opportunities/{opp_id}", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == f"/capture/{opp_id}"


def test_sidebar_capture_nav_first_in_group():
    client = TestClient(create_app())
    res = client.get("/capture")
    html = res.text
    capture_idx = html.index('href="/capture"')
    knowledge_idx = html.index('href="/knowledge"')
    assert capture_idx < knowledge_idx
    assert 'data-lucide="waypoints"' in html