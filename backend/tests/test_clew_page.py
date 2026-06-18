"""Clew standalone page."""

import pytest
from fastapi.testclient import TestClient

from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_clew_page_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_clew_page_loads():
    client = TestClient(create_app())
    res = client.get("/clew")
    assert res.status_code == 200
    assert "clew-body" in res.text
    assert "clew-facet-form" in res.text
    assert "clew-results-panel" in res.text
    assert "Set search facets in the form above" in res.text
    assert "clew-drawer-root" not in res.text
    assert "guide-clew" in res.text
    assert "openGuideDialog('guide-clew')" in res.text
    assert "echarts.min.js" in res.text
    assert "clew_charts.js" in res.text
    assert 'name="include_mcp"' in res.text
    assert "Live MCP supplement" in res.text
    assert "How to use" in res.text
    assert "substring search" in res.text


def test_clew_prefill_query():
    client = TestClient(create_app())
    res = client.get("/clew?recipient=Acme&agency=Army&mode=teaming&run=0")
    assert res.status_code == 200
    assert "Acme" in res.text
    assert "Army" in res.text


def test_sidebar_lists_clew():
    client = TestClient(create_app())
    res = client.get("/pulse")
    assert 'href="/clew"' in res.text


def test_insights_links_clew_not_embedded_card():
    client = TestClient(create_app())
    res = client.get("/insights")
    assert 'href="/clew"' in res.text
    assert 'id="insights-clew"' not in res.text