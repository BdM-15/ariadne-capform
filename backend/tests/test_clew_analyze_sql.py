"""Clew SQL — PostgreSQL round() must cast to numeric."""

import pytest
from fastapi.testclient import TestClient

from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_clew_money_flow_recipient_query_returns_200():
    client = TestClient(create_app())
    res = client.get(
        "/partials/clew/results",
        params={"recipient": "Amentum", "mode": "money_flow", "run": 1},
    )
    assert res.status_code == 200
    assert "clew-echarts-host" in res.text or "insights-explore-msg-warn" in res.text