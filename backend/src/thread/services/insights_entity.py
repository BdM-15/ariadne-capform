"""Phase 17e-g — Entity profile lenses (Agency + Competitor drill-down within active slice)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.charts import (
    adjacent_competitors,
    agency_recipient_matrix,
    agency_sub_flow,
    extent_competed_breakdown,
    money_flow,
    pricing_bucket_breakdown,
    set_aside_breakdown,
    spend_trend,
    teaming,
    top_recipients,
)
from thread.intel.slice_cache import get_cached_entity_profile, store_cached_entity_profile
from thread.intel.echarts_options import attach_entity_echarts
from thread.intel.facet_query import InsightFacetQuery, build_facet_sql
from thread.intel import pg_queries as intel_queries
from thread.intel.charts import enrich_expiring_rows_shape_gates
from thread.intel.pg_queries import table_exists
from thread.intel.sql_expressions import AGENCY_EXPR, PRIME_TABLE, round_numeric


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
    months_ahead: int = 18,
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


async def _competition_mix(
    session: AsyncSession,
    scoped: InsightFacetQuery,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(scoped)
    set_aside = await set_aside_breakdown(session, facet_sql, facet_params)
    extent = await extent_competed_breakdown(session, facet_sql, facet_params)
    pricing = await pricing_bucket_breakdown(session, facet_sql, facet_params)
    return {"set_aside": set_aside, "extent_competed": extent, "pricing_buckets": pricing}


async def _agency_profile(
    session: AsyncSession,
    scoped: InsightFacetQuery,
    entity: EntityContext,
    slice_query: InsightFacetQuery,
) -> dict[str, Any]:
    kpis = await _entity_kpis(session, scoped)
    contractors = await top_recipients(session, scoped, limit=12)
    spend = await spend_trend(session, scoped, limit=12)
    sub_flow = await agency_sub_flow(session, scoped, limit=12)
    agencies_for_matrix = await _top_agencies_in_scope(session, scoped, limit=10)
    competition = await _competition_mix(session, scoped)
    matrix = await agency_recipient_matrix(session, scoped, limit=100)
    flow = await money_flow(session, scoped, limit=14)

    return {
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
        "money_flow": flow.get("flows") or [],
        "slice_summary": _slice_hint(slice_query),
        **competition,
    }


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


def _slice_hint(slice_query: InsightFacetQuery) -> str:
    parts: list[str] = []
    if slice_query.naics_codes:
        parts.append("NAICS " + ", ".join(slice_query.naics_codes))
    if slice_query.agency:
        parts.append(slice_query.agency)
    if slice_query.recipient:
        parts.append(slice_query.recipient)
    return " · ".join(parts) if parts else "active slice"