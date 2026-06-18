"""Phase 17b — Clew MCP live overlay."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from thread.clew.mcp_overlay import _extract_rows, fetch_mcp_overlay
from thread.config import get_settings
from thread.intel.facet_query import InsightFacetQuery


def test_extract_rows_from_award_results():
    payload = {
        "results": [
            {
                "Recipient Name": "Acme Federal LLC",
                "Awarding Agency": "Department of the Army",
                "Award Amount": 2500000,
                "Award ID": "ABC123",
            }
        ]
    }
    rows = _extract_rows(
        payload,
        title_keys=("Recipient Name",),
        subtitle_keys=("Awarding Agency",),
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "Acme Federal LLC"
    assert rows[0]["amount"] == "$2.50M"


@pytest.mark.asyncio
async def test_fetch_mcp_overlay_skipped_when_not_requested():
    settings = get_settings()
    query = InsightFacetQuery(id="t", name="t", recipient="Acme")
    out = await fetch_mcp_overlay(settings, query, "money_flow", include_mcp=False)
    assert out["enabled"] is False
    assert out["status"] == "skipped"


@pytest.mark.asyncio
async def test_fetch_mcp_overlay_usaspending_layer():
    settings = get_settings()
    settings = settings.model_copy(update={"enable_live_mcps": True})
    query = InsightFacetQuery(id="t", name="t", recipient="Acme")

    mock_service = MagicMock()
    mock_service.invoke = AsyncMock(
        return_value={
            "ok": True,
            "output": '{"results": [{"Recipient Name": "Acme Corp", "Award Amount": 1000000}]}',
        }
    )

    out = await fetch_mcp_overlay(
        settings,
        query,
        "money_flow",
        include_mcp=True,
        mcp_service=mock_service,
    )
    assert out["enabled"] is True
    assert out["status"] == "ready"
    assert len(out["layers"]) == 1
    assert out["layers"][0]["server"] == "usaspending"
    assert out["layers"][0]["rows"][0]["title"] == "Acme Corp"
    mock_service.invoke.assert_awaited_once()


