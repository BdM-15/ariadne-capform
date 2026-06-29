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
from thread.intel.pg_parallel import gather_pg, run_pg
from thread.intel.pg_queries import table_exists
from thread.ui.formatters import format_count, format_money_from_millions
from thread.intel.sql_expressions import (
    AGENCY_EXPR,
    AGENCY_NORMALIZED_EXPR,
    BASE_AWARD_WHERE,
    CAPTURE_CHANNEL_EXPR,
    EXPIRING_CONTRACT_VALUE_EXPR,
    EXPIRING_MONTHS_AHEAD,
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


INTENSITY_OFFICE_LIMIT = 64
OVERVIEW_SCHEMA_VERSION = 5  # ponytail: bump when overview/intensity shape changes — invalidates slice cache


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
    # ponytail: independent chart queries — fan out on separate PG sessions (pool semaphore)
    (
        kpis,
        spend,
        intensity,
        set_aside,
        extent,
        recipients,
        pricing,
        idv_split,
        motion_channels,
        motion_timing,
        motion_teaming,
        motion_parent,
        motion_expiring,
        motion_paths,
        expiring_tl,
        vehicles,
        ffp,
    ) = await gather_pg(
        lambda s: _slice_kpis(s, facet_sql, facet_params),
        lambda s: spend_trend(s, query, limit=limit),
        lambda s: agency_intensity(s, query, limit=INTENSITY_OFFICE_LIMIT),
        lambda s: set_aside_breakdown(s, facet_sql, facet_params, limit=limit),
        lambda s: extent_competed_breakdown(s, facet_sql, facet_params, limit=limit),
        lambda s: top_recipients(s, query, limit=limit),
        lambda s: pricing_bucket_breakdown(s, facet_sql, facet_params, limit=limit),
        lambda s: idv_channel_split(s, facet_sql, facet_params),
        lambda s: capture_channel_breakdown(s, facet_sql, facet_params),
        lambda s: capture_channel_timing(s, facet_sql, facet_params),
        lambda s: teaming_targets(s, facet_sql, facet_params),
        lambda s: set_aside_parent_shadow(s, facet_sql, facet_params),
        lambda s: expiring_capture_channels(s, facet_sql, facet_params),
        lambda s: motion_money_paths(s, facet_sql, facet_params),
        lambda s: expiring_timeline(s, facet_sql, facet_params),
        lambda s: vehicle_breakdown(s, facet_sql, facet_params, limit=limit),
        lambda s: ffp_shaping_radar(s, query),
    )

    result: dict[str, Any] = {
        "status": "ready",
        "mode": "overview",
        "schema_version": OVERVIEW_SCHEMA_VERSION,
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
        "expiring_timeline": expiring_tl,
        "vehicle_breakdown": vehicles,
        "ffp_shaping": ffp,
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
    months_ahead: int = EXPIRING_MONTHS_AHEAD,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT
            ({CAPTURE_CHANNEL_EXPR}) AS channel,
            COUNT(*) AS contracts,
            {round_numeric(f"SUM({EXPIRING_CONTRACT_VALUE_EXPR}) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {BASE_AWARD_WHERE}
          {facet_sql}
        GROUP BY channel
    """
    params = {**facet_params, "months_ahead": str(months_ahead)}
    rows = (await session.execute(text(sql), params)).all()
    raw = [
        {"channel": str(r.channel or "other"), "actions": int(r.contracts), "millions": float(r.millions or 0)}
        for r in rows
    ]
    return _normalize_channel_rows(raw)


async def expiring_timeline(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    months_ahead: int = EXPIRING_MONTHS_AHEAD,
) -> dict[str, Any]:
    """Monthly buckets of expiring contract $ and base-award count."""
    sql = f"""
        SELECT
            to_char(date_trunc('month', period_of_performance_current_end_date), 'YYYY-MM') AS month,
            COUNT(*) AS contracts,
            {round_numeric(f"SUM({EXPIRING_CONTRACT_VALUE_EXPR}) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {BASE_AWARD_WHERE}
          {facet_sql}
        GROUP BY date_trunc('month', period_of_performance_current_end_date)
        ORDER BY month ASC
    """
    params = {**facet_params, "months_ahead": str(months_ahead)}
    rows = (await session.execute(text(sql), params)).all()
    buckets = [
        {
            "month": str(r.month),
            "contracts": int(r.contracts),
            "actions": int(r.contracts),
            "millions": float(r.millions or 0),
        }
        for r in rows
    ]
    if not buckets:
        return {"buckets": [], "peak_millions": 0.0, "insight": ""}

    peak = max(buckets, key=lambda b: b["millions"])
    peak_label = peak["month"]
    try:
        year, mon = peak_label.split("-")
        month_names = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        peak_label = f"{month_names[int(mon)]} {year}"
    except (ValueError, IndexError):
        pass
    insight = (
        f"Peak cluster {peak_label} — {format_money_from_millions(peak['millions'])} across "
        f"{format_count(peak['contracts'])} contracts"
        if peak["millions"] > 0
        else ""
    )
    return {
        "buckets": buckets,
        "peak_millions": float(peak["millions"]),
        "insight": insight,
    }


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


def _intensity_quadrant(
    actions: int,
    millions: float,
    *,
    median_actions: float,
    median_millions: float,
) -> str:
    hi_actions = actions >= median_actions
    hi_money = millions >= median_millions
    if hi_actions and hi_money:
        return "hot"
    if hi_money:
        return "high_value"
    if hi_actions:
        return "high_volume"
    return "watch"


def _intensity_buyer_grouping(query: InsightFacetQuery) -> tuple[str, str, str, str]:
    """Awarding office by default — contracting shop is the actionable capture unit."""
    if query.funding_office and not query.awarding_office:
        expr = "COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified office)')"
        return expr, "funding_office", "office", "Funding office (requirements owner)"
    expr = "COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)')"
    return expr, "awarding_office", "office", "Awarding office (contract actions)"


async def agency_intensity(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    limit: int = INTENSITY_OFFICE_LIMIT,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    group_expr, hone_field, level, level_label = _intensity_buyer_grouping(query)
    sql = f"""
        SELECT
            {group_expr} AS label,
            MAX(COALESCE(NULLIF(TRIM(({AGENCY_NORMALIZED_EXPR})), ''), '')) AS parent_agency,
            MAX(
                COALESCE(
                    NULLIF(TRIM(awarding_sub_agency_name), ''),
                    NULLIF(TRIM(funding_sub_agency_name), ''),
                    ''
                )
            ) AS parent_sub,
            COUNT(DISTINCT NULLIF(TRIM(funding_office_name), '')) AS funding_office_count,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE {group_expr} != ''
          AND {group_expr} != '(Unspecified)'
          AND {group_expr} != '(Unspecified office)'
          {facet_sql}
        GROUP BY label
        HAVING COUNT(*) > 0
        ORDER BY millions DESC NULLS LAST, actions DESC NULLS LAST
        LIMIT :limit
    """
    total_sql = f"""
        SELECT {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1 {facet_sql}
    """
    async def _intensity_rows(s: AsyncSession):
        return (await s.execute(text(sql), {**facet_params, "limit": limit})).all()

    async def _intensity_total(s: AsyncSession):
        return (await s.execute(text(total_sql), facet_params)).first()

    async def _intensity_office_count(s: AsyncSession):
        return (
            await s.execute(
                text(
                    f"""
                    SELECT COUNT(DISTINCT {group_expr}) AS n
                    FROM {PRIME_TABLE}
                    WHERE {group_expr} != ''
                      AND {group_expr} != '(Unspecified)'
                      AND {group_expr} != '(Unspecified office)'
                      {facet_sql}
                    """
                ),
                facet_params,
            )
        ).first()

    rows, total_row, office_count_row = await gather_pg(
        _intensity_rows,
        _intensity_total,
        _intensity_office_count,
    )
    slice_total_m = float(total_row.millions or 0) if total_row else 0.0
    office_total = int(office_count_row.n or 0) if office_count_row else 0
    points = [
        {
            "label": str(r.label),
            "agency": str(r.label),
            "parent_agency": str(r.parent_agency or ""),
            "parent_sub": str(r.parent_sub or ""),
            "funding_office_count": int(r.funding_office_count or 0),
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
        p["quadrant"] = _intensity_quadrant(
            p["actions"],
            p["millions"],
            median_actions=median_actions,
            median_millions=median_millions,
        )
        p["hot"] = p["quadrant"] == "hot"
        if slice_total_m > 0:
            p["share_pct"] = round(100.0 * p["millions"] / slice_total_m, 1)
        if p["hot"]:
            hot.append(p["label"])
    return {
        "points": points,
        "median_actions": median_actions,
        "median_millions": median_millions,
        "slice_total_millions": slice_total_m,
        "hot_agencies": hot,
        "hot_labels": hot,
        "level": level,
        "level_label": level_label,
        "hone_field": hone_field,
        "office_total": office_total,
        "office_shown": len(points),
        "caption": (
            f"Top {len(points)} of {office_total} awarding offices by obligated $. "
            "Click any dot → Agency profile with funding-office customer map."
        ),
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


def _office_node_id(kind: str, label: str) -> str:
    return f"{kind}::{label}"


async def office_customer_trace(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    awarding_office: str,
    limit: int = 14,
    recipients_per_funding: int = 3,
) -> dict[str, Any]:
    """Awarding office → funding office customer map — DR expose hop-1 + prime BFS hop-2."""
    office = (awarding_office or query.awarding_office or "").strip()
    empty: dict[str, Any] = {
        "mode": "office_customer_trace",
        "method": "Awarding office → funding office (requirements owner) obligation paths.",
        "flows": [],
        "relations_graph": {},
        "funding_office_count": 0,
        "summary": "No awarding office in scope.",
    }
    if not office:
        return empty

    facet_sql, facet_params = build_facet_sql(query)
    funding_sql = f"""
        SELECT
            COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)') AS funding_office,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE COALESCE(NULLIF(TRIM(awarding_office_name), ''), '') = :awarding_office
          {facet_sql}
        GROUP BY funding_office
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    funding_rows = (
        await session.execute(
            text(funding_sql),
            {**facet_params, "awarding_office": office, "limit": limit},
        )
    ).all()
    if not funding_rows:
        return {
            **empty,
            "summary": f"No funding-office paths for awarding office “{office[:48]}”.",
        }

    flows = [
        {
            "source": office,
            "target": str(r.funding_office),
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in funding_rows
    ]
    total_m = sum(f["millions"] for f in flows) or 1.0
    for f in flows:
        f["pct"] = round(100.0 * f["millions"] / total_m, 1)

    top_funding = [f["target"] for f in flows[: min(8, len(flows))]]
    recipient_sql = f"""
        WITH ranked AS (
            SELECT
                COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)') AS funding_office,
                recipient_name AS recipient,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)')
                    ORDER BY SUM(COALESCE(federal_action_obligation, 0)) DESC NULLS LAST
                ) AS rn
            FROM {PRIME_TABLE}
            WHERE COALESCE(NULLIF(TRIM(awarding_office_name), ''), '') = :awarding_office
              AND recipient_name IS NOT NULL
              {facet_sql}
            GROUP BY funding_office, recipient_name
        )
        SELECT funding_office, recipient, actions, millions
        FROM ranked
        WHERE rn <= :recipients_per_funding
          AND funding_office = ANY(:top_funding)
        ORDER BY millions DESC NULLS LAST
    """
    recipient_rows = (
        await session.execute(
            text(recipient_sql),
            {
                **facet_params,
                "awarding_office": office,
                "recipients_per_funding": recipients_per_funding,
                "top_funding": top_funding,
            },
        )
    ).all()

    awarding_id = _office_node_id("awarding_office", office)
    nodes: dict[str, dict[str, Any]] = {
        awarding_id: {
            "id": awarding_id,
            "label": office,
            "kind": "awarding_office",
            "hop": 0,
            "millions_out": total_m,
            "millions_in": 0.0,
            "millions_total": total_m,
            "actions": sum(f["actions"] for f in flows),
            "magnitude_tier": "high" if total_m >= 10 else "medium" if total_m >= 1 else "low",
        },
    }
    edges: list[dict[str, Any]] = []
    for f in flows:
        fund_label = f["target"]
        fund_id = _office_node_id("funding_office", fund_label)
        fm = f["millions"]
        tier = "high" if fm >= 10 else "medium" if fm >= 1 else "low"
        nodes.setdefault(
            fund_id,
            {
                "id": fund_id,
                "label": fund_label,
                "kind": "funding_office",
                "hop": 1,
                "millions_in": 0.0,
                "millions_out": 0.0,
                "millions_total": 0.0,
                "actions": 0,
                "magnitude_tier": tier,
            },
        )
        nodes[fund_id]["millions_in"] += fm
        nodes[fund_id]["millions_total"] += fm
        nodes[fund_id]["actions"] += f["actions"]
        edges.append({
            "source": awarding_id,
            "target": fund_id,
            "kind": "customer_trace",
            "family": "customer_trace",
            "millions": fm,
            "actions": f["actions"],
            "hop": 1,
        })

    for r in recipient_rows:
        fund_id = _office_node_id("funding_office", str(r.funding_office))
        if fund_id not in nodes:
            continue
        prime_label = str(r.recipient)
        prime_id = _office_node_id("prime", prime_label)
        pm = float(r.millions or 0)
        tier = "high" if pm >= 10 else "medium" if pm >= 1 else "low"
        nodes.setdefault(
            prime_id,
            {
                "id": prime_id,
                "label": prime_label,
                "kind": "prime",
                "hop": 2,
                "millions_in": pm,
                "millions_out": 0.0,
                "millions_total": pm,
                "actions": int(r.actions),
                "magnitude_tier": tier,
            },
        )
        edges.append({
            "source": fund_id,
            "target": prime_id,
            "kind": "obligation",
            "family": "org_money",
            "millions": pm,
            "actions": int(r.actions),
            "hop": 2,
        })

    relations_graph = {
        "mode": "office_customer_graph",
        "method": (
            "BFS expose — hop 1: awarding → funding offices (customers); "
            "hop 2: top primes per funding office."
        ),
        "nodes": list(nodes.values())[:48],
        "edges": edges[:96],
        "relation_families": ["customer_trace", "org_money"],
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_hop": 2 if recipient_rows else 1,
            "millions_in_subgraph": round(total_m, 2),
            "seed_awarding_office": office,
            "funding_office_count": len(flows),
        },
    }

    return {
        "mode": "office_customer_trace",
        "method": relations_graph["method"],
        "flows": flows,
        "relations_graph": relations_graph,
        "funding_office_count": len(flows),
        "summary": (
            f"{len(flows)} funding offices · ${total_m:.1f}M through "
            f"awarding office “{_truncate_office_label(office)}”."
        ),
    }


def _truncate_office_label(label: str, *, max_len: int = 40) -> str:
    s = (label or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _empty_customer_trace(summary: str = "No buyer trace in scope.") -> dict[str, Any]:
    return {
        "mode": "customer_trace",
        "method": "Buyer hierarchy — requirements owners and top performers.",
        "flows": [],
        "relations_graph": {},
        "funding_office_count": 0,
        "summary": summary,
    }


async def buyer_customer_trace(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    root_label: str,
    root_scope: str,
    limit: int = 14,
    children_per_parent: int = 3,
    recipients_per_funding: int = 3,
    subs_per_prime: int = 2,
) -> dict[str, Any]:
    """Scope-adaptive customer trace — agency / sub-agency / office."""
    root = (root_label or "").strip()
    if not root:
        return _empty_customer_trace()
    if root_scope == "office":
        trace = await office_customer_trace(
            session,
            query,
            awarding_office=root,
            limit=limit,
            recipients_per_funding=recipients_per_funding,
        )
        if trace.get("flows"):
            await _enrich_customer_trace_subs(session, query, trace, subs_per_prime=subs_per_prime)
        trace["mode"] = "customer_trace"
        return trace
    if root_scope == "sub_agency":
        return await _hierarchy_customer_trace(
            session,
            query,
            root_label=root,
            root_kind="sub_agency",
            child_col="awarding_office_name",
            child_kind="awarding_office",
            grandchild_col="recipient_name",
            grandchild_kind="prime",
            sankey_title="Customer map — sub-agency → contracting office",
            graph_title="Customer trace — sub-agency → offices → primes",
            limit=limit,
            children_per_parent=children_per_parent,
        )
    if root_scope == "agency":
        return await _hierarchy_customer_trace(
            session,
            query,
            root_label=root,
            root_kind="agency",
            child_col="awarding_sub_agency_name",
            child_kind="sub_agency",
            grandchild_col="awarding_office_name",
            grandchild_kind="awarding_office",
            sankey_title="Customer map — agency → sub-agency",
            graph_title="Customer trace — agency → sub-agencies → offices",
            limit=limit,
            children_per_parent=children_per_parent,
        )
    return _empty_customer_trace()


async def _hierarchy_customer_trace(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    root_label: str,
    root_kind: str,
    child_col: str,
    child_kind: str,
    grandchild_col: str,
    grandchild_kind: str,
    sankey_title: str,
    graph_title: str,
    limit: int,
    children_per_parent: int,
) -> dict[str, Any]:
    facet_sql, facet_params = build_facet_sql(query)
    child_sql = f"""
        SELECT
            COALESCE(NULLIF(TRIM({child_col}), ''), '(Unspecified)') AS child,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE 1=1
          {facet_sql}
        GROUP BY child
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    child_rows = (
        await session.execute(text(child_sql), {**facet_params, "limit": limit})
    ).all()
    if not child_rows:
        return _empty_customer_trace(f"No {child_kind} paths for “{root_label[:48]}”.")

    flows = [
        {
            "source": root_label,
            "target": str(r.child),
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in child_rows
    ]
    total_m = sum(f["millions"] for f in flows) or 1.0
    for f in flows:
        f["pct"] = round(100.0 * f["millions"] / total_m, 1)

    top_children = [f["target"] for f in flows[: min(8, len(flows))]]
    grandchild_sql = f"""
        WITH ranked AS (
            SELECT
                COALESCE(NULLIF(TRIM({child_col}), ''), '(Unspecified)') AS parent,
                COALESCE(NULLIF(TRIM({grandchild_col}), ''), '(Unspecified)') AS grandchild,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(NULLIF(TRIM({child_col}), ''), '(Unspecified)')
                    ORDER BY SUM(COALESCE(federal_action_obligation, 0)) DESC NULLS LAST
                ) AS rn
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
            GROUP BY parent, grandchild
        )
        SELECT parent, grandchild, actions, millions
        FROM ranked
        WHERE rn <= :children_per_parent
          AND parent = ANY(:top_children)
        ORDER BY millions DESC NULLS LAST
    """
    grandchild_rows = (
        await session.execute(
            text(grandchild_sql),
            {
                **facet_params,
                "children_per_parent": children_per_parent,
                "top_children": top_children,
            },
        )
    ).all()

    root_id = _office_node_id(root_kind, root_label)
    nodes: dict[str, dict[str, Any]] = {
        root_id: {
            "id": root_id,
            "label": root_label,
            "kind": root_kind,
            "hop": 0,
            "millions_out": total_m,
            "millions_in": 0.0,
            "millions_total": total_m,
            "actions": sum(f["actions"] for f in flows),
            "magnitude_tier": "high" if total_m >= 10 else "medium" if total_m >= 1 else "low",
        },
    }
    edges: list[dict[str, Any]] = []
    for f in flows:
        child_label = f["target"]
        child_id = _office_node_id(child_kind, child_label)
        cm = f["millions"]
        tier = "high" if cm >= 10 else "medium" if cm >= 1 else "low"
        nodes.setdefault(
            child_id,
            {
                "id": child_id,
                "label": child_label,
                "kind": child_kind,
                "hop": 1,
                "millions_in": 0.0,
                "millions_out": 0.0,
                "millions_total": 0.0,
                "actions": 0,
                "magnitude_tier": tier,
            },
        )
        nodes[child_id]["millions_in"] += cm
        nodes[child_id]["millions_total"] += cm
        nodes[child_id]["actions"] += f["actions"]
        edges.append({
            "source": root_id,
            "target": child_id,
            "kind": "customer_trace",
            "family": "customer_trace",
            "millions": cm,
            "actions": f["actions"],
            "hop": 1,
        })

    for r in grandchild_rows:
        child_id = _office_node_id(child_kind, str(r.parent))
        if child_id not in nodes:
            continue
        gc_label = str(r.grandchild)
        gc_id = _office_node_id(grandchild_kind, gc_label)
        gm = float(r.millions or 0)
        tier = "high" if gm >= 10 else "medium" if gm >= 1 else "low"
        nodes.setdefault(
            gc_id,
            {
                "id": gc_id,
                "label": gc_label,
                "kind": grandchild_kind,
                "hop": 2,
                "millions_in": gm,
                "millions_out": 0.0,
                "millions_total": gm,
                "actions": int(r.actions),
                "magnitude_tier": tier,
            },
        )
        edges.append({
            "source": child_id,
            "target": gc_id,
            "kind": "obligation" if grandchild_kind == "prime" else "customer_trace",
            "family": "org_money" if grandchild_kind == "prime" else "customer_trace",
            "millions": gm,
            "actions": int(r.actions),
            "hop": 2,
        })

    relations_graph = {
        "mode": "customer_trace_graph",
        "method": graph_title,
        "nodes": list(nodes.values())[:48],
        "edges": edges[:96],
        "relation_families": ["customer_trace", "org_money"],
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_hop": 2 if grandchild_rows else 1,
            "millions_in_subgraph": round(total_m, 2),
            "root_scope": root_kind,
        },
    }
    return {
        "mode": "customer_trace",
        "method": relations_graph["method"],
        "flows": flows,
        "relations_graph": relations_graph,
        "sankey_title": sankey_title,
        "graph_title": graph_title,
        "funding_office_count": len(flows),
        "summary": (
            f"{len(flows)} {child_kind.replace('_', ' ')}s · ${total_m:.1f}M under "
            f"“{_truncate_office_label(root_label)}”."
        ),
    }


async def _subs_for_primes(
    session: AsyncSession,
    query: InsightFacetQuery,
    primes: list[str],
    *,
    subs_per_prime: int,
) -> list[dict[str, Any]]:
    if not primes or subs_per_prime < 1:
        return []
    if not await table_exists(session, SUB_TABLE):
        return []
    facet_sql, facet_params = _subaward_facet_sql(query)
    where_extra = f"AND {facet_sql}" if facet_sql else ""
    sql = f"""
        WITH ranked AS (
            SELECT
                prime_awardee_name AS prime,
                subawardee_name AS sub,
                {round_numeric("SUM(COALESCE(NULLIF(subaward_amount, '')::DOUBLE PRECISION, 0)) / 1000000.0")} AS millions,
                COUNT(*) AS links,
                ROW_NUMBER() OVER (
                    PARTITION BY prime_awardee_name
                    ORDER BY SUM(COALESCE(NULLIF(subaward_amount, '')::DOUBLE PRECISION, 0)) DESC NULLS LAST
                ) AS rn
            FROM {SUB_TABLE}
            WHERE prime_awardee_name = ANY(:primes)
              AND subawardee_name IS NOT NULL
              {where_extra}
            GROUP BY prime_awardee_name, subawardee_name
        )
        SELECT prime, sub, millions, links
        FROM ranked
        WHERE rn <= :subs_per_prime
        ORDER BY millions DESC NULLS LAST
    """
    rows = (
        await session.execute(
            text(sql),
            {**facet_params, "primes": primes, "subs_per_prime": subs_per_prime},
        )
    ).all()
    return [
        {
            "prime": r.prime,
            "sub": r.sub,
            "millions": float(r.millions or 0),
            "links": int(r.links),
        }
        for r in rows
    ]


async def _enrich_customer_trace_subs(
    session: AsyncSession,
    query: InsightFacetQuery,
    trace: dict[str, Any],
    *,
    subs_per_prime: int,
) -> None:
    graph = trace.get("relations_graph") or {}
    nodes_list = graph.get("nodes") or []
    edges = list(graph.get("edges") or [])
    nodes = {n["id"]: n for n in nodes_list}
    primes = [n["label"] for n in nodes_list if n.get("kind") == "prime"]
    if not primes:
        return
    sub_edges = await _subs_for_primes(session, query, primes[:12], subs_per_prime=subs_per_prime)
    for e in sub_edges:
        prime_id = _office_node_id("prime", e["prime"])
        if prime_id not in nodes:
            continue
        sub_label = e["sub"]
        sub_id = _office_node_id("sub", sub_label)
        sm = e["millions"]
        tier = "high" if sm >= 10 else "medium" if sm >= 1 else "low"
        nodes.setdefault(
            sub_id,
            {
                "id": sub_id,
                "label": sub_label,
                "kind": "sub",
                "hop": 3,
                "millions_in": sm,
                "millions_out": 0.0,
                "millions_total": sm,
                "actions": e["links"],
                "magnitude_tier": tier,
            },
        )
        edges.append({
            "source": prime_id,
            "target": sub_id,
            "kind": "teaming",
            "family": "teaming",
            "millions": sm,
            "actions": e["links"],
            "hop": 3,
        })
    summary = graph.get("summary") or {}
    if sub_edges:
        summary["max_hop"] = max(int(summary.get("max_hop") or 0), 3)
    graph["nodes"] = list(nodes.values())[:56]
    graph["edges"] = edges[:112]
    graph["summary"] = summary
    trace["relations_graph"] = graph


async def entity_obligation_flow(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    entity_scope: str,
    limit: int = 14,
    subs_per_prime: int = 2,
) -> dict[str, Any]:
    """Drill-scoped obligation paths — no upstream agency hop."""
    facet_sql, facet_params = build_facet_sql(query)
    if entity_scope == "office":
        source_expr = (
            "COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)')"
        )
        title = "Obligation paths — funding office → prime"
        method = "Funding office → prime within awarding-office drill."
    else:
        source_expr = (
            "COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)')"
        )
        title = "Obligation paths — contracting office → prime"
        method = "Contracting office → prime within buyer drill."

    sql = f"""
        SELECT
            {source_expr} AS source,
            recipient_name AS target,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY source, target
        ORDER BY millions DESC NULLS LAST
        LIMIT :limit
    """
    rows = (await session.execute(text(sql), {**facet_params, "limit": limit})).all()
    flows = [
        {
            "source": str(r.source),
            "target": str(r.target),
            "millions": float(r.millions or 0),
            "actions": int(r.actions),
        }
        for r in rows
    ]
    top_primes = list(dict.fromkeys(f["target"] for f in flows))[:8]
    for e in await _subs_for_primes(session, query, top_primes, subs_per_prime=subs_per_prime):
        flows.append({
            "source": e["prime"],
            "target": e["sub"],
            "millions": e["millions"],
            "actions": e["links"],
        })
    return {
        "mode": "entity_obligation_flow",
        "method": method,
        "title": title,
        "flows": flows,
        "summary": f"{len(flows)} obligation hops in buyer drill",
    }


async def entity_award_spine(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    entity_scope: str,
    limit: int = 20,
    trace_buyer_office: str | None = None,
    trace_recipient: str | None = None,
) -> dict[str, Any]:
    """Top base awards in drill — contract hop linking buyer offices to recipients."""
    if not query.has_filters():
        return {"mode": "entity_award_spine", "rows": [], "summary": "Run slice first."}
    facet_sql, facet_params = build_facet_sql(query)
    show_funding = entity_scope == "office"
    buyer_expr = (
        "COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)')"
        if show_funding
        else "COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)')"
    )
    trace_sql = ""
    trace_params: dict[str, Any] = {}
    buyer_filter = (trace_buyer_office or "").strip()
    recipient_filter = (trace_recipient or "").strip()
    if buyer_filter:
        trace_sql += f" AND {buyer_expr} = :trace_buyer_office"
        trace_params["trace_buyer_office"] = buyer_filter
    if recipient_filter:
        trace_sql += " AND recipient_name = :trace_recipient"
        trace_params["trace_recipient"] = recipient_filter
    count_sql = f"""
        SELECT
            COUNT(*) AS total_contracts,
            COUNT(DISTINCT recipient_name) AS total_recipients
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          AND contract_award_unique_key IS NOT NULL
          {BASE_AWARD_WHERE}
          {facet_sql}
          {trace_sql}
    """
    count_row = (
        await session.execute(text(count_sql), {**facet_params, **trace_params})
    ).first()
    total_contracts = int(count_row.total_contracts or 0) if count_row else 0
    total_recipients = int(count_row.total_recipients or 0) if count_row else 0
    sql = f"""
        SELECT
            contract_award_unique_key AS award_key,
            COALESCE(
                NULLIF(TRIM(award_id_piid), ''),
                NULLIF(TRIM(parent_award_id_piid), '')
            ) AS piid,
            recipient_name AS recipient,
            COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)') AS funding_office,
            COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)') AS awarding_office,
            {round_numeric(f"{EXPIRING_CONTRACT_VALUE_EXPR} / 1000000.0")} AS millions,
            period_of_performance_current_end_date::text AS end_date,
            COALESCE(NULLIF(TRIM(type_of_contract_pricing), ''), 'Unknown') AS pricing
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          AND contract_award_unique_key IS NOT NULL
          {BASE_AWARD_WHERE}
          {facet_sql}
          {trace_sql}
        ORDER BY {EXPIRING_CONTRACT_VALUE_EXPR} DESC NULLS LAST
        LIMIT :limit
    """
    raw = (
        await session.execute(text(sql), {**facet_params, **trace_params, "limit": limit})
    ).all()
    rows = [
        {
            "award_key": str(r.award_key),
            "piid": str(r.piid or "").strip() or None,
            "recipient": str(r.recipient),
            "funding_office": str(r.funding_office),
            "awarding_office": str(r.awarding_office),
            "millions": float(r.millions or 0),
            "end_date": str(r.end_date) if r.end_date else None,
            "pricing": str(r.pricing),
            "buyer_office": str(r.funding_office if show_funding else r.awarding_office),
        }
        for r in raw
        if r.award_key
    ]
    # Same row shape as expiring list → insights_recompete_rows.html (drawer holds actions)
    recompete_rows = []
    for row in rows:
        months_to_end = 0
        if row["end_date"]:
            try:
                from datetime import date, datetime

                end = datetime.fromisoformat(str(row["end_date"])[:10]).date()
                today = date.today()
                months_to_end = max(0, (end.year - today.year) * 12 + (end.month - today.month))
            except ValueError:
                months_to_end = 0
        recompete_rows.append({
            "award_key": row["award_key"],
            "recipient": row["recipient"],
            "agency": row["buyer_office"],
            "funding_office": row["funding_office"],
            "piid": row["piid"],
            "end_date": row["end_date"],
            "months_to_end": months_to_end,
            "obligation": row["millions"] * 1_000_000.0,
        })
    total_m = round(sum(row["millions"] for row in rows), 1)
    shown = len(rows)
    if buyer_filter or recipient_filter:
        label_parts = [p for p in (buyer_filter, recipient_filter) if p]
        summary = f"{shown} contract{'s' if shown != 1 else ''}"
        if total_contracts > shown:
            summary += f" of {total_contracts}"
        if label_parts:
            summary += " · " + " × ".join(label_parts)
        if total_m:
            summary += f" · ${total_m:.1f}M shown"
    elif total_contracts > shown:
        summary = f"Top {shown} of {total_contracts} contracts"
    else:
        summary = f"{shown} contract{'s' if shown != 1 else ''}"
    if not (buyer_filter or recipient_filter):
        if total_recipients:
            summary += f" · {total_recipients} contractor{'s' if total_recipients != 1 else ''}"
        if total_m:
            summary += f" · ${total_m:.1f}M shown"
    return {
        "mode": "entity_award_spine",
        "rows": rows,
        "summary": summary,
        "total_contracts": total_contracts,
        "total_recipients": total_recipients,
        "shown": shown,
        "recompete_rows": recompete_rows,
        "trace_filtered": bool(buyer_filter or recipient_filter),
    }


async def entity_recipient_matrix(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    entity_scope: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Heatmap rows scoped to drill depth — funding×prime or office×prime."""
    facet_sql, facet_params = build_facet_sql(query)
    if entity_scope == "office":
        row_expr = (
            "COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)')"
        )
        row_axis = "funding_office"
        summary = "Funding office × prime ties in drill"
    elif entity_scope in {"sub_agency", "agency"}:
        row_expr = (
            "COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)')"
        )
        row_axis = "awarding_office"
        summary = "Contracting office × prime ties in drill"
    else:
        return await agency_recipient_matrix(session, query, limit=limit)

    sql = f"""
        SELECT
            {row_expr} AS agency,
            recipient_name AS recipient,
            COUNT(*) AS actions,
            {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS millions
        FROM {PRIME_TABLE}
        WHERE recipient_name IS NOT NULL
          {facet_sql}
        GROUP BY agency, recipient_name
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
        "row_axis": row_axis,
        "summary": summary,
    }


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


def _award_shape_gate(
    *,
    pricing_bucket: str,
    agency_non_fixed_pct: float,
    pressure_tier: str,
    obligation_millions: float,
    pricing_label: str,
) -> tuple[str | None, str | None]:
    """Per-award shape gate for expiring rows — None for firm-fixed awards."""
    if pricing_bucket == "firm_fixed":
        return None, None
    oblig_m = float(obligation_millions or 0)
    if agency_non_fixed_pct >= 35 and oblig_m >= 0.5:
        return (
            "shape_now",
            f"Non-fixed ({pricing_label}) expiring at agency with {agency_non_fixed_pct}% "
            "flexible pricing — early shaping window",
        )
    if agency_non_fixed_pct >= 25 or pressure_tier in ("high", "moderate"):
        return "monitor", "Flexible pricing recompete — watch for shift toward fixed-price terms"
    return "watch", "Non-fixed expiring award — lower agency pressure in slice"


async def agency_pricing_pressure(
    session: AsyncSession,
    facet_sql: str,
    facet_params: dict[str, Any],
    *,
    agency_limit: int = 50,
) -> dict[str, dict[str, Any]]:
    """Agency-level non-fixed pricing share — shared by FFP radar and expiring row badges."""
    sql = f"""
        WITH bucketed AS (
            SELECT
                ({AGENCY_EXPR}) AS agency,
                ({PRICING_BUCKET_EXPR}) AS pricing_bucket,
                federal_action_obligation AS oblig
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
        ),
        agency_totals AS (
            SELECT agency, SUM(oblig) AS total_oblig
            FROM bucketed
            GROUP BY agency
            HAVING SUM(oblig) > 0
        ),
        agency_buckets AS (
            SELECT agency, pricing_bucket, SUM(oblig) AS bucket_oblig
            FROM bucketed
            GROUP BY agency, pricing_bucket
        )
        SELECT
            tot.agency,
            {round_numeric("tot.total_oblig / 1000000.0")} AS total_millions,
            bk.pricing_bucket,
            {round_numeric("bk.bucket_oblig / 1000000.0")} AS millions
        FROM agency_totals tot
        JOIN agency_buckets bk ON bk.agency = tot.agency
        ORDER BY tot.total_oblig DESC NULLS LAST
    """
    rows = (await session.execute(text(sql), facet_params)).all()
    agency_map: dict[str, dict[str, float]] = {}
    total_lookup: dict[str, float] = {}
    for r in rows:
        agency = r.agency
        if agency not in agency_map:
            agency_map[agency] = {}
            total_lookup[agency] = float(r.total_millions or 0)
        agency_map[agency][str(r.pricing_bucket)] = float(r.millions or 0)

    lookup: dict[str, dict[str, Any]] = {}
    for agency, buckets in sorted(
        agency_map.items(),
        key=lambda x: total_lookup.get(x[0], 0),
        reverse=True,
    )[:agency_limit]:
        total = total_lookup.get(agency, 0) or 1.0
        non_fixed_m = sum(
            buckets.get(k, 0)
            for k in ("cost_reimbursement", "time_materials", "performance_based", "other")
        )
        non_fixed_pct = round((non_fixed_m / total) * 100, 1)
        lookup[agency] = {
            "non_fixed_pct": non_fixed_pct,
            "pressure_tier": _pressure_tier(non_fixed_pct),
        }
    return lookup


async def enrich_expiring_rows_shape_gates(
    session: AsyncSession,
    query: InsightFacetQuery,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach shape_gate + shape_reason to expiring contract rows (in-place copy)."""
    if not rows or not query.has_filters():
        return rows
    facet_sql, facet_params = build_facet_sql(query)
    pressure = await agency_pricing_pressure(session, facet_sql, facet_params)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        agency = str(copy.get("agency") or "")
        agency_info = pressure.get(agency, {})
        gate, reason = _award_shape_gate(
            pricing_bucket=str(copy.get("pricing_bucket") or "other"),
            agency_non_fixed_pct=float(agency_info.get("non_fixed_pct") or 0),
            pressure_tier=str(agency_info.get("pressure_tier") or "low"),
            obligation_millions=float(copy.get("obligation") or 0) / 1_000_000.0,
            pricing_label=str(copy.get("pricing") or "Unknown"),
        )
        if gate:
            copy["shape_gate"] = gate
            copy["shape_reason"] = reason
        enriched.append(copy)
    return enriched


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
            {round_numeric(f"{EXPIRING_CONTRACT_VALUE_EXPR} / 1000000.0")} AS obligation_millions,
            period_of_performance_current_end_date::text AS end_date
        FROM {PRIME_TABLE}
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {BASE_AWARD_WHERE}
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
        agency_non_fixed = agency_pct_lookup.get(er.agency, 0)
        pressure_tier = agency_tier_lookup.get(er.agency, "low")
        oblig_m = float(er.obligation_millions or 0)
        shape_gate, shape_reason = _award_shape_gate(
            pricing_bucket=str(er.pricing_bucket or "other"),
            agency_non_fixed_pct=agency_non_fixed,
            pressure_tier=pressure_tier,
            obligation_millions=oblig_m,
            pricing_label=str(er.pricing or "Unknown"),
        )
        if not shape_gate:
            continue

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


async def agency_adjacent_competitors(
    session: AsyncSession,
    query: InsightFacetQuery,
    *,
    entity_scope: str,
    limit: int = 8,
    exclude_top_n: int = 8,
    max_share_pct: float = 12.0,
) -> list[dict[str, Any]]:
    """Niche primes at shared buyer units within entity drill — not top share holders."""
    facet_sql, facet_params = build_facet_sql(query)
    if entity_scope == "office":
        buyer_expr = (
            "COALESCE(NULLIF(TRIM(funding_office_name), ''), '(Unspecified funding)')"
        )
    else:
        buyer_expr = (
            "COALESCE(NULLIF(TRIM(awarding_office_name), ''), '(Unspecified office)')"
        )

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
    drill_total = sum(float(r.millions or 0) for r in market_rows) or 1.0
    top_names = {r.recipient_name for r in market_rows[:exclude_top_n]}

    overlap_sql = f"""
        WITH drill_buyers AS (
            SELECT DISTINCT {buyer_expr} AS buyer
            FROM {PRIME_TABLE}
            WHERE 1=1
              {facet_sql}
        ),
        recipient_totals AS (
            SELECT recipient_name,
                   {round_numeric("SUM(COALESCE(federal_action_obligation, 0)) / 1000000.0")} AS drill_millions
            FROM {PRIME_TABLE}
            WHERE recipient_name IS NOT NULL
              {facet_sql}
            GROUP BY recipient_name
        ),
        overlap AS (
            SELECT
                p.recipient_name,
                {buyer_expr} AS buyer,
                COUNT(*) AS actions,
                {round_numeric("SUM(COALESCE(p.federal_action_obligation, 0)) / 1000000.0")} AS millions
            FROM {PRIME_TABLE} p
            WHERE p.recipient_name IS NOT NULL
              {facet_sql}
              AND {buyer_expr} IN (SELECT buyer FROM drill_buyers)
            GROUP BY p.recipient_name, {buyer_expr}
        )
        SELECT
            o.recipient_name,
            COUNT(DISTINCT o.buyer) AS shared_buyers,
            SUM(o.actions) AS total_actions,
            {round_numeric("SUM(o.millions)")} AS shared_millions,
            MAX(o.buyer) AS sample_buyer,
            MAX(rt.drill_millions) AS drill_millions
        FROM overlap o
        LEFT JOIN recipient_totals rt ON rt.recipient_name = o.recipient_name
        GROUP BY o.recipient_name
        ORDER BY shared_buyers DESC, shared_millions ASC
        LIMIT :scan_limit
    """
    rows = (
        await session.execute(
            text(overlap_sql),
            {**facet_params, "scan_limit": max(limit * 3, 24)},
        )
    ).all()

    candidates: list[dict[str, Any]] = []
    for r in rows:
        name = r.recipient_name or "Unknown"
        if name in top_names:
            continue
        drill_m = float(r.drill_millions or 0)
        share_pct = round((drill_m / drill_total) * 100, 2)
        if share_pct > max_share_pct:
            continue
        shared_n = int(r.shared_buyers or 0)
        shared_m = float(r.shared_millions or 0)
        if shared_n >= 2 and share_pct <= 5.0:
            fit = "promising"
            fit_reason = "Adjacent at shared buyer units — flank or teammate candidate"
        elif shared_n >= 1:
            fit = "research"
            fit_reason = "Thin overlap in drill — validate capability before outreach"
        else:
            continue
        candidates.append({
            "recipient": name,
            "shared_agencies": shared_n,
            "shared_buyers": shared_n,
            "total_actions": int(r.total_actions or 0),
            "shared_millions": shared_m,
            "market_millions": drill_m,
            "market_share_pct": share_pct,
            "sample_agency": r.sample_buyer,
            "fit": fit,
            "fit_reason": fit_reason,
        })

    fit_order = {"promising": 0, "research": 1}
    candidates.sort(
        key=lambda c: (
            fit_order.get(c["fit"], 9),
            -(c["shared_buyers"] or 0),
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