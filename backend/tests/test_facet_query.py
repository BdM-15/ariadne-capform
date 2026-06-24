"""Facet queries — no NAICS default; operator-defined search only."""

from thread.intel.facet_query import (
    MIN_VALUE_BASIS_OBLIGATED,
    MIN_VALUE_BASIS_POTENTIAL,
    InsightFacetQuery,
    build_facet_sql,
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


def test_query_accepts_awarding_office_only():
    q = query_from_dict(
        {
            "id": "office",
            "name": "Army CIO",
            "awarding_office": "W6QK ACC-APG",
        }
    )
    assert q is not None
    assert q.awarding_office == "W6QK ACC-APG"
    sql, params = build_facet_sql(q)
    assert "awarding_office_name ILIKE" in sql
    assert params["awarding_office"] == "%W6QK ACC-APG%"


def test_query_accepts_recipient_uei():
    q = query_from_dict(
        {
            "id": "uei",
            "name": "UEI lookup",
            "recipient_uei": "ABC123DEF456",
        }
    )
    assert q is not None
    assert "UEI: ABC123DEF456" in describe_query(q)


def test_min_contract_value_defaults_to_potential_column():
    q = query_from_dict({"id": "big", "name": "Big deals", "naics_codes": "561210", "min_contract_value": "1M"})
    assert q is not None
    assert q.min_contract_value == 1_000_000.0
    assert q.min_value_basis == MIN_VALUE_BASIS_POTENTIAL
    sql, params = build_facet_sql(q)
    assert "potential_total_value_of_award" in sql
    assert "federal_action_obligation" not in sql
    assert params["min_contract_value"] == 1_000_000.0
    assert "Min potential value" in describe_query(q)


def test_min_contract_value_obligated_basis():
    q = query_from_dict(
        {
            "id": "funded",
            "name": "Funded floor",
            "naics_codes": "561210",
            "min_contract_value": "500000",
            "min_value_basis": "obligated",
        }
    )
    assert q is not None
    assert q.min_value_basis == MIN_VALUE_BASIS_OBLIGATED
    sql, _ = build_facet_sql(q)
    assert "total_dollars_obligated" in sql
    assert "Min total obligated" in describe_query(q)


def test_min_contract_value_reads_legacy_min_obligation_key():
    q = query_from_dict({"id": "legacy", "name": "Legacy", "naics_codes": "561210", "min_obligation": "2M"})
    assert q is not None
    assert q.min_contract_value == 2_000_000.0


def test_bookmark_open_vals_includes_advanced_facets():
    from thread.intel.facet_query import bookmark_open_vals, format_contract_value_floor

    q = query_from_dict(
        {
            "id": "prime",
            "name": "Prime NAICS",
            "naics_codes": "561210",
            "min_contract_value": "500M",
            "min_value_basis": "potential",
            "exclude_agencies": "Department of Energy",
        }
    )
    assert q is not None
    assert format_contract_value_floor(q.min_contract_value) == "500M"
    vals = bookmark_open_vals(q)
    assert vals["min_contract_value"] == "500M"
    assert vals["min_value_basis"] == "potential"
    assert vals["exclude_agencies"] == "Department of Energy"
    assert vals["naics_codes"] == "561210"


def test_exclude_agencies_filter_sql():
    q = query_from_dict(
        {
            "id": "no-doe",
            "name": "561210 w/o DOE",
            "naics_codes": "561210",
            "exclude_agencies": "Department of Energy, DOE",
        }
    )
    assert q is not None
    assert q.exclude_agencies == ("Department of Energy", "DOE")
    sql, params = build_facet_sql(q)
    assert "NOT" in sql
    assert params["exclude_agency_0"] == "%Department of Energy%"
    assert "Exclude:" in describe_query(q)


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