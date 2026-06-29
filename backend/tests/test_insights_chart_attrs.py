"""Regression — chart option JSON must be parseable in HTML attributes."""

from __future__ import annotations

import json
import os
import re
import socket
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.intel.echarts_options import attach_entity_echarts
from thread.main import create_app
from thread.ui.routes import templates

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="THREAD_SKIP_PG_TESTS set",
)

ATTR_RE = re.compile(
    r'data-chart-key="([^"]+)".*?data-chart-option=(["\'])(.*?)\2',
    re.DOTALL,
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


if not _postgres_reachable():
    pytestmark = pytest.mark.skip(reason="Postgres not ready")


def _assert_chart_attrs_parse(html: str) -> None:
    hosts = list(ATTR_RE.finditer(html))
    assert hosts, "expected at least one chart host"
    for m in hosts:
        key, quote, raw = m.group(1), m.group(2), m.group(3)
        assert quote == "'", f"{key} must use single-quoted data-chart-option (got {quote!r})"
        json.loads(raw)


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_chart_attr_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_overview_chart_attrs_use_single_quotes_and_parse(client):
    res = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "overview", "naics_codes": "561210"},
    )
    assert res.status_code == 200
    _assert_chart_attrs_parse(res.text)


def test_agency_lens_template_never_double_quotes_chart_json():
    """Formatter regression — double-quoted JSON breaks ECharts mount in the browser."""
    profile = attach_entity_echarts(
        {
            "mode": "agency_profile",
            "spend_trend": [{"year": 2024, "millions": 1.0, "actions": 2}],
            "agency_recipient_matrix": {
                "cells": [
                    {"agency": "DEPT A", "recipient": "ACME", "actions": 5, "millions": 2.0},
                ],
                "agencies": ["DEPT A"],
                "recipients": ["ACME"],
            },
            "money_flow": [{"recipient": "ACME", "agency": "DEPT A", "millions": 2.0}],
            "office_customer_trace": {
                "flows": [
                    {"source": "KO Shop", "target": "Program X", "millions": 1.5, "actions": 3},
                ],
                "relations_graph": {
                    "nodes": [
                        {
                            "id": "awarding_office::KO Shop",
                            "label": "KO Shop",
                            "kind": "awarding_office",
                            "millions_total": 1.5,
                            "magnitude_tier": "medium",
                        },
                    ],
                    "edges": [],
                },
                "summary": "1 funding offices",
            },
            "top_contractors": [
                {"recipient": "ACME", "millions": 2.0, "actions": 5, "share_pct": 100.0},
            ],
            "pricing_buckets": [{"bucket": "Firm fixed", "millions": 1.0}],
            "set_aside": [{"bucket": "Small Business", "millions": 0.5}],
            "extent_competed": [{"extent": "Full and Open", "millions": 1.5}],
            "expiring_timeline": {
                "buckets": [{"month": "2026-09", "contracts": 2, "millions": 1.2}],
                "insight": "Peak cluster Sep 2026",
            },
        },
        "agency",
    )
    entity = SimpleNamespace(
        display_label="Office · KO Shop",
        scope="office",
    )
    html = templates.get_template("partials/insights_agency_lens.html").render(
        {
            "entity_idle": False,
            "entity_ready": True,
            "entity_error": None,
            "entity": entity,
            "entity_profile": profile,
            "agency_overview": {"hierarchy_line": "DEPT A → KO Shop", "posture": "open slice"},
            "agency_sam_forward": type("Sam", (), {
                "status": "not_configured",
                "notices": (),
                "summary": "",
                "error": None,
            })(),
            "sam_match_naics": False,
            "active_lens": "agency",
            "overview_ready": False,
        }
    )
    assert 'data-chart-option="' not in html
    assert "How they buy" in html
    assert "Competitive landscape" in html
    assert "set_aside" in html
    assert "prime_share" in html
    assert "SAM forward" in html
    assert "entity_expiring_timeline" in html
    assert "Top contractors in slice" not in html
    _assert_chart_attrs_parse(html)


def test_agency_lens_renders_award_spine():
    html = templates.get_template("partials/insights_agency_lens.html").render(
        {
            "entity_idle": False,
            "entity_ready": True,
            "entity_error": None,
            "entity": SimpleNamespace(display_label="Office · KO Shop", scope="office"),
            "entity_profile": {
                "charts": {},
                "award_spine": {
                    "summary": "Top 1 of 2 contracts · 1 contractor",
                    "recompete_rows": [
                        {
                            "award_key": "CONT_AWD_1",
                            "piid": "W912HQ24C0001",
                            "recipient": "ACME LLC",
                            "agency": "Program X",
                            "obligation": 2_100_000.0,
                            "end_date": "2026-09-30",
                            "months_to_end": 3,
                        },
                    ],
                    "rows": [],
                },
            },
            "agency_overview": {"cards": []},
            "agency_sam_forward": type("Sam", (), {"status": "not_configured", "notices": ()})(),
            "sam_match_naics": False,
            "active_lens": "agency",
            "overview_ready": False,
        }
    )
    assert "insights-award-spine-panel" in html
    assert "insights-result-row" in html
    assert 'data-award-key="CONT_AWD_1"' in html
    assert "insights-trace-obligation-row--triple" in html