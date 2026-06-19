"""PostgreSQL intel queries — ported from capture-insights backend/app/queries.py."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.facet_query import InsightFacetQuery, build_facet_sql
from thread.intel.sql_expressions import (
    AGENCY_EXPR,
    MONTHS_TO_END_EXPR,
    PRICING_BUCKET_EXPR,
    PRIME_TABLE,
    STATE_EXPR,
    naics_filter,
    round_numeric,
)


async def table_exists(session: AsyncSession, table_name: str) -> bool:
    row = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = :name"
            ")"
        ),
        {"name": table_name},
    )
    return bool(row.scalar())


async def get_intel_stats(session: AsyncSession) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "prime_awards_ready": False,
        "prime_award_count": 0,
        "subaward_count": 0,
        "naics_cache_count": 0,
    }
    if not await table_exists(session, PRIME_TABLE):
        return stats
    stats["prime_awards_ready"] = True
    stats["prime_award_count"] = int(
        (await session.execute(text(f"SELECT COUNT(*) FROM {PRIME_TABLE}"))).scalar() or 0
    )
    if await table_exists(session, "intel_usaspending_subawards"):
        stats["subaward_count"] = int(
            (
                await session.execute(text("SELECT COUNT(*) FROM intel_usaspending_subawards"))
            ).scalar()
            or 0
        )
    if await table_exists(session, "intel_naics_summary_cache"):
        stats["naics_cache_count"] = int(
            (
                await session.execute(text("SELECT COUNT(*) FROM intel_naics_summary_cache"))
            ).scalar()
            or 0
        )
    return stats


async def get_market_summary(
    session: AsyncSession,
    naics_codes: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    nf_sql, nf_params = naics_filter(naics_codes)
    params: dict[str, Any] = dict(nf_params)
    date_sql = ""
    if start_date:
        date_sql += " AND action_date >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_sql += " AND action_date <= :end_date"
        params["end_date"] = end_date

    sql = f"""
        SELECT
            COUNT(*) AS total_actions,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS total_millions,
            {round_numeric("AVG(federal_action_obligation) / 1000.0", 0)} AS avg_thousands,
            MIN(action_date) AS earliest_date,
            MAX(action_date) AS latest_date
        FROM {PRIME_TABLE}
        WHERE 1=1
        {nf_sql}
        {date_sql}
    """
    row = (await session.execute(text(sql), params)).one()
    if not row.total_actions:
        return {
            "naics_codes": naics_codes,
            "total_actions": 0,
            "total_millions": 0,
            "avg_thousands": 0,
            "message": "No data found for these filters.",
        }
    return {
        "naics_codes": naics_codes,
        "total_actions": int(row.total_actions),
        "total_millions": float(row.total_millions or 0),
        "avg_thousands": float(row.avg_thousands or 0),
        "earliest_date": str(row.earliest_date) if row.earliest_date else None,
        "latest_date": str(row.latest_date) if row.latest_date else None,
        "note": "Numbers from PostgreSQL intel tables (migrated USAspending bulk).",
    }


async def get_top_agencies(
    session: AsyncSession,
    naics_codes: list[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    nf_sql, nf_params = naics_filter(naics_codes)
    sql = f"""
        SELECT
            parent_award_agency_name AS agency,
            COUNT(*) AS actions,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS total_millions
        FROM {PRIME_TABLE}
        WHERE 1=1
        {nf_sql}
        GROUP BY parent_award_agency_name
        ORDER BY total_millions DESC NULLS LAST
        LIMIT :limit
    """
    params = {**nf_params, "limit": limit}
    rows = (await session.execute(text(sql), params)).all()
    return [
        {
            "agency": r.agency,
            "actions": int(r.actions),
            "total_millions": float(r.total_millions or 0),
        }
        for r in rows
    ]


async def get_expiring_contracts(
    session: AsyncSession,
    naics_codes: list[str],
    months_ahead: int = 24,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Legacy NAICS-list entry — prefer get_expiring_contracts_for_query with facet query."""
    if not naics_codes:
        return []
    return await get_expiring_contracts_for_query(
        session,
        InsightFacetQuery(id="legacy", name="legacy", naics_codes=tuple(naics_codes)),
        months_ahead=months_ahead,
        limit=limit,
    )


async def count_expiring_for_query(
    session: AsyncSession,
    query: InsightFacetQuery,
    months_ahead: int = 18,
) -> int:
    if not query.has_filters():
        return 0
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT COUNT(*) AS n
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {facet_sql}
    """
    params = {**facet_params, "months_ahead": str(months_ahead)}
    row = (await session.execute(text(sql), params)).first()
    return int(row.n if row else 0)


async def get_award_profile(
    session: AsyncSession,
    award_key: str,
) -> dict[str, Any] | None:
    """Single award row for packet route-driven fill."""
    key = (award_key or "").strip()
    if not key or not await table_exists(session, PRIME_TABLE):
        return None
    sql = f"""
        SELECT
            contract_award_unique_key AS award_key,
            recipient_name AS recipient,
            federal_action_obligation AS obligation,
            period_of_performance_current_end_date AS end_date,
            {AGENCY_EXPR} AS agency,
            COALESCE(NULLIF(type_of_contract_pricing, ''), 'Unknown') AS pricing,
            naics_code
        FROM {PRIME_TABLE}
        WHERE contract_award_unique_key = :award_key
        LIMIT 1
    """
    row = (await session.execute(text(sql), {"award_key": key})).first()
    if row is None:
        return None
    return {
        "award_key": row.award_key,
        "recipient": row.recipient,
        "obligation": float(row.obligation) if row.obligation is not None else None,
        "end_date": str(row.end_date) if row.end_date else None,
        "agency": row.agency,
        "pricing": row.pricing,
        "naics_code": row.naics_code,
    }


async def get_awards_by_keys(
    session: AsyncSession,
    award_keys: list[str],
) -> dict[str, dict[str, Any]]:
    """Batch lookup for watchlist enrichment."""
    keys = [k.strip() for k in award_keys if k and str(k).strip()]
    if not keys or not await table_exists(session, PRIME_TABLE):
        return {}
    placeholders = ", ".join(f":key_{i}" for i in range(len(keys)))
    params = {f"key_{i}": k for i, k in enumerate(keys)}
    sql = f"""
        SELECT
            contract_award_unique_key AS award_key,
            recipient_name AS recipient,
            federal_action_obligation AS obligation,
            period_of_performance_current_end_date AS end_date,
            {AGENCY_EXPR} AS agency,
            {MONTHS_TO_END_EXPR} AS months_to_end,
            naics_code
        FROM {PRIME_TABLE}
        WHERE contract_award_unique_key IN ({placeholders})
    """
    rows = (await session.execute(text(sql), params)).all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[r.award_key] = {
            "award_key": r.award_key,
            "recipient": r.recipient,
            "obligation": float(r.obligation) if r.obligation is not None else None,
            "end_date": str(r.end_date) if r.end_date else None,
            "agency": r.agency,
            "months_to_end": int(r.months_to_end or 0),
            "naics_code": r.naics_code,
        }
    return out


async def get_expiring_contracts_for_query(
    session: AsyncSession,
    query: InsightFacetQuery,
    months_ahead: int = 24,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not query.has_filters():
        return []
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            contract_award_unique_key AS award_key,
            recipient_name AS recipient,
            federal_action_obligation AS obligation,
            period_of_performance_current_end_date AS end_date,
            {AGENCY_EXPR} AS agency,
            {STATE_EXPR} AS pop_state,
            COALESCE(NULLIF(type_of_contract_pricing, ''), 'Unknown') AS pricing,
            {PRICING_BUCKET_EXPR} AS pricing_bucket,
            {MONTHS_TO_END_EXPR} AS months_to_end,
            naics_code
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {facet_sql}
        ORDER BY period_of_performance_current_end_date ASC
        LIMIT :limit
    """
    params = {**facet_params, "months_ahead": str(months_ahead), "limit": limit}
    rows = (await session.execute(text(sql), params)).all()
    return [
        {
            "award_key": r.award_key,
            "recipient": r.recipient,
            "obligation": float(r.obligation) if r.obligation is not None else None,
            "end_date": str(r.end_date) if r.end_date else None,
            "agency": r.agency,
            "pop_state": r.pop_state,
            "pricing": r.pricing,
            "pricing_bucket": r.pricing_bucket,
            "months_to_end": int(r.months_to_end or 0),
            "naics_code": r.naics_code,
        }
        for r in rows
    ]


async def get_quick_opportunity_snapshot(
    session: AsyncSession,
    naics: str = "561210",
) -> dict[str, Any]:
    codes = [naics]
    return {
        "summary": await get_market_summary(session, codes),
        "top_agencies": await get_top_agencies(session, codes, limit=5),
        "expiring_soon": await get_expiring_contracts(session, codes, months_ahead=18, limit=5),
    }