"""Phase 2a — Overview verdict cards + slice brief."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from thread.config import Settings
from thread.intel.facet_query import query_from_dict
from thread.main import create_app
from thread.services.insights_overview import overview_capture_verdict, overview_chart_guides

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="THREAD_SKIP_PG_TESTS set",
)


def _postgres_reachable() -> bool:
    try:
        url = Settings().database_url
        host = urlparse(url.replace("+asyncpg", "")).hostname or "127.0.0.1"
        port = urlparse(url.replace("+asyncpg", "")).port or 5432
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def test_overview_chart_guides_cover_motion_fy_trend():
    guides = overview_chart_guides()
    motion = guides["motion_fy_trend"]
    assert "fiscal years" in motion["read"].lower()
    assert guides["intensity"]["use"]


def test_overview_capture_verdict_builds_six_cards():
    overview = {
        "kpis": {"millions": 120.5, "award_count": 400, "agency_count": 8, "recipient_count": 22},
        "spend_trend": [
            {"year": 2023, "millions": 40.0},
            {"year": 2024, "millions": 50.0},
        ],
        "agency_intensity": {"hot_agencies": ["Department of Defense", "Department of Energy"]},
        "top_recipients": [
            {"recipient": "Acme Federal LLC", "millions": 30.0},
            {"recipient": "Beta Systems", "millions": 20.0},
            {"recipient": "Gamma Corp", "millions": 10.0},
        ],
        "set_aside": [
            {"bucket": "(Not Applicable)", "millions": 60.0},
            {"bucket": "SMALL BUSINESS SET-ASIDE", "millions": 40.0},
        ],
    }
    query = query_from_dict(
        {
            "id": "t",
            "name": "t",
            "naics_codes": "561210",
        }
    )
    verdict = overview_capture_verdict(
        overview,
        query=query,
        pipeline={"count": 12, "millions": 8.2},
    )
    assert len(verdict["cards"]) == 6
    assert "motion_fy_trend" in verdict["chart_guides"]
    assert "motion_fy_backload" not in verdict["chart_guides"]
    assert all(c.get("tooltip") for c in verdict["cards"])
    assert verdict["cards"][0]["id"] == "tam"
    assert verdict["cards"][0]["value"] == "$120.5M"
    assert verdict["cards"][1]["value"] == "+25.0%"
    assert verdict["cards"][2]["hint"].startswith("12")
    assert len(verdict["shipley"]) == 4
    assert "brief" not in verdict


def test_overview_capture_verdict_shipley_shape_now_pursue():
    overview = {
        "kpis": {"millions": 80.0, "award_count": 200, "agency_count": 5},
        "spend_trend": [],
        "agency_intensity": {"hot_agencies": ["GSA"]},
        "top_recipients": [],
        "set_aside": [],
        "motion": {
            "channels": [
                {"channel": "open_competed", "millions": 50.0},
                {"channel": "set_aside_non_competed", "millions": 30.0},
            ],
            "teaming_targets": [],
        },
        "pricing_buckets": [{"bucket": "time_materials", "millions": 40.0}],
    }
    verdict = overview_capture_verdict(
        overview,
        pipeline={"count": 10, "millions": 5.0},
        expiring_rows=(
            {
                "recipient": "Shape Target LLC",
                "months_to_end": 5,
                "obligation": 1_000_000,
                "shape_gate": "shape_now",
                "shape_reason": "Early shaping window",
            },
        ),
    )
    shape = next(c for c in verdict["shipley"] if c["id"] == "shape_window")
    assert shape["gate"] == "pursue"


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_overview_verdict_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not _postgres_reachable(), reason="Postgres not ready")
async def test_overview_slice_renders_metric_cards_and_brief():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=120.0) as client:
        res = await client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "overview", "naics_codes": "561210"},
        )
    assert res.status_code == 200, res.text[:400]
    html = res.text
    assert "insights-metric-cards" in html
    assert "insights-slice-brief" not in html
    assert "insights-slice-bar" in html or "Explain slice" in html
    assert "insights-overview-hero-row" in html
    assert "insights-overview-section" in html
    assert "FY obligation pulse" in html or "motion_fy_trend" in html
    assert "Motion brief" in html or "direct-prime" in html
    assert "Entry lane mix" in html or "motion_channels" in html
    assert "Q4 mix shift" in html or "motion_q4_timing" in html
    assert "FY end-load index" not in html
    assert "Quarterly action rhythm" not in html
    assert "Market access" in html
    assert "Competitive landscape" in html
    assert "Capture gates" in html or "insights-shipley-section" in html
    assert "insights-kpi-strip" not in html
    assert "insights-metric-tip" in html
    assert "insights-chart-tip" in html
    assert "Capture gates" in html or "insights-shipley-section" in html