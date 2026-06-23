"""DR-style graph trace — multi-hop BFS + relation families."""

from thread.intel.echarts_options import attach_trace_echarts
from thread.intel.graph_trace import (
    EdgeKind,
    NodeKind,
    RelationFamily,
    EDGE_FAMILY,
    build_browse_funnel,
    extract_people_from_sam_entity,
    merge_graph_expand,
    merge_people_into_graph,
    people_edges_from_records,
)


def test_edge_family_includes_teaming_not_only_people():
    assert EDGE_FAMILY[EdgeKind.TEAMING] == RelationFamily.TEAMING
    assert EDGE_FAMILY[EdgeKind.CO_OCCURRENCE] == RelationFamily.CO_OCCURRENCE
    assert EDGE_FAMILY[EdgeKind.TEAMING_NETWORK] == RelationFamily.TEAMING
    assert EdgeKind.PERSON_AFFILIATION in EDGE_FAMILY
    assert RelationFamily.PEOPLE.value == "people"


def test_build_browse_funnel_from_relations():
    graph = {
        "relation_families": ["org_money", "teaming"],
        "edges": [
            {
                "source": "agency::Army",
                "target": "prime::Acme",
                "kind": "obligation",
                "family": "org_money",
                "millions": 5.0,
            },
        ],
    }
    funnel = build_browse_funnel(graph)
    assert funnel["flows"][0]["source"] == "Army"
    assert funnel["flows"][0]["target"] == "Acme"


def test_merge_graph_expand_adds_edges():
    base = {
        "nodes": [{"id": "prime::A", "label": "A", "kind": "prime"}],
        "edges": [],
        "summary": {"node_count": 1, "edge_count": 0},
    }
    expansion = {
        "node_id": "prime::A",
        "nodes": [{"id": "sub::B", "label": "B", "kind": "sub"}],
        "edges": [
            {
                "source": "prime::A",
                "target": "sub::B",
                "kind": "teaming",
                "family": "teaming",
                "millions": 1.0,
            }
        ],
    }
    merged = merge_graph_expand(base, expansion)
    assert len(merged["edges"]) == 1
    assert len(merged["nodes"]) == 2


def test_extract_people_from_sam_entity_pocs():
    payload = {
        "entityData": [
            {
                "pointsOfContact": {
                    "governmentBusinessPOC": {
                        "firstName": "Jane",
                        "lastName": "Doe",
                        "title": "President",
                    },
                    "electronicBusinessPOC": {
                        "firstName": "John",
                        "lastName": "Smith",
                        "title": "CFO",
                    },
                }
            }
        ]
    }
    people = extract_people_from_sam_entity(payload)
    assert len(people) == 2
    assert people[0]["name"] == "Jane Doe"
    assert people[0]["title"] == "President"


def test_merge_people_into_graph_adds_family():
    base = {
        "nodes": [{"id": "prime::Acme", "label": "Acme", "kind": "prime", "hop": 0}],
        "edges": [],
        "relation_families": [],
        "summary": {"node_count": 1, "edge_count": 0},
    }
    people_edges = people_edges_from_records("Acme", [{"name": "Jane Doe", "title": "CEO"}])
    merged = merge_people_into_graph(base, people_edges)
    assert "people" in merged["relation_families"]
    assert any(e["kind"] == "person_affiliation" for e in merged["edges"])
    assert any(n["kind"] == NodeKind.PERSON.value for n in merged["nodes"])


def test_attach_trace_includes_relations_graph():
    bundle = {
        "mode": "trace_lens",
        "relations_graph": {
            "relation_families": ["teaming", "org_money"],
            "nodes": [
                {"id": "prime::Acme", "label": "Acme", "kind": "prime", "millions_total": 12.0, "magnitude_tier": "high", "hop": 0},
                {"id": "agency::Army", "label": "Army", "kind": "agency", "millions_total": 12.0, "magnitude_tier": "high", "hop": 1},
            ],
            "edges": [
                {"source": "agency::Army", "target": "prime::Acme", "kind": "obligation", "millions": 12.0},
            ],
            "summary": {"max_hop": 1},
        },
        "browse_funnel": {
            "flows": [{"source": "Army", "target": "Acme", "millions": 12.0, "kind": "obligation"}],
        },
    }
    out = attach_trace_echarts(bundle)
    charts = out.get("charts") or {}
    assert charts["relations_graph"]["series"][0]["type"] == "graph"
    assert charts["relations_graph"]["_intel"]["mode"] == "relations_graph"
    assert "browse_funnel" in charts