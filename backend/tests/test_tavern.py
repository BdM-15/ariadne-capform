"""Mission Control Tavern — router smoke tests."""

import pytest
from fastapi.testclient import TestClient

from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_tavern_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_tavern_health():
    client = TestClient(create_app())
    res = client.get("/tavern/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "Tavern backend ready"


def test_tavern_dashboard_html():
    client = TestClient(create_app())
    res = client.get("/tavern/dashboard")
    assert res.status_code == 200
    assert "Mission Control Tavern" in res.text
    assert "http://127.0.0.1:9622/tavern" in res.text


def test_tavern_router_importable():
    from tavern.router import router as tavern_router

    assert tavern_router is not None
    paths = {getattr(r, "path", None) for r in tavern_router.routes}
    assert "/health" in paths
    assert "/metrics" in paths