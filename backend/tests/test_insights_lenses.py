"""Phase 17 — Data Insights live explore + saved bookmarks."""

import json

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.intel.facet_query import (
    delete_insight_query,
    load_insight_queries,
    new_insight_query_from_form,
    save_insight_query,
)
from thread.intel.sam_query import (
    load_sam_queries,
    new_sam_query_from_form,
    save_sam_query,
)
from thread.main import create_app
from thread.services.insights_display import build_insights_page_context


def test_save_radar_bookmark(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    q = new_insight_query_from_form(settings, name="Army IT", agency="Army", naics_codes="541512")
    assert q is not None
    save_insight_query(settings, q)
    assert len(load_insight_queries(settings)) == 1


def test_delete_radar_bookmark(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    q = new_insight_query_from_form(settings, name="Delete me", recipient="Acme")
    assert q is not None
    save_insight_query(settings, q)
    assert delete_insight_query(settings, q.id) is True
    assert load_insight_queries(settings) == ()


def test_save_sam_bookmark(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    q = new_sam_query_from_form(settings, name="Cyber O", title="cyber", notice_type="o")
    assert q is not None
    save_sam_query(settings, q)
    assert len(load_sam_queries(settings)) == 1


def test_new_lens_rejects_empty_facets(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    assert new_insight_query_from_form(settings, name="Empty") is None
    assert new_sam_query_from_form(settings, name="Empty SAM") is None


@pytest.mark.asyncio
async def test_build_insights_page_context(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    state = tmp_path / ".thread"
    state.mkdir(parents=True)
    (state / "insight_queries.json").write_text(
        json.dumps([{"id": "army", "name": "Army", "agency": "Army"}]),
        encoding="utf-8",
    )

    ctx = await build_insights_page_context(db_session, settings)
    assert len(ctx.radar_lenses) == 1
    assert ctx.radar_lenses[0].summary.startswith("Agency:")
    assert ctx.naics_portfolio == ()


def test_insights_lens_tab_not_stuck_on_prior_lens():
    """Duplicate lens params (tab + stale form field) let the last value win — must not stick on agency."""
    client = TestClient(create_app())
    stuck = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": ["recompete", "agency"],
            "naics_codes": "561210",
        },
    )
    assert stuck.status_code == 200
    assert "insights-agency-lens" in stuck.text
    assert "insights-radar-explore" not in stuck.text

    recompete = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "recompete", "naics_codes": "561210"},
    )
    assert recompete.status_code == 200
    assert 'data-active-lens="recompete"' in recompete.text
    assert "insights-radar-explore" in recompete.text


def test_insights_agency_tab_browse_mode_after_slice():
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "agency", "naics_codes": "561210"},
    )
    assert res.status_code == 200
    html = res.text
    assert "Top agencies in the active slice" in html or "insights-idle-hint" in html
    assert 'name="lens"' not in html


def test_insights_slice_partial_idle():
    client = TestClient(create_app())
    res = client.get("/partials/insights/slice?lens=overview&run=0")
    assert res.status_code == 200
    assert "insights-slice-panel" in res.text
    assert "insights-lens-tabs" in res.text


def test_insights_slice_chart_options_valid_json():
    """Chart options must use single-quoted attrs — double-quoted tojson breaks HTML."""
    import json
    import re
    import socket
    from urllib.parse import urlparse

    from thread.config import Settings

    try:
        url = Settings().database_url
        host = urlparse(url.replace("+asyncpg", "")).hostname or "127.0.0.1"
        port = urlparse(url.replace("+asyncpg", "")).port or 5432
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError:
        pytest.skip("Postgres not ready")

    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "overview", "naics_codes": "561210"},
    )
    assert res.status_code == 200
    hosts = re.findall(r"data-chart-option='([^']*)'", res.text)
    assert len(hosts) >= 3
    for raw in hosts:
        option = json.loads(raw)
        assert option.get("series")


def test_insights_slice_partial_requires_facets():
    client = TestClient(create_app())
    res = client.get("/partials/insights/slice?lens=overview&run=1")
    assert res.status_code == 200
    assert "at least one facet" in res.text.lower() or "Set at least one facet" in res.text


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_insights_ui_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_insights_page_renders_live_explore():
    client = TestClient(create_app())
    res = client.get("/insights")
    html = res.text
    assert res.status_code == 200
    assert "insights-frame" in html
    assert "insights-radar-form" in html
    assert "Run slice" in html
    assert "Lens results" in html
    assert "Activate" not in html
    assert "Save current search" in html
    assert "guide-modal" in html
    assert "openGuideDialog" in html
    assert "btn-hero-magenta" in html
    assert "insights-bookmarks-drawer" in html
    assert "Clew" in html
    assert "data-insights-collapse" in html
    assert 'id="insights-facet-card"' in html
    assert "insights-facet-toolbar" in html
    assert "insights-facet-primary" in html
    assert 'id="insights-lenses-card"' in html
    assert 'id="insights-slice-panel"' in html
    assert "hx-swap=\"outerHTML\"" in html
    assert 'action="/partials/insights/slice"' not in html
    assert 'name="lens"' not in html
    assert 'hx-vals=\'{"lens": "overview"}\'' in html
    assert "slicePanelHasResults" in html
    assert "openLensesCard" in html
    assert "insights-award-drawer-root" in html
    assert "thread_insights_award_drawer" in html
    assert "thread_insights_session.js" in html
    assert 'id="insights-clear-btn"' in html
    assert ">Clear</button>" in html
    assert "NAICS portfolio config" in html
    assert "Add at least one facet" not in html
    assert "Shell stub" not in html
    assert "peer facets" in html.lower() or "peer facet" in html.lower() or "peer dimensions" in html.lower()