"""Phase 17e-g — Competition, Trace, and entity profile ECharts builders."""

from thread.intel.echarts_options import (
    _relations_force_graph,
    attach_competition_echarts,
    attach_entity_echarts,
    attach_trace_echarts,
)


def test_relations_force_graph_handles_negative_millions():
    graph = {
        "nodes": [
            {
                "id": "prime::A",
                "label": "A",
                "kind": "prime",
                "millions_total": -1.5,
                "magnitude_tier": "low",
            },
            {
                "id": "agency::B",
                "label": "B",
                "kind": "agency",
                "millions_total": 12.0,
                "magnitude_tier": "high",
            },
        ],
        "edges": [
            {
                "source": "agency::B",
                "target": "prime::A",
                "kind": "obligation",
                "millions": -2.0,
            }
        ],
        "relation_families": ["org_money"],
        "summary": {"max_hop": 1},
    }
    chart = _relations_force_graph(graph)
    assert chart is not None
    assert chart["series"][0]["data"][0]["symbolSize"] >= 14


def test_attach_entity_echarts_includes_heatmap_and_sankeys():
    profile = {
        "mode": "competitor_profile",
        "spend_trend": [{"year": 2024, "millions": 1.0, "actions": 2}],
        "agency_recipient_matrix": {
            "cells": [
                {"agency": "DEPT A", "recipient": "ACME", "actions": 5, "millions": 2.0},
            ],
            "agencies": ["DEPT A"],
            "recipients": ["ACME"],
        },
        "money_flow": [{"recipient": "ACME", "agency": "DEPT A", "millions": 2.0}],
        "teaming": [{"prime": "ACME", "sub": "SUBCO", "millions": 0.5}],
        "set_aside": [{"bucket": "NO SET ASIDE USED", "millions": 1.0}],
        "extent_competed": [{"extent": "FULL AND OPEN COMPETITION", "millions": 1.0}],
        "pricing_buckets": [{"bucket": "Firm fixed", "millions": 0.8}],
    }
    out = attach_entity_echarts(profile, "competitor")
    charts = out.get("charts") or {}
    assert charts["relationship_heatmap"]["series"][0]["type"] == "heatmap"
    assert charts["money_flow"]["series"][0]["type"] == "sankey"
    assert charts["teaming"]["series"][0]["type"] == "sankey"
    assert "pricing_buckets" in charts


def test_attach_competition_echarts_ffp_and_vehicles():
    bundle = {
        "mode": "competition_lens",
        "set_aside": [{"bucket": "SBA", "millions": 3.0}],
        "extent_competed": [{"extent": "FULL AND OPEN", "millions": 2.0}],
        "pricing_buckets": [{"bucket": "Firm fixed", "millions": 4.0}],
        "vehicle_breakdown": [
            {"pricing": "FFP", "vehicle": "IDIQ", "millions": 2.0},
            {"pricing": "T&M", "vehicle": "IDIQ", "millions": 1.0},
        ],
        "idv_split": [{"channel": "IDV / Task Order", "millions": 5.0}],
        "ffp_shaping": {
            "agency_pressure": [
                {"agency": "DEPT A", "non_fixed_pct": 42.0, "pressure_tier": "moderate"},
            ],
        },
    }
    out = attach_competition_echarts(bundle)
    charts = out.get("charts") or {}
    assert "ffp_pressure" in charts
    assert charts["ffp_pressure"]["series"][0]["type"] == "bar"
    assert "vehicle_breakdown" in charts
    assert "pricing_buckets" in charts


def test_attach_trace_echarts_inline_dr():
    bundle = {
        "mode": "trace_lens",
        "money_flow": {
            "flows": [{"recipient": "ACME", "agency": "DEPT A", "millions": 1.5}],
        },
        "teaming": {"edges": [{"prime": "ACME", "sub": "SUB", "millions": 0.3}]},
        "agency_recipient_matrix": {
            "cells": [{"agency": "DEPT A", "recipient": "ACME", "actions": 3, "millions": 1.5}],
            "agencies": ["DEPT A"],
            "recipients": ["ACME"],
        },
    }
    out = attach_trace_echarts(bundle)
    charts = out.get("charts") or {}
    assert charts["money_flow"]["series"][0]["type"] == "sankey"
    assert charts["teaming"]["series"][0]["type"] == "sankey"
    assert charts["relationship_heatmap"]["series"][0]["type"] == "heatmap"