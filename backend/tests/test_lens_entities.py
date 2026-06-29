"""Per-lens entity memory + agency overview brief."""

from thread.intel.facet_query import InsightFacetQuery
from thread.services.insights_entity import (
    EntityContext,
    _contractors_with_share,
    agency_overview_brief,
    agency_sam_forward_query,
    resolve_lens_entities,
)


def test_agency_sam_forward_query_broad_by_default():
    entity = EntityContext(kind="agency", value="DEPT OF HOMELAND SECURITY", scope="agency")
    q = agency_sam_forward_query(entity, InsightFacetQuery(id="t", name="t", naics_codes=("561210",)))
    assert q.agency_keyword == "DEPT OF HOMELAND SECURITY"
    assert q.naics_code is None
    assert q.days_back == 90


def test_agency_sam_forward_query_naics_optional():
    entity = EntityContext(kind="agency", value="CISA", scope="sub_agency")
    slice_q = InsightFacetQuery(id="t", name="t", naics_codes=("541512", "561210"))
    q = agency_sam_forward_query(entity, slice_q, match_naics=True)
    assert q.naics_code == "541512"


def test_contractors_with_share():
    rows = _contractors_with_share(
        [{"recipient": "A", "millions": 3.0}, {"recipient": "B", "millions": 1.0}],
        4.0,
    )
    assert rows[0]["share_pct"] == 75.0
    assert rows[1]["share_pct"] == 25.0


def test_resolve_lens_entities_keeps_agency_when_competitor_drilled():
    active, agency, competitor = resolve_lens_entities(
        lens="agency",
        agency_entity_value="KO Shop A",
        agency_entity_scope="office",
        competitor_entity_value="ACME LLC",
        competitor_entity_scope="recipient",
    )
    assert agency is not None and agency.value == "KO Shop A"
    assert competitor is not None and competitor.value == "ACME LLC"
    assert active is not None and active.value == "KO Shop A"


def test_legacy_drill_merges_into_competitor_slot_only():
    _, agency, competitor = resolve_lens_entities(
        lens="competitor",
        agency_entity_value="KO Shop A",
        agency_entity_scope="office",
        entity_kind="competitor",
        entity_value="ACME LLC",
        entity_scope="recipient",
    )
    assert agency is not None and agency.value == "KO Shop A"
    assert competitor is not None and competitor.value == "ACME LLC"


def test_entity_award_spine_trace_filter_adds_buyer_predicate():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from thread.intel.charts import entity_award_spine
    from thread.intel.facet_query import InsightFacetQuery

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.first.return_value = MagicMock(total_contracts=3, total_recipients=2)
    result_mock.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    async def _run():
        q = InsightFacetQuery(id="t", name="t", naics_codes="561210")
        return await entity_award_spine(
            session,
            q,
            entity_scope="office",
            trace_buyer_office="W4MM USA JOINT MUNITIONS CMD",
        )

    asyncio.run(_run())
    sql = session.execute.await_args_list[1].args[0].text
    assert ":trace_buyer_office" in sql
    assert session.execute.await_args_list[1].args[1]["trace_buyer_office"] == (
        "W4MM USA JOINT MUNITIONS CMD"
    )


def test_entity_award_spine_empty_without_filters():
    import asyncio
    from unittest.mock import AsyncMock

    from thread.intel.charts import entity_award_spine
    from thread.intel.facet_query import InsightFacetQuery

    async def _run():
        session = AsyncMock()
        q = InsightFacetQuery(id="t", name="t")
        result = await entity_award_spine(session, q, entity_scope="office")
        session.execute.assert_not_called()
        return result

    result = asyncio.run(_run())
    assert result["rows"] == []
    assert result["mode"] == "entity_award_spine"


def test_agency_overview_office_cards():
    entity = EntityContext(kind="agency", value="KO Shop", scope="office", label="Office · KO Shop")
    brief = agency_overview_brief(
        entity,
        {
            "kpis": {"millions": 12.4, "recipient_count": 8, "award_count": 40},
            "hierarchy": {"parent_agency": "Dept X", "parent_sub": "Sub Y"},
            "office_customer_trace": {"funding_office_count": 5},
            "set_aside": [{"bucket": "SBA", "millions": 4.0}],
            "top_contractors": [{"recipient": "ACME", "millions": 5.0}],
        },
        recompete_rows=[{"shape_gate": "shape_now", "obligation_millions": 1.2}],
    )
    assert "Dept X" in brief["hierarchy_line"]
    assert len(brief["cards"]) == 4
    assert brief["cards"][0]["id"] == "obligated"