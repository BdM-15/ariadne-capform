"""Phase 17b.1 — Clew ?path= deep-link encode/decode."""

from thread.clew.path_link import (
    analysis_from_path,
    clew_path_href,
    encode_path_param,
    parse_path_param,
)


def test_parse_and_encode_roundtrip():
    edges = [
        {"source": "Acme Corp", "target": "Department of Army", "value": 12.5},
        {"source": "Beta LLC", "target": "DISA", "value": 3.2},
    ]
    raw = encode_path_param(edges)
    assert parse_path_param(raw) == edges


def test_parse_escapes_commas_in_names():
    raw = r"Acme\, Inc,Army,4.5"
    parsed = parse_path_param(raw)
    assert len(parsed) == 1
    assert parsed[0]["source"] == "Acme, Inc"
    assert parsed[0]["target"] == "Army"
    assert parsed[0]["value"] == 4.5


def test_analysis_from_path_builds_sankey_chart():
    analysis = analysis_from_path(
        mode="money_flow",
        edges=[{"source": "Recipient A", "target": "Agency B", "value": 8.0}],
    )
    assert analysis["path_preloaded"] is True
    assert analysis["chart"]["series"][0]["type"] == "sankey"


def test_clew_path_href_includes_path_query():
    href = clew_path_href(
        mode="teaming",
        source="Prime Co",
        target="Sub Co",
        value=1.25,
        agency="Army",
    )
    assert href.startswith("/clew?")
    assert "path=" in href
    assert "mode=teaming" in href
    assert "agency=Army" in href


def test_clew_page_renders_path_preload():
    from fastapi.testclient import TestClient

    from thread.main import create_app

    client = TestClient(create_app())
    res = client.get("/clew?path=Acme%20Corp,Army,12.5&mode=money_flow")
    assert res.status_code == 200
    assert "deep-link path" in res.text
    assert "clew-echarts-host" in res.text
    assert "Pre-loaded path" in res.text