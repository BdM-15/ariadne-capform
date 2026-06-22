"""Shared intel ECharts — Overview lens option builders."""

from thread.intel.echarts_options import attach_overview_echarts


def test_attach_overview_echarts_builds_intensity_and_kpi_charts():
    overview = {
        "mode": "overview",
        "kpis": {"millions": 10.5, "award_count": 100},
        "spend_trend": [{"year": 2024, "millions": 5.0, "actions": 50}],
        "agency_intensity": {
            "points": [
                {"agency": "DEPT A", "actions": 10, "millions": 5.0, "hot": True},
                {"agency": "DEPT B", "actions": 2, "millions": 1.0, "hot": False},
            ],
            "median_actions": 6,
            "median_millions": 3.0,
            "hot_agencies": ["DEPT A"],
        },
        "agency_sub_flow": [{"label": "ARMY", "kind": "sub_agency", "actions": 5, "millions": 3.0}],
        "agency_sub_flow_group": "sub_agency",
        "set_aside": [{"bucket": "NO SET ASIDE USED", "actions": 10, "millions": 4.0}],
        "extent_competed": [{"extent": "FULL AND OPEN COMPETITION", "actions": 8, "millions": 3.5}],
        "top_recipients": [{"recipient": "ACME LLC", "actions": 4, "millions": 2.0}],
    }
    out = attach_overview_echarts(overview)
    charts = out.get("charts") or {}
    assert "intensity" in charts
    assert charts["intensity"]["series"][0]["type"] == "scatter"
    assert "sub_flow" in charts
    assert "set_aside" in charts
    assert charts["set_aside"]["series"][0]["type"] == "pie"