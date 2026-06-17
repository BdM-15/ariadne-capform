"""Facet queries — no NAICS default; operator-defined search only."""

from thread.intel.facet_query import (
    InsightFacetQuery,
    describe_query,
    load_insight_queries,
    query_from_dict,
    resolve_active_radar_query,
)


def test_no_builtin_queries_by_default(settings):
    assert load_insight_queries(settings) == ()
    assert resolve_active_radar_query(settings) is None
    assert describe_query(None) == "No active search"


def test_query_accepts_agency_only_without_naics():
    q = query_from_dict({"id": "army", "name": "Army spend", "agency": "Department of the Army"})
    assert q is not None
    assert q.naics_codes == ()
    assert describe_query(q) == "Agency: Department of the Army"


def test_query_accepts_competitor_recipient():
    q = query_from_dict({"id": "incumbent", "name": "Incumbent scan", "recipient": "Acme Federal"})
    assert q is not None
    assert "Recipient: Acme Federal" in describe_query(q)


def test_query_rejects_empty_facets():
    assert query_from_dict({"id": "empty", "name": "Empty"}) is None


def test_active_query_from_file(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    state_dir = settings.resolve(settings.thread_state_dir)
    state_dir.mkdir(parents=True)
    (state_dir / "insight_queries.json").write_text(
        '[{"id": "q1", "name": "Army IT", "agency": "Army", "naics_codes": ["541512"]}]',
        encoding="utf-8",
    )
    (state_dir / "active_insight_query.json").write_text('{"id": "q1"}', encoding="utf-8")
    active = resolve_active_radar_query(settings)
    assert active is not None
    assert active.id == "q1"
    assert "Army" in describe_query(active)