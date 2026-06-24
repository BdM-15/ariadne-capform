"""Expiring timeline + per-award shape gate badges (Phase 2c)."""

from thread.intel.charts import _award_shape_gate
from thread.intel.echarts_options import attach_overview_echarts
from thread.intel.sql_expressions import BASE_AWARD_WHERE, is_base_award
from thread.services.insights_overview import overview_chart_guides


def test_is_base_award_modification_zero():
    assert is_base_award("0") is True
    assert is_base_award(0) is True
    assert is_base_award("1") is False
    assert is_base_award("P00001") is False
    assert is_base_award(None) is False


def test_base_award_where_filters_modifications():
    assert "modification_number" in BASE_AWARD_WHERE
    assert "'0'" in BASE_AWARD_WHERE


def test_award_shape_gate_firm_fixed_skipped():
    gate, reason = _award_shape_gate(
        pricing_bucket="firm_fixed",
        agency_non_fixed_pct=50.0,
        pressure_tier="high",
        obligation_millions=2.0,
        pricing_label="FIRM FIXED PRICE",
    )
    assert gate is None
    assert reason is None


def test_award_shape_gate_shape_now_threshold():
    gate, reason = _award_shape_gate(
        pricing_bucket="time_materials",
        agency_non_fixed_pct=40.0,
        pressure_tier="moderate",
        obligation_millions=0.6,
        pricing_label="TIME AND MATERIALS",
    )
    assert gate == "shape_now"
    assert "early shaping" in (reason or "").lower()


def test_award_shape_gate_monitor_on_pressure():
    gate, _ = _award_shape_gate(
        pricing_bucket="cost_reimbursement",
        agency_non_fixed_pct=28.0,
        pressure_tier="moderate",
        obligation_millions=0.1,
        pricing_label="COST PLUS FIXED FEE",
    )
    assert gate == "monitor"


def test_award_shape_gate_watch_low_pressure():
    gate, _ = _award_shape_gate(
        pricing_bucket="other",
        agency_non_fixed_pct=10.0,
        pressure_tier="low",
        obligation_millions=1.0,
        pricing_label="OTHER",
    )
    assert gate == "watch"


def test_attach_overview_echarts_builds_expiring_timeline():
    overview = {
        "spend_trend": [],
        "agency_intensity": {"points": []},
        "expiring_timeline": {
            "buckets": [
                {"month": "2026-03", "millions": 4.5, "contracts": 12, "actions": 12},
                {"month": "2026-04", "millions": 2.0, "contracts": 5, "actions": 5},
            ],
            "peak_millions": 4.5,
            "insight": "Peak cluster Mar 2026 — $4.5M across 12 contracts",
        },
    }
    out = attach_overview_echarts(overview)
    charts = out.get("charts") or {}
    assert "expiring_timeline" in charts
    assert "title" not in charts["expiring_timeline"]
    assert charts["expiring_timeline"]["series"][0]["type"] == "bar"
    assert charts["expiring_timeline"]["series"][1]["type"] == "line"


def test_attach_overview_expiring_timeline_thins_x_labels_when_many_buckets():
    buckets = [
        {"month": f"2026-{m:02d}", "millions": float(m), "actions": m}
        for m in range(1, 19)
    ]
    overview = {
        "spend_trend": [],
        "agency_intensity": {"points": []},
        "expiring_timeline": {"buckets": buckets, "peak_millions": 18.0, "insight": ""},
    }
    chart = attach_overview_echarts(overview)["charts"]["expiring_timeline"]
    axis = chart["xAxis"]["axisLabel"]
    assert axis["fontSize"] == 8
    assert axis.get("hideOverlap") is True


def test_overview_chart_guides_include_expiring_timeline():
    guides = overview_chart_guides()
    assert "expiring_timeline" in guides
    assert "shape" in guides["expiring_timeline"]["use"].lower()
    assert "modification" in guides["expiring_timeline"]["read"].lower() or "base contract" in guides["expiring_timeline"]["read"].lower()