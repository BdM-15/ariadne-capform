"""Phase 17e-g — Entity profile lenses (Agency + Competitor drill-down within active slice)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.charts import (
    adjacent_competitors,
    agency_adjacent_competitors,
    agency_sub_flow,
    buyer_customer_trace,
    entity_award_spine,
    entity_obligation_flow,
    entity_recipient_matrix,
    expiring_timeline,
    extent_competed_breakdown,
    money_flow,
    pricing_bucket_breakdown,
    set_aside_breakdown,
    spend_trend,
    teaming,
    teaming_targets,
    top_recipients,
)
from thread.intel.slice_cache import get_cached_entity_profile, store_cached_entity_profile
from thread.intel.echarts_options import attach_entity_echarts
from thread.intel.facet_query import InsightFacetQuery, build_facet_sql
from thread.intel.sql_expressions import EXPIRING_MONTHS_AHEAD
from thread.intel import pg_queries as intel_queries
from thread.intel.charts import enrich_expiring_rows_shape_gates
from thread.intel.pg_parallel import gather_pg
from thread.intel.pg_queries import table_exists
from thread.intel.sam_query import SamMonitorQuery, describe_sam_query
from thread.intel.sql_expressions import AGENCY_EXPR, PRIME_TABLE, round_numeric
from thread.services.sam_monitor import build_sam_explore_results


ENTITY_SCOPES = frozenset({"agency", "sub_agency", "office", "recipient"})


@dataclass(frozen=True)
class EntityContext:
    kind: str
    value: str
    scope: str = "agency"
    label: str = ""

    def is_active(self) -> bool:
        return bool(self.value.strip())

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        return self.value


def resolve_lens_entities(
    *,
    lens: str,
    agency_entity_value: str = "",
    agency_entity_scope: str = "",
    competitor_entity_value: str = "",
    competitor_entity_scope: str = "",
    entity_kind: str = "",
    entity_value: str = "",
    entity_scope: str = "",
) -> tuple[EntityContext | None, EntityContext | None, EntityContext | None]:
    """Per-lens entity memory — legacy entity_* merges into matching slot on drill."""
    agency = entity_from_params(
        entity_kind="agency",
        entity_value=agency_entity_value,
        entity_scope=agency_entity_scope or "agency",
    )
    competitor = entity_from_params(
        entity_kind="competitor",
        entity_value=competitor_entity_value,
        entity_scope=competitor_entity_scope or "recipient",
    )
    legacy = entity_from_params(
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
    )
    if legacy:
        if legacy.kind == "competitor":
            competitor = legacy
        else:
            agency = legacy
    active: EntityContext | None = None
    if lens == "agency":
        active = agency
    elif lens == "competitor":
        active = competitor
    return active, agency, competitor


def entity_from_params(
    *,
    entity_kind: str = "",
    entity_value: str = "",
    entity_scope: str = "",
) -> EntityContext | None:
    value = entity_value.strip()
    if not value:
        return None
    kind = (entity_kind or "").strip().lower()
    scope = (entity_scope or kind or "agency").strip().lower()
    if kind not in {"agency", "competitor"}:
        if scope == "recipient":
            kind = "competitor"
        else:
            kind = "agency"
    if scope not in ENTITY_SCOPES:
        scope = "recipient" if kind == "competitor" else "agency"
    label = value
    if kind == "agency" and scope == "sub_agency":
        label = f"Sub-agency · {value}"
    elif kind == "agency" and scope == "office":
        label = f"Office · {value}"
    elif kind == "competitor":
        label = value
    return EntityContext(kind=kind, value=value, scope=scope, label=label)


def scoped_slice_query(slice_query: InsightFacetQuery, entity: EntityContext) -> InsightFacetQuery:
    """Apply entity focus on top of the operator slice — facets are additive, not replaced."""
    if entity.kind == "competitor":
        return replace(slice_query, recipient=entity.value)
    if entity.scope == "sub_agency":
        return replace(slice_query, sub_agency=entity.value)
    if entity.scope == "office":
        return replace(slice_query, awarding_office=entity.value)
    return replace(slice_query, agency=entity.value)


@dataclass(frozen=True)
class EntityProfileResult:
    entity: EntityContext
    profile: dict[str, Any]
    status: str
    error: str | None = None
    cache_hit: bool = False
    cache_age_seconds: float | None = None


async def build_entity_profile(
    session: AsyncSession,
    settings: Settings,
    slice_query: InsightFacetQuery | None,
    entity: EntityContext | None,
    *,
    lens: str,
) -> EntityProfileResult:
    if entity is None or not entity.is_active():
        return EntityProfileResult(
            entity=entity or EntityContext(kind=lens, value="", scope="agency"),
            profile={"idle": True},
            status="idle",
        )
    if slice_query is None or not slice_query.has_filters():
        return EntityProfileResult(
            entity=entity,
            profile={},
            status="no_slice",
            error="Run a facet slice on Overview first, then drill into an entity.",
        )
    if not await table_exists(session, PRIME_TABLE):
        return EntityProfileResult(
            entity=entity,
            profile={},
            status="loading",
            error="PG intel not ready — resume migration.",
        )

    cache = get_cached_entity_profile(
        settings,
        slice_query,
        kind=entity.kind,
        scope=entity.scope,
        value=entity.value,
    )
    if cache and cache.entity_profile:
        profile = attach_entity_echarts(dict(cache.entity_profile), entity.kind)
        return EntityProfileResult(
            entity=entity,
            profile=profile,
            status="ready",
            cache_hit=True,
            cache_age_seconds=cache.age_seconds,
        )

    scoped = scoped_slice_query(slice_query, entity)
    try:
        if entity.kind == "competitor":
            raw = await _competitor_profile(session, scoped, entity, slice_query, settings)
        else:
            raw = await _agency_profile(session, scoped, entity, slice_query)
    except Exception as exc:  # pragma: no cover — surfaced in UI
        return EntityProfileResult(
            entity=entity,
            profile={},
            status="error",
            error=str(exc),
        )

    if raw.get("error"):
        return EntityProfileResult(
            entity=entity,
            profile=raw,
            status="error",
            error=str(raw["error"]),
        )

    # Decision-grade for every agency scope (incl. office) — recompete timing drives go/no-go.
    raw["recompete_rows"] = await fetch_entity_recompete(session, slice_query, entity)
    store_cached_entity_profile(
        settings,
        slice_query,
        kind=entity.kind,
        scope=entity.scope,
        value=entity.value,
        profile=raw,
    )
    profile = attach_entity_echarts(raw, entity.kind)
    return EntityProfileResult(entity=entity, profile=profile, status="ready")


async def fetch_entity_recompete(
    session: AsyncSession,
    slice_query: InsightFacetQuery,
    entity: EntityContext,
    *,
    months_ahead: int = EXPIRING_MONTHS_AHEAD,
    limit: int = 10,
) -> list[dict[str, Any]]:
    scoped = scoped_slice_query(slice_query, entity)
    rows = await intel_queries.get_expiring_contracts_for_query(
        session,
        scoped,
        months_ahead=months_ahead,
        limit=limit,
    )
    return await enrich_expiring_rows_shape_gates(session, scoped, rows)


def explore_query_for_entity(
    slice_query: InsightFacetQuery | None,
    entity: EntityContext | None,
) -> InsightFacetQuery | None:
    if slice_query is None or entity is None or not entity.is_active():
        return slice_query
    return scoped_slice_query(slice_query, entity)


async def fetch_trace_award_spine(
    session: AsyncSession,
    slice_query: InsightFacetQuery,
    entity: EntityContext,
    *,
    trace_buyer_office: str = "",
    trace_recipient: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Award spine rows scoped to graph/heatmap trace focus (not just global top-N)."""
    scoped = scoped_slice_query(slice_query, entity)
    return await entity_award_spine(
        session,
        scoped,
        entity_scope=entity.scope,
        limit=limit,
        trace_buyer_office=trace_buyer_office.strip() or None,
        trace_recipient=trace_recipient.strip() or None,
    )


async def _competition_mix(
    session: AsyncSession,
    scoped: InsightFacetQuery,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(scoped)
    set_aside, extent, pricing = await gather_pg(
        lambda s: set_aside_breakdown(s, facet_sql, facet_params),
        lambda s: extent_competed_breakdown(s, facet_sql, facet_params),
        lambda s: pricing_bucket_breakdown(s, facet_sql, facet_params),
    )
    return {"set_aside": set_aside, "extent_competed": extent, "pricing_buckets": pricing}


async def _agency_profile(
    session: AsyncSession,
    scoped: InsightFacetQuery,
    entity: EntityContext,
    slice_query: InsightFacetQuery,
) -> dict[str, Any]:
    """Decision-grade Agency profile (agency / sub-agency / office) — all queries in parallel.

    Office scope used to run a lighter subset for speed; with the M0 NAICS/office composite
    indexes + parallel fan-out + slice cache it now returns the full relationship picture
    (money flow, agency×recipient heat map, pricing mix, top agencies) like any agency drill.
    """
    facet_sql, facet_params = build_facet_sql(scoped)
    (
        kpis,
        contractors,
        spend,
        sub_flow,
        agencies_for_matrix,
        set_aside,
        extent,
        pricing,
        matrix,
        flow,
        customer_trace,
        award_spine,
        hierarchy,
        teaming,
        adjacent,
        expiring_tl,
    ) = await gather_pg(
        lambda s: _entity_kpis(s, scoped),
        lambda s: top_recipients(s, scoped, limit=12),
        lambda s: spend_trend(s, scoped, limit=12),
        lambda s: agency_sub_flow(s, scoped, limit=12),
        lambda s: _top_agencies_in_scope(s, scoped, limit=10),
        lambda s: set_aside_breakdown(s, facet_sql, facet_params),
        lambda s: extent_competed_breakdown(s, facet_sql, facet_params),
        lambda s: pricing_bucket_breakdown(s, facet_sql, facet_params),
        lambda s: entity_recipient_matrix(s, scoped, entity_scope=entity.scope, limit=100),
        lambda s: entity_obligation_flow(s, scoped, entity_scope=entity.scope, limit=14),
        lambda s: buyer_customer_trace(
            s, scoped, root_label=entity.value, root_scope=entity.scope,
        ),
        lambda s: entity_award_spine(s, scoped, entity_scope=entity.scope, limit=20),
        lambda s: _agency_hierarchy(s, scoped, entity),
        lambda s: teaming_targets(s, facet_sql, facet_params),
        lambda s: agency_adjacent_competitors(s, scoped, entity_scope=entity.scope, limit=8),
        lambda s: expiring_timeline(s, facet_sql, facet_params),
    )

    total_m = float(kpis.get("millions") or 0)
    contractors = _contractors_with_share(contractors, total_m)

    profile: dict[str, Any] = {
        "status": "ready",
        "mode": "agency_profile",
        "entity": {
            "kind": entity.kind,
            "value": entity.value,
            "scope": entity.scope,
            "label": entity.display_label,
        },
        "kpis": kpis,
        "top_contractors": contractors,
        "spend_trend": spend.get("bars") or [],
        "agency_sub_flow": sub_flow.get("rows") or [],
        "agency_sub_flow_group": sub_flow.get("group"),
        "top_agencies": agencies_for_matrix,
        "agency_recipient_matrix": matrix,
        "money_flow": flow,
        "slice_summary": _slice_hint(slice_query),
        "set_aside": set_aside,
        "extent_competed": extent,
        "pricing_buckets": pricing,
        "hierarchy": hierarchy,
        "teaming_targets": teaming,
        "adjacent_competitors": adjacent,
        "expiring_timeline": expiring_tl,
        "award_spine": award_spine,
    }
    if customer_trace.get("flows"):
        profile["customer_trace"] = customer_trace
        if entity.scope == "office":
            profile["office_customer_trace"] = customer_trace
    return profile


async def _competitor_profile(
    session: AsyncSession,
    scoped: InsightFacetQuery,
    entity: EntityContext,
    slice_query: InsightFacetQuery,
    settings: Settings,
) -> dict[str, Any]:
    kpis = await _entity_kpis(session, scoped)
    identity = await _recipient_identity(session, scoped, entity.value)
    spend = await spend_trend(session, scoped, limit=12)
    top_agencies = await _top_agencies_in_scope(session, scoped, limit=12)
    top_naics = await _top_naics_in_scope(session, scoped, limit=10)
    subs = await teaming(session, scoped, limit=10)
    competition = await _competition_mix(session, scoped)
    matrix = await agency_recipient_matrix(session, scoped, limit=100)
    flow = await money_flow(session, scoped, limit=14)
    adjacent = await adjacent_competitors(session, slice_query, entity.value, limit=8)

    return {
        "status": "ready",
        "mode": "competitor_profile",
        "entity": {
            "kind": entity.kind,
            "value": entity.value,
            "scope": entity.scope,
            "label": entity.display_label,
        },
        "identity": identity,
        "kpis": kpis,
        "spend_trend": spend.get("bars") or [],
        "top_agencies": top_agencies,
        "top_naics": top_naics,
        "teaming": subs.get("edges") or [],
        "teaming_error": subs.get("error"),
        "agency_recipient_matrix": matrix,
        "money_flow": flow.get("flows") or [],
        "adjacent_competitors": adjacent,
        "slice_summary": _slice_hint(slice_query),
        **competition,
    }


async def _entity_kpis(
    session: AsyncSession,
    query: InsightFacetQuery,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            COUNT(*) AS award_count,
            COUNT(DISTINCT recipient_name) AS recipient_count,
            COUNT(DISTINCT ({AGENCY_EXPR})) AS agency_count,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
    """
    row = (await session.execute(text(sql), facet_params)).one()
    return {
        "award_count": int(row.award_count or 0),
        "recipient_count": int(row.recipient_count or 0),
        "agency_count": int(row.agency_count or 0),
        "millions": float(row.millions or 0),
    }


async def _recipient_identity(
    session: AsyncSession,
    query: InsightFacetQuery,
    recipient: str,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            recipient_name AS recipient,
            MAX(recipient_uei) AS recipient_uei,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY recipient_name
        ORDER BY millions DESC NULLS LAST
        LIMIT 1
    """
    row = (await session.execute(text(sql), facet_params)).first()
    if not row:
        return {"recipient": recipient, "recipient_uei": None, "actions": 0, "millions": 0.0}
    return {
        "recipient": row.recipient,
        "recipient_uei": (row.recipient_uei or "").strip() or None,
        "actions": int(row.actions),
        "millions": float(row.millions or 0),
    }


async def _top_agencies_in_scope(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            ({AGENCY_EXPR}) AS agency,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE ({AGENCY_EXPR}) != ''
          {facet_sql}
        GROUP BY agency
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "agency": r.agency,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def _top_naics_in_scope(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            COALESCE(NULLIF(TRIM(naics_code), ''), '(Unknown)') AS naics,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY naics
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "naics": r.naics,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


_OPEN_SET_ASIDE = frozenset({"(Not Applicable)", "NO SET ASIDE USED", "No Set-Aside Used"})


def agency_overview_brief(
    entity: EntityContext,
    profile: dict[str, Any],
    *,
    recompete_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Agency tab overview row — metric cards + hierarchy line + one posture sentence."""
    kpis = profile.get("kpis") or {}
    hierarchy = profile.get("hierarchy") or {}
    office_trace = profile.get("customer_trace") or profile.get("office_customer_trace") or {}
    sub_flow = profile.get("agency_sub_flow") or []
    contractors = profile.get("top_contractors") or []
    set_aside = profile.get("set_aside") or []
    recompete = list(recompete_rows or profile.get("recompete_rows") or [])

    millions = float(kpis.get("millions") or 0)
    shape_now = sum(1 for r in recompete if r.get("shape_gate") == "shape_now")
    expiring_m = sum(float(r.get("obligation_millions") or 0) for r in recompete)

    set_total = sum(float(r.get("millions") or 0) for r in set_aside) or 0.0
    restricted_m = sum(
        float(r.get("millions") or 0)
        for r in set_aside
        if str(r.get("bucket") or "") not in _OPEN_SET_ASIDE
    )
    set_aside_pct = round(100.0 * restricted_m / set_total, 1) if set_total > 0 else 0.0

    top_share = 0.0
    if contractors and millions > 0:
        top_share = round(100.0 * float(contractors[0].get("millions") or 0) / millions, 1)

    hierarchy_line = _hierarchy_line(entity, hierarchy, sub_flow)

    cards: list[dict[str, str]] = [
        {
            "id": "obligated",
            "label": "Obligated",
            "value": f"${millions:.1f}M",
            "hint": "In active slice",
        },
    ]
    if entity.scope == "office":
        fund_n = int(office_trace.get("funding_office_count") or 0)
        cards.extend([
            {
                "id": "funding_offices",
                "label": "Funding offices",
                "value": str(fund_n),
                "hint": "Requirements owners served",
            },
            {
                "id": "contractors",
                "label": "Contractors",
                "value": str(kpis.get("recipient_count") or 0),
                "hint": "Primes in slice",
            },
            {
                "id": "recompete",
                "label": "Shape-now",
                "value": str(shape_now),
                "hint": f"{len(recompete)} expiring · ${expiring_m:.1f}M",
            },
        ])
    elif entity.scope == "sub_agency":
        cards.extend([
            {
                "id": "offices",
                "label": "Offices",
                "value": str(hierarchy.get("office_count") or 0),
                "hint": "Awarding offices in slice",
            },
            {
                "id": "concentration",
                "label": "Top prime share",
                "value": f"{top_share:.0f}%" if top_share else "—",
                "hint": "Largest contractor",
            },
            {
                "id": "recompete",
                "label": "Expiring",
                "value": str(len(recompete)),
                "hint": f"${expiring_m:.1f}M pipeline",
            },
        ])
    else:
        cards.extend([
            {
                "id": "subs",
                "label": "Sub-agencies",
                "value": str(len(sub_flow)),
                "hint": "Active in slice",
            },
            {
                "id": "concentration",
                "label": "Top prime share",
                "value": f"{top_share:.0f}%" if top_share else "—",
                "hint": "Largest contractor",
            },
            {
                "id": "set_aside",
                "label": "Set-aside mix",
                "value": f"{set_aside_pct:.0f}%" if set_total > 0 else "—",
                "hint": "Restricted obligations",
            },
        ])

    posture_parts: list[str] = []
    if set_aside_pct >= 25:
        posture_parts.append(f"{set_aside_pct:.0f}% set-aside — teammate lane likely")
    if entity.scope == "office" and int(office_trace.get("funding_office_count") or 0) >= 4:
        posture_parts.append("multi-customer shop — map funding offices before capture")
    if shape_now >= 1:
        posture_parts.append(f"{shape_now} shape-now expirations in slice")
    if top_share >= 40:
        posture_parts.append(f"concentrated ({top_share:.0f}% top prime)")
    posture = " · ".join(posture_parts) if posture_parts else "Open slice — drill charts below for lane mix."

    return {
        "hierarchy_line": hierarchy_line,
        "cards": cards,
        "posture": posture,
    }


def _contractors_with_share(
    contractors: list[dict[str, Any]],
    total_millions: float,
) -> list[dict[str, Any]]:
    total = float(total_millions or 0) or 1.0
    return [
        {
            **row,
            "share_pct": round(100.0 * float(row.get("millions") or 0) / total, 1),
        }
        for row in contractors
    ]


def _hierarchy_line(
    entity: EntityContext,
    hierarchy: dict[str, Any],
    sub_flow: list[dict[str, Any]],
) -> str:
    if entity.scope == "office":
        parts = [
            hierarchy.get("parent_agency"),
            hierarchy.get("parent_sub"),
            entity.value,
        ]
        return " → ".join(str(p).strip() for p in parts if p and str(p).strip())
    if entity.scope == "sub_agency":
        parent = hierarchy.get("parent_agency") or ""
        if parent:
            return f"{parent} → {entity.value}"
        return entity.value
    top_subs = [r.get("label") for r in sub_flow[:3] if r.get("label")]
    if top_subs:
        return f"{entity.value} → {', '.join(top_subs)}"
    return entity.value


async def _agency_hierarchy(
    session: AsyncSession,
    scoped: InsightFacetQuery,
    entity: EntityContext,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(scoped)
    sql = f"""
        SELECT
            MAX(NULLIF(TRIM(({AGENCY_EXPR})), '')) AS parent_agency,
            MAX(NULLIF(TRIM(awarding_sub_agency_name), '')) AS parent_sub,
            COUNT(DISTINCT NULLIF(TRIM(awarding_office_name), '')) AS office_count
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
    """
    row = (await session.execute(text(sql), facet_params)).one()
    return {
        "parent_agency": (row.parent_agency or "").strip() or None,
        "parent_sub": (row.parent_sub or "").strip() or None,
        "office_count": int(row.office_count or 0),
    }


def _slice_hint(slice_query: InsightFacetQuery) -> str:
    parts: list[str] = []
    if slice_query.naics_codes:
        parts.append("NAICS " + ", ".join(slice_query.naics_codes))
    if slice_query.agency:
        parts.append(slice_query.agency)
    if slice_query.recipient:
        parts.append(slice_query.recipient)
    return " · ".join(parts) if parts else "active slice"


def agency_sam_forward_query(
    entity: EntityContext,
    slice_query: InsightFacetQuery | None,
    *,
    match_naics: bool = False,
) -> SamMonitorQuery:
    """Buyer-scoped SAM search — broad by default; optional slice NAICS chip."""
    keyword = entity.value.strip()
    naics: str | None = None
    if match_naics and slice_query and slice_query.naics_codes:
        naics = slice_query.naics_codes[0]
    digest = hashlib.sha256(
        f"{entity.scope}:{keyword}:{naics or ''}".encode(),
    ).hexdigest()[:12]
    return SamMonitorQuery(
        id=f"agency-fwd-{digest}",
        name=f"SAM forward · {entity.display_label[:48]}",
        agency_keyword=keyword,
        naics_code=naics,
        days_back=90,
        limit=15,
        description="Agency drill — buyer-scoped forward notices",
    )


async def fetch_agency_sam_forward(
    settings: Settings,
    entity: EntityContext,
    slice_query: InsightFacetQuery | None,
    *,
    match_naics: bool = False,
):
    from thread.services.insights_explore import SamExploreResult

    query = agency_sam_forward_query(entity, slice_query, match_naics=match_naics)
    widget = await build_sam_explore_results(settings, query)
    notices = tuple(
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
    )
    summary = describe_sam_query(query)
    if match_naics and query.naics_code:
        summary = f"{summary} · NAICS filter on"
    return SamExploreResult(
        query=query,
        summary=summary,
        notices=notices,
        status=widget.status,
        error=widget.error,
        configured=widget.configured,
    )