"""Clew ECharts option builders."""

from thread.clew.charts import attach_echarts_option


def test_spend_trend_chart_option():
    analysis = {
        "mode": "spend_trend",
        "bars": [{"year": 2022, "millions": 10.5, "actions": 3, "pct": 100}],
    }
    out = attach_echarts_option(analysis)
    assert "chart" in out
    assert out["chart"]["series"][0]["type"] == "bar"
    assert out["chart"]["xAxis"]["data"] == ["2022"]


def test_money_flow_sankey_option():
    analysis = {
        "mode": "money_flow",
        "flows": [
            {"recipient": "Acme LLC", "agency": "Army", "millions": 5.0, "pct": 100},
        ],
    }
    out = attach_echarts_option(analysis)
    assert out["chart"]["series"][0]["type"] == "sankey"
    assert len(out["chart"]["series"][0]["links"]) == 1


def test_teaming_sankey_option():
    analysis = {
        "mode": "teaming",
        "edges": [{"prime": "Prime Co", "sub": "Sub Co", "millions": 2.0, "pct": 100}],
    }
    out = attach_echarts_option(analysis)
    assert out["chart"]["series"][0]["type"] == "sankey"


def test_recipient_landscape_bar_option():
    analysis = {
        "mode": "recipient_landscape",
        "recipients": [{"recipient": "Big Corp", "millions": 9.0, "pct": 100, "agency_count": 2, "actions": 4}],
    }
    out = attach_echarts_option(analysis)
    assert out["chart"]["series"][0]["type"] == "bar"


def test_skips_error_analysis():
    analysis = {"mode": "money_flow", "error": "no data"}
    out = attach_echarts_option(analysis)
    assert "chart" not in out