"""Clew analytics — trace money paths over migrated USAspending PostgreSQL intel.

Utility layer separate from raw USAspending explore (facet queries + pg_queries).
Modes: spend_trend, money_flow, teaming, recipient_landscape.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.facet_query import InsightFacetQuery, build_facet_sql, query_from_dict
from thread.intel.pg_queries import table_exists
from thread.intel.sql_expressions import AGENCY_EXPR, PRIME_TABLE, round_numeric

SUB_TABLE = "intel_usaspending_subawards"

ANALYSIS_MODES = frozenset({"spend_trend", "money_flow", "teaming", "recipient_landscape"})


def facet_from_payload(body: dict[str, Any]) -> InsightFacetQuery | None:
    facet = body.get("facet")
    if isinstance(facet, dict):
        return query_from_dict({**facet, "id": facet.get("id") or "analyze", "name": facet.get("name") or "Analysis"})
    return query_from_dict(
        {
            "id": "analyze",
            "name": "Analysis",
            "agency": body.get("agency"),
            "sub_agency": body.get("sub_agency"),
            "recipient": body.get("recipient"),
            "naics_codes": body.get("naics_codes") or body.get("naics"),
            "psc_codes": body.get("psc_codes"),
        }
    )


def _subaward_facet_sql(query: InsightFacetQuery) -> tuple[str, dict[str, Any]]:
    """Facet filters for subaward table (column names differ from prime)."""
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
        return await _spend_trend(session, query, limit=limit)
    if mode == "money_flow":
        return await _money_flow(session, query, limit=limit)
    if mode == "teaming":
        return await _teaming(session, query, limit=limit)
    return await _recipient_landscape(session, query, limit=limit)


async def _spend_trend(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
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
        "method": "Yearly obligation totals on facet-filtered prime awards (USAspending bulk / capture-insights pattern).",
        "bars": bars,
        "summary": f"{len(bars)} fiscal years in slice",
    }


async def _money_flow(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
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
        "method": "Recipient → agency obligation paths — follow-the-money over who wins and who buys.",
        "flows": flows,
        "summary": f"Top {len(flows)} money paths in facet slice",
    }


async def _recipient_landscape(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
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
        "method": "Recipient concentration — who captures spend in this facet slice.",
        "recipients": recipients,
        "summary": f"Top {len(recipients)} recipients by obligated spend",
    }


async def _teaming(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int,
) -> dict[str, Any]:
    if not await table_exists(session, SUB_TABLE):
        return {
            "mode": "teaming",
            "error": "FFATA subaward bulk not in PostgreSQL yet.",
            "error_hint": (
                "Teaming Sankey needs intel_usaspending_subawards. "
                "Re-run intel migration without --skip-subawards "
                "(scripts/run-intel-migration.ps1). "
                "Until then: use Money flow mode, or Teaming + Live MCP for SAM/USAspending live rows."
            ),
            "method": "Prime → sub teaming edges (FFATA bulk).",
        }
    sub_count = int(
        (await session.execute(text(f"SELECT COUNT(*) FROM {SUB_TABLE}"))).scalar() or 0
    )
    if sub_count == 0:
        return {
            "mode": "teaming",
            "error": "Subaward table empty — migration still loading FFATA rows.",
            "error_hint": (
                "Resume or wait for intel migration (do not use --skip-subawards). "
                "Live MCP supplement can still return SAM subawards when recipient is set."
            ),
            "method": "Prime → sub teaming edges (FFATA bulk).",
        }

    facet_sql, facet_params = _subaward_facet_sql(query)
    where_extra = f"AND {facet_sql}" if facet_sql else ""
    sql = f"""
        SELECT
            prime_awardee_name AS prime,
            subawardee_name AS sub,
            {round_numeric("SUM(COALESCE(subaward_amount, 0)) / 1000000.0")} AS millions,
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
    peak = max((e["millions"] for e in edges), default=0.0) or 1.0
    for e in edges:
        e["pct"] = round(100.0 * e["millions"] / peak, 1)
    return {
        "mode": "teaming",
        "method": "Teaming structure beyond prime-only: prime contractor → subcontractor edges on migrated FFATA subawards.",
        "edges": edges,
        "summary": f"{len(edges)} prime→sub edges in facet slice · {sub_count:,} subaward rows in PG",
        "live_supplement": "SAM MCP subaward search adds live notices — Tools → MCP when bulk is stale.",
    }