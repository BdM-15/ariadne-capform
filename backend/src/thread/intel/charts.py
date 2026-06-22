"""Shared intel chart queries — Insights Overview + Clew trace modes (DR follow-the-money SQL)."""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.facet_query import InsightFacetQuery, build_facet_sql
from thread.intel.pg_queries import table_exists
from thread.intel.sql_expressions import (
    AGENCY_EXPR,
    AGENCY_NORMALIZED_EXPR,
    EXTENT_COMPETED_NORMALIZED_EXPR,
    PRIME_TABLE,
    SET_ASIDE_CHART_EXPR,
    SUB_TABLE,
    round_numeric,
)

ANALYSIS_MODES = frozenset({"spend_trend", "money_flow", "teaming", "recipient_landscape"})

_OVERVIEW_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_OVERVIEW_TTL_SECONDS = 120.0


def clear_overview_cache() -> None:
    """Test helper — drop in-memory overview cache."""
    _OVERVIEW_CACHE.clear()


def _overview_cache_key(query: InsightFacetQuery) -> str:
    payload = {
        "naics": list(query.naics_codes),
        "agency": query.agency,
        "sub_agency": query.sub_agency,
        "recipient": query.recipient,
        "psc": list(query.psc_codes),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _subaward_facet_sql(query: InsightFacetQuery) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if query.recipient:
        clauses.append(
            "(prime_awardee_name ILIKE :recipient OR subawardee_name ILIKE :recipient)"
        )
        params["recipient"] = f"%{query.recipient}%"

    if query.agency:
        clauses.append(
            "(prime_award_awarding_agency_name ILIKE :agency "
            "OR prime_award_funding_agency_name ILIKE :agency)"
        )
        params["agency"] = f"%{query.agency}%"

    return (" AND ".join(clauses) if clauses else ""), params


async def run_facet_analysis(
    session: AsyncSession,
    query: InsightFacetQuery,
    mode: str,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    if mode not in ANALYSIS_MODES:
        return {"mode": mode, "error": f"Unknown mode — choose from {sorted(ANALYSIS_MODES)}"}
    if not query.has_filters():
        return {"mode": mode, "error": "At least one search facet required."}
    if not await table_exists(session, PRIME_TABLE):
        return {"mode": mode, "error": "Prime awards table missing — run intel migration."}

    if mode == "spend_trend":
        return await spend_trend(session, query, limit=limit)
    if mode == "money_flow":
        return await money_flow(session, query, limit=limit)
    if mode == "teaming":
        return await teaming(session, query, limit=limit)
    return await recipient_landscape(session, query, limit=limit)


async def run_slice_overview(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
    use_cache: bool = True,
) -> dict[str, Any]:
    if not query.has_filters():
        return {"error": "At least one search facet required.", "status": "no_query"}
    if not await table_exists(session, PRIME_TABLE):
        return {"error": "Prime awards table missing — run intel migration.", "status": "loading"}

    cache_key = _overview_cache_key(query)
    if use_cache:
        cached = _OVERVIEW_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _OVERVIEW_TTL_SECONDS:
            return dict(cached[1])

    facet_sql, facet_params = build_facet_sql(query)
    kpis = await _slice_kpis(session, facet_sql, facet_params)
    spend = await spend_trend(session, query, limit=limit)
    intensity = await agency_intensity(session, query, limit=limit)
    sub_flow = await agency_sub_flow(session, query, limit=limit)
    set_aside = await set_aside_breakdown(session, facet_sql, facet_params, limit=limit)
    extent = await extent_competed_breakdown(session, facet_sql, facet_params, limit=limit)
    recipients = await top_recipients(session, query, limit=limit)

    result: dict[str, Any] = {
        "status": "ready",
        "mode": "overview",
        "kpis": kpis,
        "spend_trend": spend.get("bars") or [],
        "agency_intensity": intensity,
        "agency_sub_flow": sub_flow.get("rows") or [],
        "agency_sub_flow_group": sub_flow.get("group"),
        "set_aside": set_aside,
        "extent_competed": extent,
        "top_recipients": recipients,
        "summary": "Slice overview",
    }
    _OVERVIEW_CACHE[cache_key] = (time.monotonic(), dict(result))
    return result


async def _slice_kpis(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
) -> dict[str, Any]:
    sql = f"""
        SELECT
            COUNT(*) AS award_count,
            COUNT(DISTINCT recipient_name) AS recipient_count,
            COUNT(DISTINCT ({AGENCY_NORMALIZED_EXPR})) AS agency_count,
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


async def spend_trend(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            EXTRACT(YEAR FROM action_date)::int AS fiscal_year,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS millions,
            COUNT(*) AS actions
        FROM {PRIME_TABLE}
        WHERE action_date IS NOT NULL
          {facet_sql}
        GROUP BY fiscal_year
        ORDER BY fiscal_year ASC
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    bars = [
        {
            "year": int(r.fiscal_year),
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in rows
    ]
    peak = max((b["millions"] for b in bars), default=0.0) or 1.0
    for b in bars:
        b["pct"] = round(100.0 * b["millions"] / peak, 1)
    return {
        "mode": "spend_trend",
        "method": "Yearly obligation totals on facet-filtered prime awards.",
        "bars": bars,
        "summary": f"{len(bars)} fiscal years in slice",
    }


async def money_flow(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            recipient_name AS recipient,
            {AGENCY_EXPR} AS agency,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS millions,
            COUNT(*) AS actions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY recipient_name, {AGENCY_EXPR}
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    flows = [
        {
            "recipient": r.recipient,
            "agency": r.agency,
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in rows
    ]
    peak = max((f["millions"] for f in flows), default=0.0) or 1.0
    for f in flows:
        f["pct"] = round(100.0 * f["millions"] / peak, 1)
    return {
        "mode": "money_flow",
        "method": "Recipient → agency obligation paths.",
        "flows": flows,
        "summary": f"Top {len(flows)} money paths in facet slice",
    }


async def recipient_landscape(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            recipient_name AS recipient,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS millions,
            COUNT(*) AS actions,
            COUNT(DISTINCT {AGENCY_EXPR}) AS agency_count
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY recipient_name
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    recipients = [
        {
            "recipient": r.recipient,
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
            "agency_count": int(r.agency_count or 0),
        }
        for r in rows
    ]
    peak = max((x["millions"] for x in recipients), default=0.0) or 1.0
    for x in recipients:
        x["pct"] = round(100.0 * x["millions"] / peak, 1)
    return {
        "mode": "recipient_landscape",
        "method": "Recipient concentration in facet slice.",
        "recipients": recipients,
        "summary": f"Top {len(recipients)} recipients by obligated spend",
    }


async def teaming(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    if not await table_exists(session, SUB_TABLE):
        return {
            "mode": "teaming",
            "error": "FFATA subaward bulk not in PostgreSQL yet.",
            "method": "Prime → sub teaming edges (FFATA bulk).",
        }
    sub_count = int(
        (await session.execute(text(f"SELECT COUNT(*) FROM {SUB_TABLE}"))).scalar() or 0
    )
    if sub_count == 0:
        return {
            "mode": "teaming",
            "error": "Subaward table empty — migration still loading FFATA rows.",
            "method": "Prime → sub teaming edges (FFATA bulk).",
        }

    facet_sql, facet_params = _subaward_facet_sql(query)
    where_extra = f"AND {facet_sql}" if facet_sql else ""
    sql = f"""
        SELECT
            prime_awardee_name AS prime,
            subawardee_name AS sub,
            {round_numeric("SUM(COALESCE(NULLIF(subaward_amount, '')::DOUBLE PRECISION, 0)) / 1000000.0")} AS millions,
            COUNT(*) AS links
        FROM {SUB_TABLE}
        WHERE prime_awardee_name IS NOT NULL
          AND subawardee_name IS NOT NULL
          {where_extra}
        GROUP BY prime_awardee_name, subawardee_name
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    edges = [
        {
            "prime": r.prime,
            "sub": r.sub,
            "millions": float(r.millions or 0),
            "links": int(r.links),
        }
        for r in rows
    ]
    return {
        "mode": "teaming",
        "method": "Prime → subcontractor edges on migrated FFATA subawards.",
        "edges": edges,
        "summary": f"{len(edges)} prime→sub edges in facet slice",
    }


async def agency_intensity(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            ({AGENCY_NORMALIZED_EXPR}) AS agency,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE ({AGENCY_NORMALIZED_EXPR}) != ''
          {facet_sql}
        GROUP BY agency
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    points = [
        {
            "agency": r.agency,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]
    action_vals = [p["actions"] for p in points]
    money_vals = [p["millions"] for p in points]
    median_actions = statistics.median(action_vals) if action_vals else 0
    median_millions = statistics.median(money_vals) if money_vals else 0
    hot: list[str] = []
    for p in points:
        p["hot"] = p["actions"] >= median_actions and p["millions"] >= median_millions
        if p["hot"]:
            hot.append(p["agency"])
    return {
        "points": points,
        "median_actions": median_actions,
        "median_millions": median_millions,
        "hot_agencies": hot,
    }


async def agency_sub_flow(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    group_col = (
        "awarding_sub_agency_name"
        if query.agency and not query.sub_agency
        else "awarding_office_name"
        if query.sub_agency
        else "awarding_sub_agency_name"
    )
    label = (
        "sub_agency"
        if group_col == "awarding_sub_agency_name"
        else "office"
    )
    sql = f"""
        SELECT
            COALESCE(NULLIF(TRIM({group_col}), ''), '(Unspecified)') AS label,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY label
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    flow_rows = [
        {
            "label": r.label,
            "kind": label,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]
    return {"rows": flow_rows, "group": label}


async def set_aside_breakdown(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({SET_ASIDE_CHART_EXPR}) AS bucket,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY bucket
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "bucket": r.bucket,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def extent_competed_breakdown(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            NULLIF(({EXTENT_COMPETED_NORMALIZED_EXPR}), '') AS extent,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY extent
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "extent": r.extent or "(Unknown)",
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def top_recipients(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
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
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "recipient": r.recipient,
            "recipient_uei": (r.recipient_uei or "").strip() or None,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]