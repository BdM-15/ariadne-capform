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


def test_flow_paths_sankey_entity_obligation():
    analysis = {
        "mode": "entity_obligation_flow",
        "title": "Obligation paths — funding office → prime",
        "flows": [
            {"source": "Program X", "target": "ACME", "millions": 2.0},
            {"source": "ACME", "target": "SUBCO", "millions": 0.4},
        ],
    }
    from thread.intel.echarts_options import _flow_paths_sankey

    chart = _flow_paths_sankey(analysis)
    assert chart is not None
    assert chart["series"][0]["type"] == "sankey"
    links = chart["series"][0]["links"]
    assert len(links) == 2
    assert links[0]["value"] == 2.0
    assert links[1]["value"] == 0.4


def test_prime_share_bar_chart():
    from thread.intel.echarts_options import _prime_share_bar_chart

    chart = _prime_share_bar_chart([
        {"recipient": "ACME", "millions": 8.0, "share_pct": 40.0},
        {"recipient": "BETA", "millions": 4.0, "share_pct": 20.0},
    ])
    assert chart is not None
    assert chart["series"][0]["type"] == "bar"
    assert chart["_intel"]["mode"] == "prime_share"


def test_attach_entity_echarts_agency_customer_trace():
    profile = {
        "mode": "agency_profile",
        "customer_trace": {
            "mode": "customer_trace",
            "sankey_title": "Customer map — agency → sub-agency",
            "graph_title": "Customer trace — agency → sub-agencies → offices",
            "flows": [
                {"source": "DEPT A", "target": "CISA", "millions": 5.0, "actions": 10},
            ],
            "relations_graph": {
                "nodes": [
                    {"id": "agency::DEPT A", "label": "DEPT A", "kind": "agency", "millions_total": 5.0, "magnitude_tier": "medium"},
                    {"id": "sub_agency::CISA", "label": "CISA", "kind": "sub_agency", "millions_total": 5.0, "magnitude_tier": "medium"},
                ],
                "edges": [
                    {"source": "agency::DEPT A", "target": "sub_agency::CISA", "kind": "customer_trace", "millions": 5.0},
                ],
            },
        },
        "money_flow": {
            "mode": "entity_obligation_flow",
            "title": "Obligation paths — contracting office → prime",
            "flows": [{"source": "KO Shop", "target": "ACME", "millions": 1.5}],
        },
        "agency_recipient_matrix": {
            "row_axis": "awarding_office",
            "cells": [{"agency": "KO Shop", "recipient": "ACME", "actions": 3, "millions": 1.5}],
            "agencies": ["KO Shop"],
            "recipients": ["ACME"],
        },
    }
    out = attach_entity_echarts(profile, "agency")
    charts = out.get("charts") or {}
    assert charts["office_customer_flow"]["series"][0]["type"] == "sankey"
    assert "sub_flow" not in charts
    assert charts["money_flow"]["series"][0]["type"] == "sankey"
    assert "Contracting office" in charts["relationship_heatmap"]["title"]["text"]


def test_attach_entity_echarts_office_customer_trace():
    profile = {
        "mode": "agency_profile",
        "entity": {"kind": "agency", "value": "KO Shop A", "scope": "office"},
        "office_customer_trace": {
            "flows": [
                {"source": "KO Shop A", "target": "Program Office X", "millions": 4.2, "actions": 12},
                {"source": "KO Shop A", "target": "Program Office Y", "millions": 1.1, "actions": 3},
            ],
            "relations_graph": {
                "nodes": [
                    {"id": "awarding_office::KO Shop A", "label": "KO Shop A", "kind": "awarding_office", "millions_total": 5.3, "magnitude_tier": "medium"},
                    {"id": "funding_office::Program Office X", "label": "Program Office X", "kind": "funding_office", "millions_total": 4.2, "magnitude_tier": "medium"},
                ],
                "edges": [
                    {"source": "awarding_office::KO Shop A", "target": "funding_office::Program Office X", "kind": "customer_trace", "millions": 4.2},
                ],
            },
        },
        "money_flow": {
            "mode": "entity_obligation_flow",
            "title": "Obligation paths — funding office → prime",
            "flows": [{"source": "Program Office X", "target": "ACME", "millions": 1.5}],
        },
    }
    out = attach_entity_echarts(profile, "agency")
    charts = out.get("charts") or {}
    assert "office_customer_flow" not in charts
    assert "money_flow" not in charts
    assert charts["office_customer_graph"]["series"][0]["type"] == "graph"
    assert charts["office_customer_graph"].get("legend")


def test_heatmap_shows_twelve_recipients_and_y_zoom():
    from thread.intel.echarts_options import _agency_recipient_heatmap

    recipients = [f"PRIME CONTRACTOR {i} LLC" for i in range(12)]
    cells = [
        {"agency": "W90A US ARMY", "recipient": r, "actions": i + 1, "millions": float(i)}
        for i, r in enumerate(recipients)
    ]
    chart = _agency_recipient_heatmap({
        "row_axis": "funding_office",
        "cells": cells,
        "agencies": ["W90A US ARMY"],
        "recipients": recipients,
    })
    assert chart is not None
    assert len(chart["yAxis"]["data"]) == 12
    assert chart["dataZoom"]
    assert chart["_intel"]["tooltipTemplate"] == "relationship_heatmap"


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