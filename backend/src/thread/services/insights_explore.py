"""Live Data Insights explore — no save/activate required."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.slice_cache import get_cached_explore_rows, store_cached_explore_rows
from thread.intel import pg_queries as intel_queries
from thread.intel.charts import enrich_expiring_rows_shape_gates
from thread.intel.facet_query import ADVANCED_FACET_FIELDS, InsightFacetQuery, describe_query, query_from_dict
from thread.intel.sam_query import SamMonitorQuery, describe_sam_query, query_from_dict as sam_from_dict
from thread.mcp.service import MCPService
from thread.services.insights_entity import EntityContext, entity_from_params, explore_query_for_entity
from thread.services.sam_monitor import build_sam_explore_results


def _sam_configured(settings: Settings) -> bool:
    mcp = MCPService(settings)
    sam_srv = next((s for s in mcp.list_servers() if s["id"] == "sam_gov"), None)
    return bool(sam_srv and sam_srv["configured"])


@dataclass(frozen=True)
class RadarExploreResult:
    query: InsightFacetQuery | None
    summary: str
    rows: tuple[dict[str, Any], ...]
    intel_live: bool
    status: str = "idle"
    error: str | None = None
    cache_hit: bool = False
    cache_age_seconds: float | None = None


@dataclass(frozen=True)
class SamExploreResult:
    query: SamMonitorQuery | None
    summary: str
    notices: tuple[dict[str, Any], ...]
    status: str
    error: str | None
    configured: bool


def _facet_from_params(
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    min_obligation: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    exclude_agencies: str = "",
) -> InsightFacetQuery | None:
    raw = {
        "id": "explore",
        "name": "Live explore",
        "agency": agency.strip() or None,
        "sub_agency": sub_agency.strip() or None,
        "recipient": recipient.strip() or None,
        "naics_codes": naics_codes.strip(),
        "psc_codes": psc_codes.strip(),
        "min_obligation": min_obligation.strip() or None,
    }
    for field in ADVANCED_FACET_FIELDS:
        value = locals().get(field, "")
        raw[field] = (value or "").strip() or None
    return query_from_dict(raw)


def _sam_from_params(
    *,
    title: str = "",
    agency_keyword: str = "",
    naics_code: str = "",
    psc_code: str = "",
    notice_type: str = "",
    set_aside: str = "",
    days_back: int = 14,
    limit: int = 12,
) -> SamMonitorQuery | None:
    raw = {
        "id": "sam-explore",
        "name": "SAM explore",
        "title": title.strip() or None,
        "agency_keyword": agency_keyword.strip() or None,
        "naics_code": naics_code.strip() or None,
        "psc_code": psc_code.strip() or None,
        "notice_type": notice_type.strip() or None,
        "set_aside": set_aside.strip() or None,
        "days_back": days_back,
        "limit": limit,
    }
    return sam_from_dict(raw)


def _radar_has_input(**kwargs: str) -> bool:
    return any((kwargs.get(key) or "").strip() for key in (
        "agency",
        "sub_agency",
        "recipient",
        "naics_codes",
        "psc_codes",
        *ADVANCED_FACET_FIELDS,
    ))


async def explore_radar(
    session: AsyncSession,
    settings: Settings,
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    min_obligation: str = "",
    exclude_agencies: str = "",
    limit: int = 15,
    run: bool = False,
    entity_kind: str = "",
    entity_value: str = "",
    entity_scope: str = "",
) -> RadarExploreResult:
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)
    query = _facet_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_obligation=min_obligation,
        exclude_agencies=exclude_agencies,
    )
    facet_input = {
        "agency": agency,
        "sub_agency": sub_agency,
        "recipient": recipient,
        "naics_codes": naics_codes,
        "psc_codes": psc_codes,
        "min_obligation": min_obligation,
        "awarding_office": awarding_office,
        "funding_office": funding_office,
        "recipient_uei": recipient_uei,
        "pop_state": pop_state,
        "extent_competed": extent_competed,
        "type_of_set_aside": type_of_set_aside,
        "exclude_agencies": exclude_agencies,
    }
    if query is None:
        if not run and not _radar_has_input(**facet_input):
            return RadarExploreResult(
                query=None,
                summary="",
                rows=(),
                intel_live=intel_live,
                status="idle",
            )
        return RadarExploreResult(
            query=None,
            summary="",
            rows=(),
            intel_live=intel_live,
            status="no_query",
            error="Add at least one facet — agency, recipient, NAICS, PSC, or combo.",
        )
    if not intel_live:
        return RadarExploreResult(
            query=query,
            summary=describe_query(query),
            rows=(),
            intel_live=False,
            status="loading",
            error="PG intel not ready — resume migration.",
        )
    entity: EntityContext | None = entity_from_params(
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
    )
    if run:
        cache = get_cached_explore_rows(
            settings,
            query,
            entity_kind=entity.kind if entity else "",
            entity_scope=entity.scope if entity else "",
            entity_value=entity.value if entity else "",
        )
        if cache and cache.explore_rows is not None:
            summary = describe_query(query)
            if entity and entity.is_active():
                summary = f"{entity.display_label} · {summary}"
            cached_rows = list(cache.explore_rows)
            explore_query = explore_query_for_entity(query, entity)
            if explore_query is not None:
                cached_rows = await enrich_expiring_rows_shape_gates(
                    session, explore_query, cached_rows
                )
            status = "ready" if cached_rows else "empty"
            return RadarExploreResult(
                query=query,
                summary=summary,
                rows=tuple(cached_rows),
                intel_live=True,
                status=status,
                cache_hit=True,
                cache_age_seconds=cache.age_seconds,
            )

    explore_query = explore_query_for_entity(query, entity)
    assert explore_query is not None
    rows = await intel_queries.get_expiring_contracts_for_query(
        session,
        explore_query,
        months_ahead=18,
        limit=limit,
    )
    rows = await enrich_expiring_rows_shape_gates(session, explore_query, rows)
    if run:
        store_cached_explore_rows(
            settings,
            query,
            rows,
            entity_kind=entity.kind if entity else "",
            entity_scope=entity.scope if entity else "",
            entity_value=entity.value if entity else "",
        )
    status = "ready" if rows else "empty"
    summary = describe_query(query)
    if entity and entity.is_active():
        summary = f"{entity.display_label} · {summary}"
    return RadarExploreResult(
        query=query,
        summary=summary,
        rows=tuple(rows),
        intel_live=True,
        status=status,
    )


def _sam_has_input(
    *,
    title: str = "",
    agency_keyword: str = "",
    naics_code: str = "",
    psc_code: str = "",
    notice_type: str = "",
    set_aside: str = "",
) -> bool:
    return bool(
        title.strip()
        or agency_keyword.strip()
        or naics_code.strip()
        or psc_code.strip()
        or notice_type.strip()
        or set_aside.strip()
    )


async def explore_sam(
    settings: Settings,
    *,
    title: str = "",
    agency_keyword: str = "",
    naics_code: str = "",
    psc_code: str = "",
    notice_type: str = "",
    set_aside: str = "",
    days_back: int = 14,
    limit: int = 12,
    run: bool = False,
) -> SamExploreResult:
    query = _sam_from_params(
        title=title,
        agency_keyword=agency_keyword,
        naics_code=naics_code,
        psc_code=psc_code,
        notice_type=notice_type,
        set_aside=set_aside,
        days_back=days_back,
        limit=limit,
    )
    if query is None:
        if not run and not _sam_has_input(
            title=title,
            agency_keyword=agency_keyword,
            naics_code=naics_code,
            psc_code=psc_code,
            notice_type=notice_type,
            set_aside=set_aside,
        ):
            return SamExploreResult(
                query=None,
                summary="",
                notices=(),
                status="idle",
                error=None,
                configured=_sam_configured(settings),
            )
        return SamExploreResult(
            query=None,
            summary="",
            notices=(),
            status="no_query",
            error="Add at least one SAM facet besides date window.",
            configured=False,
        )
    widget = await build_sam_explore_results(settings, query)
    notices = [
        {
            "notice_id": n.notice_id,
            "title": n.title,
            "agency": n.agency,
            "solicitation_number": n.solicitation_number,
            "notice_type": n.notice_type,
            "set_aside": n.set_aside,
            "naics_code": n.naics_code,
            "posted_date": n.posted_date,
            "response_deadline": n.response_deadline,
        }
        for n in widget.notices
    ]
    return SamExploreResult(
        query=query,
        summary=describe_sam_query(query),
        notices=tuple(notices),
        status=widget.status,
        error=widget.error,
        configured=widget.configured,
    )