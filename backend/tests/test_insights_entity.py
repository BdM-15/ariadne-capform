"""Phase 17e-g — Entity profile drill-down lenses."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.main import create_app
from thread.services.insights_entity import entity_from_params, scoped_slice_query
from thread.services.insights_explore import _facet_from_params

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


if not _postgres_reachable():
    pytestmark = pytest.mark.skip(reason="Postgres not ready")


def test_entity_from_params_competitor():
    entity = entity_from_params(entity_kind="competitor", entity_value="Acme Corp")
    assert entity is not None
    assert entity.kind == "competitor"
    assert entity.scope == "recipient"


def test_scoped_slice_query_adds_agency_filter():
    base = _facet_from_params(naics_codes="561210")
    assert base is not None
    entity = entity_from_params(entity_kind="agency", entity_value="Department of Defense", entity_scope="agency")
    assert entity is not None
    scoped = scoped_slice_query(base, entity)
    assert scoped.naics_codes == ("561210",)
    assert scoped.agency == "Department of Defense"
    assert scoped.recipient is None


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_entity_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_insights_agency_drill_partial():
    client = TestClient(create_app())
    agency = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": "agency",
            "naics_codes": "561210",
            "entity_kind": "agency",
            "entity_value": "Department of Defense",
            "entity_scope": "agency",
        },
    )
    assert agency.status_code == 200
    html = agency.text
    assert "insights-agency-lens" in html
    assert "insights-entity-crumb" in html
    assert "Back to Overview" in html
    assert "Department of Defense" in html or "insights-explore-msg" in html


def test_insights_office_drill_is_decision_grade():
    """Office-scope Agency drill is no longer the lite placeholder profile (17e-g-a.1)."""
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": "agency",
            "naics_codes": "561210",
            "entity_kind": "agency",
            "entity_value": "Department of Defense",
            "entity_scope": "office",
        },
    )
    assert res.status_code == 200
    html = res.text
    assert "insights-agency-lens" in html
    assert "Placeholder until Agency polish" not in html


def test_explore_query_for_entity_scopes_recipient():
    from thread.services.insights_entity import explore_query_for_entity, entity_from_params

    base = _facet_from_params(naics_codes="561210")
    entity = entity_from_params(entity_kind="competitor", entity_value="Acme Federal LLC")
    assert base is not None and entity is not None
    scoped = explore_query_for_entity(base, entity)
    assert scoped is not None
    assert scoped.naics_codes == ("561210",)
    assert scoped.recipient == "Acme Federal LLC"


def test_insights_legacy_competition_lens_redirects_to_overview():
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": "competition",
            "naics_codes": "561210",
        },
    )
    assert res.status_code == 200
    html = res.text
    assert "insights-stage-content" in html
    assert "insights-overview-lens" in html
    assert "insights-competition-lens" not in html


def test_insights_graph_expand_requires_node_id():
    client = TestClient(create_app())
    res = client.get(
        "/api/insights/graph-expand",
        params={"naics_codes": "561210", "node_id": ""},
    )
    assert res.status_code == 400
    assert "node_id" in res.json().get("error", "")


def test_insights_legacy_trace_lens_redirects_to_overview():
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": "trace",
            "naics_codes": "561210",
        },
    )
    assert res.status_code == 200
    html = res.text
    assert "insights-stage-content" in html
    assert "insights-overview-lens" in html
    assert "insights-trace-lens" not in html


def test_insights_competitor_drill_relations_multi_hop_copy():
    client = TestClient(create_app())
    res = client.get(
        "/partials/insights/slice",
        params={
            "run": 1,
            "lens": "competitor",
            "naics_codes": "561210",
            "entity_kind": "competitor",
            "entity_value": "SAVANNAH RIVER NUCLEAR SOLUTIONS LLC",
            "entity_scope": "recipient",
        },
    )
    assert res.status_code == 200
    html = res.text
    assert "insights-competitor-lens" in html
    assert "Money flow" in html or "insights-explore-msg" in html


def test_insights_award_partial():
    client = TestClient(create_app())
    missing = client.get("/partials/insights/award", params={"award_key": "NO_SUCH_AWARD"})
    assert missing.status_code == 200
    assert "Award not found" in missing.text

    route = client.get("/partials/insights/award")
    assert route.status_code == 200
    assert "Missing award key" in route.text


def test_insights_slice_three_tabs_when_run():
    client = TestClient(create_app())
    idle = client.get("/partials/insights/slice?lens=overview&run=0")
    assert idle.status_code == 200
    assert "insights-lens-tabs-hidden" in idle.text

    res = client.get(
        "/partials/insights/slice",
        params={"run": 1, "lens": "overview", "naics_codes": "561210"},
    )
    assert res.status_code == 200
    html = res.text
    assert "insights-stage-content" in html
    assert ">Agency<" in html or ">Agency</button>" in html
    assert ">Competitor<" in html or ">Competitor</button>" in html
    assert ">Recompete<" not in html
    assert ">Trace<" not in html
    assert ">Competition<" not in html