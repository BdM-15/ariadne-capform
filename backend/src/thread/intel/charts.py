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
    CAPTURE_CHANNEL_EXPR,
    EXTENT_COMPETED_NORMALIZED_EXPR,
    IDV_FLAG_EXPR,
    PRICING_BUCKET_EXPR,
    PRIME_TABLE,
    FY_EXPR,
    QUARTER_EXPR,
    SET_ASIDE_CHART_EXPR,
    SET_ASIDE_PARENT_BACKED_EXPR,
    SUB_TABLE,
    VEHICLE_EXPR,
    round_numeric,
)

CAPTURE_CHANNEL_LABELS: dict[str, str] = {
    "open_competed": "Open · competed",
    "open_non_competed": "Open · sole/limited",
    "set_aside_competed": "Set-aside · competed",
    "set_aside_non_competed": "Set-aside · sole/NC",
    "vehicle_gated": "IDV / vehicle",
    "other": "Other",
}

CAPTURE_CHANNEL_ORDER: tuple[str, ...] = (
    "open_competed",
    "open_non_competed",
    "set_aside_competed",
    "set_aside_non_competed",
    "vehicle_gated",
    "other",
)

_SUB_ONLY_CHANNELS = frozenset({"set_aside_competed", "set_aside_non_competed"})
_DIRECT_PRIME_CHANNELS = frozenset({"open_competed"})

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
    set_aside = await set_aside_breakdown(session, facet_sql, facet_params, limit=limit)
    extent = await extent_competed_breakdown(session, facet_sql, facet_params, limit=limit)
    recipients = await top_recipients(session, query, limit=limit)
    pricing = await pricing_bucket_breakdown(session, facet_sql, facet_params, limit=limit)
    idv_split = await idv_channel_split(session, facet_sql, facet_params)
    motion_channels = await capture_channel_breakdown(session, facet_sql, facet_params)
    motion_timing = await capture_channel_timing(session, facet_sql, facet_params)
    motion_teaming = await teaming_targets(session, facet_sql, facet_params)
    motion_parent = await set_aside_parent_shadow(session, facet_sql, facet_params)
    motion_expiring = await expiring_capture_channels(session, facet_sql, facet_params)
    motion_paths = await motion_money_paths(session, facet_sql, facet_params)

    result: dict[str, Any] = {
        "status": "ready",
        "mode": "overview",
        "kpis": kpis,
        "spend_trend": spend.get("bars") or [],
        "agency_intensity": intensity,
        "set_aside": set_aside,
        "extent_competed": extent,
        "top_recipients": recipients,
        "pricing_buckets": pricing,
        "idv_split": idv_split,
        "motion": {
            "channels": motion_channels,
            "timing": motion_timing,
            "teaming_targets": motion_teaming,
            "parent_shadow": motion_parent,
            "expiring_channels": motion_expiring,
            "money_paths": motion_paths,
        },
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
            ({FY_EXPR}) AS fiscal_year,
            {round_numeric("SUM(federal_action_obligation) / 1000000.0")} AS millions,
            COUNT(*) AS actions
        FROM {PRIME_TABLE}
        WHERE action_date IS NOT NULL
          {facet_sql}
        GROUP BY ({FY_EXPR})
        ORDER BY ({FY_EXPR}) ASC
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
        "method": "Government FY obligation totals on facet-filtered prime awards.",
        "bars": bars,
        "summary": f"{len(bars)} fiscal years in slice",
    }


def _normalize_channel_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_m = sum(float(r.get("millions") or 0) for r in rows) or 0.0
    by_id = {str(r.get("channel") or "other"): r for r in rows}
    ordered: list[dict[str, Any]] = []
    for channel_id in CAPTURE_CHANNEL_ORDER:
        row = by_id.get(channel_id)
        if not row:
            continue
        millions = float(row.get("millions") or 0)
        if millions <= 0:
            continue
        ordered.append(
            {
                "channel": channel_id,
                "label": CAPTURE_CHANNEL_LABELS.get(channel_id, channel_id),
                "millions": millions,
                "actions": int(row.get("actions") or 0),
                "pct": round(100.0 * millions / total_m, 1) if total_m > 0 else 0.0,
            }
        )
    return ordered


async def capture_channel_breakdown(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({CAPTURE_CHANNEL_EXPR}) AS channel,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY channel
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    raw = [
        {"channel": str(r.channel or "other"), "actions": int(r.actions), "millions": float(r.millions or 0)}
        for r in rows
    ]
    return _normalize_channel_rows(raw)


async def capture_channel_timing(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
) -> dict[str, Any]:
    """Q4 vs rest-of-year channel mix — surfaces year-end offload lane shifts."""
    sql = f"""
        SELECT
            ({CAPTURE_CHANNEL_EXPR}) AS channel,
            CASE WHEN ({QUARTER_EXPR}) = 4 THEN 'q4' ELSE 'rest' END AS period,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE action_date IS NOT NULL
          {facet_sql}
        GROUP BY channel, period
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    lookup: dict[tuple[str, str], float] = {}
    for r in rows:
        lookup[(str(r.channel or "other"), str(r.period))] = float(r.millions or 0)

    rest_total = sum(lookup.get((ch, "rest"), 0.0) for ch in CAPTURE_CHANNEL_ORDER)
    q4_total = sum(lookup.get((ch, "q4"), 0.0) for ch in CAPTURE_CHANNEL_ORDER)

    periods: list[dict[str, Any]] = []
    for channel_id in CAPTURE_CHANNEL_ORDER:
        rest_m = lookup.get((channel_id, "rest"), 0.0)
        q4_m = lookup.get((channel_id, "q4"), 0.0)
        total = rest_m + q4_m
        if total <= 0:
            continue
        periods.append(
            {
                "channel": channel_id,
                "label": CAPTURE_CHANNEL_LABELS.get(channel_id, channel_id),
                "rest_millions": round(rest_m, 2),
                "q4_millions": round(q4_m, 2),
                "rest_pct": round(100.0 * rest_m / total, 1),
                "q4_pct": round(100.0 * q4_m / total, 1),
                "rest_mix_pct": round(100.0 * rest_m / rest_total, 1) if rest_total > 0 else 0.0,
                "q4_mix_pct": round(100.0 * q4_m / q4_total, 1) if q4_total > 0 else 0.0,
            }
        )

    rest_sub = sum(lookup.get((ch, "rest"), 0.0) for ch in _SUB_ONLY_CHANNELS)
    q4_sub = sum(lookup.get((ch, "q4"), 0.0) for ch in _SUB_ONLY_CHANNELS)
    rest_sub_pct = round(100.0 * rest_sub / rest_total, 1) if rest_total > 0 else 0.0
    q4_sub_pct = round(100.0 * q4_sub / q4_total, 1) if q4_total > 0 else 0.0
    delta_sub = round(q4_sub_pct - rest_sub_pct, 1)
    insight = ""
    if abs(delta_sub) >= 5.0:
        direction = "more" if delta_sub > 0 else "less"
        insight = (
            f"Q4 skews {direction} set-aside — {q4_sub_pct:.0f}% of Q4 obligations vs "
            f"{rest_sub_pct:.0f}% Oct–Jun (year-end offload pattern)."
        )
    return {
        "periods": periods,
        "rest_total_millions": round(rest_total, 2),
        "q4_total_millions": round(q4_total, 2),
        "rest_sub_pct": rest_sub_pct,
        "q4_sub_pct": q4_sub_pct,
        "delta_sub_pct": delta_sub,
        "insight": insight,
    }


async def teaming_targets(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    buckets_limit: int = 5,
    primes_per_bucket: int = 3,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({SET_ASIDE_CHART_EXPR}) AS bucket,
            recipient_name AS recipient,
            recipient_uei,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          AND ({SET_ASIDE_CHART_EXPR}) NOT IN ('(Not Applicable)', 'NO SET ASIDE USED')
          {facet_sql}
        GROUP BY bucket, recipient_name, recipient_uei
        ORDER BY bucket ASC, millions DESC NULLS LAST
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    bucket_totals: dict[str, float] = {}
    bucket_primes: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        bucket = str(r.bucket or "")
        millions = float(r.millions or 0)
        bucket_totals[bucket] = bucket_totals.get(bucket, 0.0) + millions
        primes = bucket_primes.setdefault(bucket, [])
        if len(primes) < primes_per_bucket:
            primes.append(
                {
                    "recipient": r.recipient,
                    "recipient_uei": r.recipient_uei,
                    "millions": millions,
                    "actions": int(r.actions),
                }
            )
    top_buckets = sorted(bucket_totals.items(), key=lambda x: x[1], reverse=True)[:buckets_limit]
    return [
        {
            "bucket": bucket,
            "millions": round(total_m, 2),
            "primes": bucket_primes.get(bucket, []),
        }
        for bucket, total_m in top_buckets
        if total_m > 0
    ]


async def set_aside_parent_shadow(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    top_limit: int = 5,
) -> dict[str, Any]:
    sql = f"""
        SELECT
            recipient_name AS recipient,
            recipient_parent_name AS parent,
            ({SET_ASIDE_CHART_EXPR}) AS bucket,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions,
            BOOL_OR({SET_ASIDE_PARENT_BACKED_EXPR}) AS parent_backed,
            BOOL_OR(
                ({SET_ASIDE_CHART_EXPR}) ILIKE '%8(A)%'
                OR ({SET_ASIDE_CHART_EXPR}) ILIKE '%8A%'
            ) AS is_eight_a
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          AND ({SET_ASIDE_CHART_EXPR}) NOT IN ('(Not Applicable)', 'NO SET ASIDE USED')
          {facet_sql}
        GROUP BY recipient_name, recipient_parent_name, bucket
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    set_aside_m = 0.0
    parent_m = 0.0
    independent_m = 0.0
    eight_a_parent_m = 0.0
    parent_rows: list[dict[str, Any]] = []
    for r in rows:
        millions = float(r.millions or 0)
        set_aside_m += millions
        if r.parent_backed:
            parent_m += millions
            if r.is_eight_a:
                eight_a_parent_m += millions
            parent_rows.append(
                {
                    "recipient": r.recipient,
                    "parent": r.parent,
                    "bucket": r.bucket,
                    "millions": millions,
                    "actions": int(r.actions),
                }
            )
        else:
            independent_m += millions
    parent_rows.sort(key=lambda x: x["millions"], reverse=True)
    total = set_aside_m or 1.0
    return {
        "set_aside_millions": round(set_aside_m, 2),
        "parent_backed_millions": round(parent_m, 2),
        "independent_millions": round(independent_m, 2),
        "parent_backed_pct": round(100.0 * parent_m / total, 1),
        "independent_pct": round(100.0 * independent_m / total, 1),
        "eight_a_parent_millions": round(eight_a_parent_m, 2),
        "eight_a_parent_pct": round(100.0 * eight_a_parent_m / total, 1),
        "top_parent_backed": parent_rows[:top_limit],
    }


async def expiring_capture_channels(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    months_ahead: int = 18,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({CAPTURE_CHANNEL_EXPR}) AS channel,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {facet_sql}
        GROUP BY channel
    """
    params = {**facet_params, "months_ahead": str(months_ahead)}
    rows = (await session.execute(text(sql), params)).all()
    raw = [
        {"channel": str(r.channel or "other"), "actions": int(r.actions), "millions": float(r.millions or 0)}
        for r in rows
    ]
    return _normalize_channel_rows(raw)


async def motion_money_paths(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({AGENCY_EXPR}) AS agency,
            ({CAPTURE_CHANNEL_EXPR}) AS channel,
            recipient_name AS recipient,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY agency, channel, recipient_name
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (
        await session.execute(text(sql), {**facet_params, "limit": limit})
    ).all()
    return [
        {
            "agency": r.agency,
            "channel": str(r.channel or "other"),
            "channel_label": CAPTURE_CHANNEL_LABELS.get(str(r.channel or "other"), str(r.channel)),
            "recipient": r.recipient,
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in rows
    ]


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


def _pressure_tier(non_fixed_pct: float) -> str:
    if non_fixed_pct >= 45:
        return "high"
    if non_fixed_pct >= 25:
        return "moderate"
    return "low"


def _agency_shape_gate(non_fixed_pct: float, expiring_non_fixed: int) -> str:
    if non_fixed_pct >= 35 and expiring_non_fixed > 0:
        return "advance"
    if non_fixed_pct >= 25 or expiring_non_fixed > 0:
        return "monitor"
    return "defer"


async def agency_recipient_matrix(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 120,
) -> dict[str, Any]:
    """Agency × recipient pairs for relationship heatmaps (capture-insights port)."""
    facet_sql, facet_params = build_facet_sql(query)
    sql = f"""
        SELECT
            ({AGENCY_EXPR}) AS agency,
            recipient_name AS recipient,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY agency, recipient_name
        HAVING COUNT(*) >= 1
        ORDER BY actions DESC, millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    cells = [
        {
            "agency": r.agency,
            "recipient": r.recipient,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]
    agencies = list(dict.fromkeys(c["agency"] for c in cells))[:12]
    recipients = list(dict.fromkeys(c["recipient"] for c in cells))[:12]
    return {
        "mode": "agency_recipient_matrix",
        "cells": cells,
        "agencies": agencies,
        "recipients": recipients,
        "summary": f"{len(cells)} agency×recipient ties in slice",
    }


async def pricing_bucket_breakdown(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    sql = f"""
        WITH bucketed AS (
            SELECT
                ({PRICING_BUCKET_EXPR}) AS pricing_bucket,
                federal_action_obligation AS oblig
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
        )
        SELECT
            pricing_bucket,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(oblig, 0)) / 1000000.0")} AS millions
        FROM bucketed
        GROUP BY pricing_bucket
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    labels = {
        "firm_fixed": "Firm fixed",
        "cost_reimbursement": "Cost reimbursable",
        "time_materials": "Time & materials",
        "performance_based": "Performance-based",
        "other": "Other / unknown",
    }
    return [
        {
            "bucket": labels.get(r.pricing_bucket, r.pricing_bucket),
            "pricing_bucket": r.pricing_bucket,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def vehicle_breakdown(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            COALESCE(type_of_contract_pricing, 'Unknown Pricing') AS pricing,
            ({VEHICLE_EXPR}) AS vehicle,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY pricing, vehicle
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    return [
        {
            "pricing": r.pricing,
            "vehicle": r.vehicle,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def idv_channel_split(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({IDV_FLAG_EXPR}) AS channel,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY channel
        ORDER BY millions DESC NULLS LAST
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    return [
        {
            "channel": r.channel,
            "actions": int(r.actions),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]


async def ffp_shaping_radar(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    months_ahead: int = 36,
    agency_limit: int = 12,
    target_limit: int = 15,
) -> dict[str, Any]:
    """FFP / flexible-pricing shaping radar — facet-scoped (capture-insights port)."""
    empty: dict[str, Any] = {
        "meta": {
            "policy_note": (
                "Agencies under non-fixed pricing pressure — shaping qualification lens, "
                "not a prediction that specific contracts will convert."
            ),
        },
        "summary": {
            "market_non_fixed_pct": 0,
            "market_firm_fixed_pct": 0,
            "agencies_high_pressure": 0,
            "shape_now_count": 0,
        },
        "agency_pressure": [],
        "shape_targets": [],
    }
    facet_sql, facet_params = build_facet_sql(query)
    market_sql = f"""
        WITH bucketed AS (
            SELECT
                ({PRICING_BUCKET_EXPR}) AS pricing_bucket,
                federal_action_obligation AS oblig
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
        )
        SELECT pricing_bucket, COUNT(*) AS actions,
               {round_numeric("SUM(COALESCE(oblig, 0)) / 1000000.0")} AS millions
        FROM bucketed
        GROUP BY pricing_bucket
        ORDER BY millions DESC NULLS LAST
    """
    market_rows = (await session.execute(text(market_sql), facet_params)).all()
    total_m = sum(float(r.millions or 0) for r in market_rows) or 0
    if not total_m:
        return empty

    bucket_m = {r.pricing_bucket: float(r.millions or 0) for r in market_rows}
    firm_fixed_m = bucket_m.get("firm_fixed", 0)
    non_fixed_m = sum(
        bucket_m.get(k, 0)
        for k in ("cost_reimbursement", "time_materials", "performance_based", "other")
    )

    agency_sql = f"""
        WITH bucketed AS (
            SELECT
                ({AGENCY_EXPR}) AS agency,
                ({PRICING_BUCKET_EXPR}) AS pricing_bucket,
                COALESCE(type_of_contract_pricing, 'Unknown') AS pricing_label,
                federal_action_obligation AS oblig
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
        ),
        agency_totals AS (
            SELECT agency, {round_numeric("SUM(oblig) / 1000000.0")} AS total_millions
            FROM bucketed
            GROUP BY agency
            HAVING SUM(oblig) > 0
        ),
        agency_buckets AS (
            SELECT
                agency,
                pricing_bucket,
                COUNT(*) AS actions,
                {round_numeric("SUM(oblig) / 1000000.0")} AS millions,
                MAX(pricing_label) AS sample_pricing
            FROM bucketed
            GROUP BY agency, pricing_bucket
        )
        SELECT
            bk.agency,
            tot.total_millions,
            bk.pricing_bucket,
            bk.millions,
            bk.actions,
            bk.sample_pricing
        FROM agency_buckets bk
        JOIN agency_totals tot ON tot.agency = bk.agency
        ORDER BY tot.total_millions DESC NULLS LAST, bk.millions DESC NULLS LAST
    """
    agency_rows = (await session.execute(text(agency_sql), facet_params)).all()

    expiring_sql = f"""
        SELECT
            contract_award_unique_key,
            recipient_name,
            ({AGENCY_EXPR}) AS agency,
            COALESCE(type_of_contract_pricing, 'Unknown') AS pricing,
            ({PRICING_BUCKET_EXPR}) AS pricing_bucket,
            {round_numeric("COALESCE(federal_action_obligation, 0) / 1000000.0")} AS obligation_millions,
            period_of_performance_current_end_date::text AS end_date
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {facet_sql}
        ORDER BY period_of_performance_current_end_date ASC
        LIMIT :exp_limit
    """
    expiring_rows = (
        await session.execute(
            text(expiring_sql),
            {**facet_params, "months_ahead": str(months_ahead), "exp_limit": max(target_limit * 4, 40)},
        )
    ).all()

    agency_map: dict[str, dict[str, Any]] = {}
    for r in agency_rows:
        agency = r.agency
        if agency not in agency_map:
            agency_map[agency] = {"agency": agency, "total_millions": float(r.total_millions or 0), "buckets": {}}
        agency_map[agency]["buckets"][r.pricing_bucket] = {
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
            "sample_pricing": r.sample_pricing,
        }

    agency_pressure: list[dict[str, Any]] = []
    for agency, entry in sorted(
        agency_map.items(),
        key=lambda x: x[1]["total_millions"],
        reverse=True,
    )[:agency_limit]:
        total = entry["total_millions"] or 1.0
        buckets = entry["buckets"]
        firm_m = buckets.get("firm_fixed", {}).get("millions", 0)
        cost_rm = buckets.get("cost_reimbursement", {}).get("millions", 0)
        tm_rm = buckets.get("time_materials", {}).get("millions", 0)
        perf_rm = buckets.get("performance_based", {}).get("millions", 0)
        other_rm = buckets.get("other", {}).get("millions", 0)
        non_fixed_m_ag = cost_rm + tm_rm + perf_rm + other_rm
        non_fixed_pct = round((non_fixed_m_ag / total) * 100, 1)

        dominant_non_fixed = None
        dominant_m = 0.0
        for bname in ("cost_reimbursement", "time_materials", "performance_based", "other"):
            bm = buckets.get(bname, {}).get("millions", 0)
            if bm > dominant_m:
                dominant_m = bm
                dominant_non_fixed = buckets.get(bname, {}).get("sample_pricing")

        expiring_non_fixed = sum(
            1 for er in expiring_rows if er.agency == agency and er.pricing_bucket != "firm_fixed"
        )

        agency_pressure.append({
            "agency": agency,
            "total_millions": round(total, 2),
            "firm_fixed_pct": round((firm_m / total) * 100, 1),
            "non_fixed_pct": non_fixed_pct,
            "dominant_non_fixed_pricing": dominant_non_fixed,
            "pressure_tier": _pressure_tier(non_fixed_pct),
            "shape_gate": _agency_shape_gate(non_fixed_pct, expiring_non_fixed),
            "expiring_non_fixed_count": expiring_non_fixed,
        })

    agency_pressure.sort(key=lambda a: (a["non_fixed_pct"], a["total_millions"]), reverse=True)
    agency_pct_lookup = {a["agency"]: a["non_fixed_pct"] for a in agency_pressure}
    agency_tier_lookup = {a["agency"]: a["pressure_tier"] for a in agency_pressure}

    shape_targets: list[dict[str, Any]] = []
    for er in expiring_rows:
        if er.pricing_bucket == "firm_fixed":
            continue
        agency_non_fixed = agency_pct_lookup.get(er.agency, 0)
        pressure_tier = agency_tier_lookup.get(er.agency, "low")
        oblig_m = float(er.obligation_millions or 0)

        if agency_non_fixed >= 35 and oblig_m >= 0.5:
            shape_gate = "shape_now"
            shape_reason = (
                f"Non-fixed ({er.pricing}) expiring at agency with {agency_non_fixed}% "
                "flexible pricing — early shaping window"
            )
        elif agency_non_fixed >= 25 or pressure_tier in ("high", "moderate"):
            shape_gate = "monitor"
            shape_reason = "Flexible pricing recompete — watch for shift toward fixed-price terms"
        else:
            shape_gate = "watch"
            shape_reason = "Non-fixed expiring award — lower agency pressure in slice"

        shape_targets.append({
            "award_key": er.contract_award_unique_key,
            "recipient": er.recipient_name,
            "agency": er.agency,
            "end_date": er.end_date,
            "pricing": er.pricing,
            "pricing_bucket": er.pricing_bucket,
            "obligation_millions": oblig_m,
            "agency_non_fixed_pct": agency_non_fixed,
            "pressure_tier": pressure_tier,
            "shape_gate": shape_gate,
            "shape_reason": shape_reason,
        })

    gate_order = {"shape_now": 0, "monitor": 1, "watch": 2}
    shape_targets.sort(
        key=lambda t: (
            gate_order.get(t["shape_gate"], 9),
            -(t["obligation_millions"] or 0),
            -(t["agency_non_fixed_pct"] or 0),
        )
    )
    shape_targets = shape_targets[:target_limit]

    return {
        "meta": empty["meta"],
        "summary": {
            "market_non_fixed_pct": round((non_fixed_m / total_m) * 100, 1),
            "market_firm_fixed_pct": round((firm_fixed_m / total_m) * 100, 1),
            "agencies_high_pressure": sum(1 for a in agency_pressure if a["pressure_tier"] == "high"),
            "shape_now_count": sum(1 for t in shape_targets if t["shape_gate"] == "shape_now"),
        },
        "agency_pressure": agency_pressure,
        "shape_targets": shape_targets,
    }


async def adjacent_competitors(
    session: AsyncSession,
    query: InsightFacetQuery,
    target_recipient: str,
    *,
    limit: int = 10,
    exclude_top_n: int = 10,
    max_share_pct: float = 8.0,
) -> list[dict[str, Any]]:
    """Co-occurrence at shared agencies — niche primes, not market leaders."""
    target = (target_recipient or "").strip()
    if not target:
        return []

    facet_sql, facet_params = build_facet_sql(query)
    market_sql = f"""
        SELECT recipient_name,
               {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY recipient_name
        ORDER BY millions DESC NULLS LAST
    """
    market_rows = (await session.execute(text(market_sql), facet_params)).all()
    total_market = sum(float(r.millions or 0) for r in market_rows) or 1.0
    top_names = {r.recipient_name for r in market_rows[:exclude_top_n]}
    top_names.add(target)

    overlap_sql = f"""
        WITH target_agencies AS (
            SELECT DISTINCT ({AGENCY_EXPR}) AS agency
            FROM {PRIME_TABLE}
            WHERE recipient_name = :target_recipient
              {facet_sql}
        ),
        recipient_totals AS (
            SELECT recipient_name,
                   {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS market_millions
            FROM {PRIME_TABLE}
            WHERE recipient_name IS NOT NULL
              {facet_sql}
            GROUP BY recipient_name
        ),
        overlap AS (
            SELECT
                p.recipient_name,
                ({AGENCY_EXPR}) AS agency,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(p.federal_action_obligation, 0)) / 1000000.0")} AS millions
            FROM {PRIME_TABLE} p
            WHERE p.recipient_name != :target_recipient
              {facet_sql}
              AND ({AGENCY_EXPR}) IN (SELECT agency FROM target_agencies)
            GROUP BY p.recipient_name, ({AGENCY_EXPR})
        )
        SELECT
            o.recipient_name,
            COUNT(DISTINCT o.agency) AS shared_agencies,
            SUM(o.actions) AS total_actions,
            {round_numeric("SUM(o.millions)")} AS shared_millions,
            MAX(o.agency) AS sample_agency,
            MAX(rt.market_millions) AS market_millions
        FROM overlap o
        LEFT JOIN recipient_totals rt ON rt.recipient_name = o.recipient_name
        GROUP BY o.recipient_name
        ORDER BY shared_agencies DESC, shared_millions ASC
        LIMIT :scan_limit
    """
    rows = (
        await session.execute(
            text(overlap_sql),
            {**facet_params, "target_recipient": target, "scan_limit": max(limit * 3, 30)},
        )
    ).all()

    candidates: list[dict[str, Any]] = []
    for r in rows:
        name = r.recipient_name or "Unknown"
        if name in top_names:
            continue
        market_m = float(r.market_millions or 0)
        share_pct = round((market_m / total_market) * 100, 2)
        if share_pct > max_share_pct:
            continue
        shared_ag = int(r.shared_agencies or 0)
        shared_m = float(r.shared_millions or 0)
        overlap_ratio = round(shared_m / market_m, 3) if market_m else 0.0
        if share_pct <= 4.0 and shared_ag >= 2:
            fit = "promising"
            fit_reason = "Adjacent vendor at shared buyers — validate gap before outreach"
        elif shared_ag >= 1 and shared_m <= 12:
            fit = "research"
            fit_reason = "Thin overlap — subs or web research may surface better fits"
        else:
            fit = "research"
            fit_reason = "Weak bulk signal — vet capability match"
        candidates.append({
            "recipient": name,
            "shared_agencies": shared_ag,
            "total_actions": int(r.total_actions or 0),
            "shared_millions": shared_m,
            "market_millions": market_m,
            "market_share_pct": share_pct,
            "overlap_ratio": overlap_ratio,
            "sample_agency": r.sample_agency,
            "fit": fit,
            "fit_reason": fit_reason,
        })

    fit_order = {"promising": 0, "research": 1}
    candidates.sort(
        key=lambda c: (
            fit_order.get(c["fit"], 9),
            -(c["shared_agencies"] or 0),
            c["market_share_pct"] or 999,
        )
    )
    return candidates[:limit]


async def run_competition_lens(
    session: AsyncSession,
    query: InsightFacetQuery,
) -> dict[str, Any]:
    """Slice-wide competition bundle — set-aside, extent, pricing, vehicles, FFP shaping."""
    if not query.has_filters():
        return {"error": "At least one search facet required.", "status": "no_query"}
    if not await table_exists(session, PRIME_TABLE):
        return {"error": "Prime awards table missing.", "status": "loading"}

    facet_sql, facet_params = build_facet_sql(query)
    set_aside = await set_aside_breakdown(session, facet_sql, facet_params)
    extent = await extent_competed_breakdown(session, facet_sql, facet_params)
    pricing = await pricing_bucket_breakdown(session, facet_sql, facet_params)
    vehicles = await vehicle_breakdown(session, facet_sql, facet_params)
    idv_split = await idv_channel_split(session, facet_sql, facet_params)
    ffp = await ffp_shaping_radar(session, query)

    return {
        "status": "ready",
        "mode": "competition_lens",
        "set_aside": set_aside,
        "extent_competed": extent,
        "pricing_buckets": pricing,
        "vehicle_breakdown": vehicles,
        "idv_split": idv_split,
        "ffp_shaping": ffp,
    }


async def run_trace_lens(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = 16,
) -> dict[str, Any]:
    """Inline DR trace — Sankey + expose graph + heat map on active slice."""
    if not query.has_filters():
        return {"error": "At least one search facet required.", "status": "no_query"}
    if not await table_exists(session, PRIME_TABLE):
        return {"error": "Prime awards table missing.", "status": "loading"}

    from thread.intel.graph_trace import build_browse_funnel, build_relations_graph

    money = await money_flow(session, query, limit=limit)
    team = await teaming(session, query, limit=limit)
    matrix = await agency_recipient_matrix(session, query, limit=80)
    relations = await build_relations_graph(
        session,
        query,
        seed_recipient=query.recipient or "",
        seed_agency=query.agency or "",
        max_hops=3,
    )
    browse = build_browse_funnel(relations)

    return {
        "status": "ready",
        "mode": "trace_lens",
        "money_flow": money,
        "teaming": team,
        "agency_recipient_matrix": matrix,
        "relations_graph": relations,
        "expose_graph": relations,
        "browse_funnel": browse,
    }


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