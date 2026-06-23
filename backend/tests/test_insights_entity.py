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


def test_explore_query_for_entity_scopes_recipient():
    from thread.services.insights_entity import explore_query_for_entity, entity_from_params

    base = _facet_from_params(naics_codes="561210")
    entity = entity_from_params(entity_kind="competitor", entity_value="Acme Federal LLC")
    assert base is not None and entity is not None
    scoped = explore_query_for_entity(base, entity)
    assert scoped is not None
    assert scoped.naics_codes == ("561210",)
    assert scoped.recipient == "Acme Federal LLC"


def test_insights_slice_has_entity_tabs():
    client = TestClient(create_app())
    res = client.get("/partials/insights/slice?lens=overview&run=0")
    assert res.status_code == 200
    assert ">Agency<" in res.text or ">Agency</button>" in res.text
    assert ">Competitor<" in res.text or ">Competitor</button>" in res.text