"""MVP sign-off funnel helpers — facet → overview → watch → track → packet fill."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from thread.intel.pg_queries import table_exists
from thread.intel.sql_expressions import (
    AGENCY_EXPR,
    BASE_AWARD_WHERE,
    EXPIRING_MONTHS_AHEAD,
    MONTHS_TO_END_EXPR,
    PRIME_TABLE,
)


async def discover_expiring_award(
    session: AsyncSession,
    *,
    months_ahead: int = EXPIRING_MONTHS_AHEAD,
) -> dict[str, Any] | None:
    """Find one prime award expiring soon (for sign-off smoke when facet slice is unknown)."""
    if not await table_exists(session, PRIME_TABLE):
        return None
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
        WHERE period_of_performance_current_end_date IS NOT NULL
          AND period_of_performance_current_end_date <= CURRENT_DATE + (:months_ahead || ' months')::interval
          AND period_of_performance_current_end_date >= CURRENT_DATE
          {BASE_AWARD_WHERE}
          AND recipient_name IS NOT NULL
          AND NULLIF(TRIM(naics_code), '') IS NOT NULL
        ORDER BY period_of_performance_current_end_date ASC
        LIMIT 1
    """
    row = (
        await session.execute(text(sql), {"months_ahead": str(months_ahead)})
    ).first()
    if row is None:
        return None
    return {
        "award_key": row.award_key,
        "recipient": row.recipient,
        "obligation": float(row.obligation) if row.obligation is not None else None,
        "end_date": str(row.end_date) if row.end_date else None,
        "agency": row.agency,
        "months_to_end": int(row.months_to_end or 0),
        "naics_code": str(row.naics_code).strip(),
    }