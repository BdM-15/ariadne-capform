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


def test_save_radar_bookmark_refreshes_facet_list(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    client = TestClient(create_app())
    res = client.post(
        "/insights/radar/save",
        data={
            "name": "Army IT",
            "agency": "Army",
            "naics_codes": "541512",
            "min_contract_value": "1M",
            "exclude_agencies": "Department of Energy",
        },
    )
    assert res.status_code == 200
    assert "hx-swap-oob" in res.text
    assert "Army IT" in res.text
    assert "insights-facet-bookmark-chip" in res.text
    assert "insights-bookmarks-drawer-root" in res.text


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

    legacy_recompete = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "recompete", "naics_codes": "561210"},
    )
    assert legacy_recompete.status_code == 200
    assert 'data-active-lens="overview"' in legacy_recompete.text
    assert "insights-slice-expiring" in legacy_recompete.text or "insights-result-row" in legacy_recompete.text
    assert ">Recompete<" not in legacy_recompete.text


def test_insights_agency_tab_browse_mode_after_slice():
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "agency", "naics_codes": "561210"},
    )
    assert res.status_code == 200
    html = res.text
    assert "Top contracting offices in the active slice" in html or "insights-idle-hint" in html
    assert 'name="lens"' not in html


def test_insights_slice_partial_idle():
    client = TestClient(create_app())
    res = client.get("/partials/insights/slice?lens=overview&run=0")
    assert res.status_code == 200
    assert "insights-stage-content" in res.text
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
    assert (
        "at least one facet" in res.text.lower()
        or "set at least one facet" in res.text.lower()
        or "set facets" in res.text.lower()
    )


def test_insights_slice_post_entity_drill_keeps_facets():
    """Long office names must POST with form body — GET URLs truncate and drop facets."""
    client = TestClient(create_app())
    long_office = "W6QK ACC-APG " + ("FIELD OFFICE " * 60)
    res = client.post(
        "/partials/insights/slice",
        data={
            "run": "1",
            "lens": "agency",
            "naics_codes": "541512",
            "agency": "Department of Energy",
            "min_contract_value": "1M",
            "entity_kind": "agency",
            "entity_scope": "office",
            "entity_value": long_office,
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert 'data-has-slice="1"' in res.text
    assert "Back to Overview" in res.text
    assert long_office[:32] in res.text


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_insights_ui_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_insights_award_partial_route():
    client = TestClient(create_app())
    res = client.get("/partials/insights/award", params={"award_key": "CONT_AWD_TEST"})
    assert res.status_code == 200
    assert "insights-award-panel" in res.text or "award" in res.text.lower()


def test_entity_state_is_div_not_form():
    """JS must not use FormData() on #insights-entity-state — it's a hidden-field div."""
    client = TestClient(create_app())
    res = client.get("/partials/insights/slice", params={"lens": "overview", "run": 0})
    assert res.status_code == 200
    assert '<div id="insights-entity-state"' in res.text
    assert '<form id="insights-entity-state"' not in res.text


@pytest.mark.asyncio
async def test_expiring_award_partial_returns_profile():
    import re
    import socket
    from urllib.parse import urlparse

    from httpx import ASGITransport, AsyncClient

    from thread.config import Settings

    try:
        url = Settings().database_url
        host = urlparse(url.replace("+asyncpg", "")).hostname or "127.0.0.1"
        port = urlparse(url.replace("+asyncpg", "")).port or 5432
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError:
        pytest.skip("Postgres not ready")

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        slice_res = await client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "overview", "naics_codes": "561210"},
        )
        keys = re.findall(r'data-award-key="([^"]+)"', slice_res.text)
        assert keys, "expiring rows should include award keys"
        award_res = await client.get("/partials/insights/award", params={"award_key": keys[0]})
    assert award_res.status_code == 200
    assert "Database error loading award" not in award_res.text
    assert "Award not found" not in award_res.text
    assert "insights-award-panel" in award_res.text
    assert "task-drawer-section" in award_res.text
    assert "Could not load contract profile" not in award_res.text
    assert "FormData" not in award_res.text


def test_expiring_rows_use_award_drawer_htmx():
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
    assert 'class="insights-award-open' in res.text
    assert 'data-award-key="' in res.text


def test_insights_page_renders_live_explore():
    client = TestClient(create_app())
    res = client.get("/insights")
    html = res.text
    assert res.status_code == 200
    assert "insights-workspace" in html
    assert "insights-radar-form" in html
    assert "Run slice" in html
    assert "Lens results" in html
    assert "guide-modal" in html
    assert "openGuideDialog('guide-data-insights')" in html
    assert "guide-data-insights" in html
    assert "btn-hero-magenta" in html
    assert "insights-bookmarks-drawer" in html
    assert 'id="insights-stage-content"' in html
    assert 'hx-target="#insights-stage-content"' in html
    assert 'hx-vals=\'{"lens": "overview"}\'' in html
    assert "insights-award-drawer-root" in html
    assert "thread_insights.js" in html
    assert ">Recompete<" not in html
    assert 'id="insights-clear-btn"' in html
    assert "Save bookmark" in html
    assert "openInsightsSaveBookmarkDrawer" in html
    assert 'name="name"' not in html.split("insights-radar-form")[1].split("</form>")[0]
    assert "Quick NAICS" in html or "Edit quick NAICS" in html
    assert "Add at least one facet" not in html
    assert "Shell stub" not in html
    assert "peer facets" in html.lower() or "peer facet" in html.lower() or "peer dimensions" in html.lower()