"""Phase 17b — Connect the dots / DataRepublican-method drill-down."""

import pytest
from fastapi.testclient import TestClient

from thread.intel.datarepublican import ANALYSIS_MODES
from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_drilldown_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_analysis_modes_defined():
    assert "money_flow" in ANALYSIS_MODES
    assert "spend_trend" in ANALYSIS_MODES
    assert "teaming" in ANALYSIS_MODES


def test_insights_page_connect_dots_section():
    client = TestClient(create_app())
    res = client.get("/insights")
    html = res.text
    assert res.status_code == 200
    assert "Connect the dots" in html
    assert "datarepublican.com" in html or "DataRepublican" in html
    assert "radar-drilldown" in html
    assert "Queue for review" in html
    assert "guide-connect-dots" in html


def test_drilldown_partial_idle():
    client = TestClient(create_app())
    res = client.get("/partials/insights/radar-drilldown")
    assert res.status_code == 200
    assert "DataRepublican" in res.text or "datarepublican" in res.text