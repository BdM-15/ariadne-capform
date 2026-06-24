"""Motion entry-lane verdict + channel helpers."""

from thread.intel.charts import _normalize_channel_rows
from thread.intel.echarts_options import attach_overview_echarts
from thread.services.insights_overview import overview_motion_brief


def test_normalize_channel_rows_orders_and_pct():
    rows = _normalize_channel_rows(
        [
            {"channel": "set_aside_non_competed", "millions": 30.0, "actions": 10},
            {"channel": "open_competed", "millions": 70.0, "actions": 40},
        ]
    )
    assert rows[0]["channel"] == "open_competed"
    assert rows[0]["pct"] == 70.0
    assert rows[1]["label"] == "Set-aside · sole/NC"


def test_overview_motion_brief_flags_sub_only_lane():
    motion = {
        "channels": [
            {"channel": "open_competed", "label": "Open · competed", "millions": 20.0, "pct": 20.0},
            {"channel": "set_aside_non_competed", "label": "Set-aside · sole/NC", "millions": 60.0, "pct": 60.0},
            {"channel": "vehicle_gated", "label": "IDV / vehicle", "millions": 20.0, "pct": 20.0},
        ],
        "timing": {"insight": "Q4 skews more set-aside — 55% of Q4 obligations vs 40% Oct–Jun."},
        "teaming_targets": [
            {
                "bucket": "8(A) SOLE SOURCE",
                "millions": 40.0,
                "primes": [{"recipient": "Small Prime LLC", "millions": 25.0, "actions": 5}],
            }
        ],
        "parent_shadow": {"parent_backed_pct": 35.0, "eight_a_parent_pct": 12.0},
        "expiring_channels": [
            {"channel": "open_competed", "millions": 5.0, "pct": 10.0},
            {"channel": "set_aside_non_competed", "millions": 45.0, "pct": 90.0},
        ],
        "money_paths": [
            {
                "agency": "Department of Defense",
                "channel_label": "Set-aside · sole/NC",
                "recipient": "Small Prime LLC",
                "millions": 12.0,
            }
        ],
    }
    brief = overview_motion_brief(motion, recompete_m=50.0)
    assert "60%" in brief["headline"]
    assert "sub/teaming" in brief["headline"]
    assert any("cannot prime" in b.lower() for b in brief["bullets"])
    assert any("vehicle" in b.lower() for b in brief["bullets"])
    assert brief["actions"][0]["entity_kind"] == "competitor"
    assert brief["teaming_targets"][0]["bucket"].startswith("8")


def test_attach_overview_echarts_builds_motion_charts():
    overview = {
        "spend_trend": [{"year": 2024, "millions": 5.0, "actions": 50}],
        "agency_intensity": {"points": []},
        "motion": {
            "channels": [
                {"channel": "open_competed", "label": "Open · competed", "millions": 4.0, "pct": 80.0, "actions": 4},
                {"channel": "set_aside_non_competed", "label": "Set-aside · sole/NC", "millions": 1.0, "pct": 20.0, "actions": 1},
            ],
            "timing": {
                "periods": [
                    {
                        "channel": "open_competed",
                        "label": "Open · competed",
                        "rest_millions": 3.0,
                        "q4_millions": 1.0,
                        "rest_mix_pct": 75.0,
                        "q4_mix_pct": 100.0,
                    }
                ],
                "rest_total_millions": 4.0,
                "q4_total_millions": 1.0,
                "insight": "",
            },
            "expiring_channels": [
                {"channel": "open_competed", "label": "Open · competed", "millions": 2.0, "pct": 100.0, "actions": 2},
            ],
            "parent_shadow": {
                "independent_millions": 2.0,
                "parent_backed_millions": 1.0,
                "independent_pct": 66.7,
                "parent_backed_pct": 33.3,
                "eight_a_parent_millions": 0.5,
            },
            "money_paths": [
                {
                    "agency": "DEPT A",
                    "channel": "open_competed",
                    "channel_label": "Open · competed",
                    "recipient": "ACME LLC",
                    "millions": 2.0,
                }
            ],
        },
    }
    out = attach_overview_echarts(overview)
    charts = out.get("charts") or {}
    assert "motion_channels" in charts
    assert charts["motion_channels"]["series"][0]["stack"] == "tam"
    assert "motion_channel_leaders" not in charts
    assert "motion_q4_timing" in charts
    assert charts["motion_q4_timing"]["series"][0]["stack"] == "mix"
    assert "motion_expiring_channels" in charts
    assert "motion_parent_shadow" in charts
    assert "motion_money_paths" in charts
    assert charts["motion_money_paths"]["series"][0]["type"] == "sankey"