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
        "set_aside": [{"bucket": "NO SET ASIDE USED", "actions": 10, "millions": 4.0}],
        "extent_competed": [{"extent": "FULL AND OPEN COMPETITION", "actions": 8, "millions": 3.5}],
        "top_recipients": [{"recipient": "ACME LLC", "actions": 4, "millions": 2.0}],
        "pricing_buckets": [{"bucket": "Firm fixed", "pricing_bucket": "firm_fixed", "actions": 6, "millions": 3.0}],
        "idv_split": [{"channel": "Standalone", "actions": 8, "millions": 5.0}],
    }
    out = attach_overview_echarts(overview)
    charts = out.get("charts") or {}
    assert "intensity" in charts
    assert "title" not in charts["intensity"]
    assert charts["intensity"]["_intel"]["overviewChart"] is True
    assert charts["intensity"]["series"][0]["type"] == "scatter"
    assert charts["intensity"]["_intel"]["tooltipTemplate"] == "intensity"
    assert "motion_fy_trend" in charts
    assert charts["motion_fy_trend"]["series"][1]["type"] == "line"
    assert "motion_fy_backload" not in charts
    assert "set_aside" in charts
    assert charts["set_aside"]["series"][0]["type"] == "pie"
    assert "pricing_buckets" in charts
    assert "idv_split" in charts


def test_intensity_scatter_uses_log_scale_when_spread_is_wide():
    overview = {
        "agency_intensity": {
            "points": [
                {"label": "BIG", "agency": "BIG", "actions": 1200, "millions": 800.0, "hot": True},
                {"label": "small", "agency": "small", "actions": 3, "millions": 0.4, "hot": False},
            ],
            "median_actions": 50,
            "median_millions": 40.0,
            "hone_field": "awarding_office",
            "level_label": "Awarding office",
        },
    }
    chart = attach_overview_echarts(overview)["charts"]["intensity"]
    assert chart["xAxis"]["type"] == "log"
    assert chart["yAxis"]["type"] == "log"
    assert chart["_intel"]["logScale"] is True
    assert chart["series"][0]["markArea"]["data"]