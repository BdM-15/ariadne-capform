"""Phase 23a — SQL views over raw intel tables (no table rewrite).

Agency normalization, obligation semantics, optional dedup matview for Clew aggregates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg

from thread.config import Settings
from thread.intel.bulk_fields import PRIME_TABLE, SUB_TABLE
from thread.intel.bulk_migration import _append_log, _load_state, _pg_dsn, _save_state, state_path
from thread.intel.sql_expressions import (
    AGENCY_EXPR,
    AGENCY_NORMALIZED_EXPR,
    ANALYTICS_SCHEMA,
    DEDUP_MATVIEW,
    EXTENT_COMPETED_NORMALIZED_EXPR,
    OBLIGATION_KIND_EXPR,
    PRIME_AWARDS_VIEW,
    SET_ASIDE_CHART_EXPR,
    SET_ASIDE_NORMALIZED_EXPR,
    SUBAWARDS_VIEW,
    agency_normalized_expr,
)

logger = logging.getLogger(__name__)


def analytics_schema_ddl() -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {ANALYTICS_SCHEMA}"


def prime_awards_view_ddl() -> str:
    return f"""
        CREATE OR REPLACE VIEW {PRIME_AWARDS_VIEW} AS
        SELECT
            p.*,
            ({AGENCY_EXPR}) AS agency_raw,
            ({AGENCY_NORMALIZED_EXPR}) AS agency_normalized,
            ({agency_normalized_expr("parent_award_agency_name")}) AS parent_award_agency_normalized,
            ({agency_normalized_expr("awarding_sub_agency_name")}) AS awarding_sub_agency_normalized,
            ({agency_normalized_expr("funding_agency_name")}) AS funding_agency_normalized,
            (federal_action_obligation < 0) AS is_deobligation,
            (COALESCE(federal_action_obligation, 0) = 0) AS is_zero_obligation,
            (federal_action_obligation > 0) AS is_positive_obligation,
            ({OBLIGATION_KIND_EXPR}) AS obligation_kind,
            ({EXTENT_COMPETED_NORMALIZED_EXPR}) AS extent_competed_normalized,
            ({SET_ASIDE_NORMALIZED_EXPR}) AS set_aside_normalized,
            ({SET_ASIDE_CHART_EXPR}) AS set_aside_chart_bucket
        FROM {PRIME_TABLE} p
    """


def subawards_view_ddl() -> str:
    return f"""
        CREATE OR REPLACE VIEW {SUBAWARDS_VIEW} AS
        SELECT
            s.*,
            COALESCE(NULLIF(TRIM(prime_awardee_name), ''), '(Unknown Prime)') AS prime_awardee_display,
            UPPER(TRIM(COALESCE(subawardee_name, ''))) AS subawardee_normalized,
            ({agency_normalized_expr("prime_award_awarding_agency_name")}) AS prime_award_awarding_agency_normalized,
            ({agency_normalized_expr("prime_award_funding_agency_name")}) AS prime_award_funding_agency_normalized
        FROM {SUB_TABLE} s
    """


def dedup_matview_ddl() -> str:
    """Distinct-on slice for Clew aggregates — expensive on full 64M load."""
    return f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {DEDUP_MATVIEW} AS
        SELECT DISTINCT ON (
            award_id_piid,
            modification_number,
            action_date,
            federal_action_obligation,
            recipient_name
        )
            p.*
        FROM {PRIME_TABLE} p
        ORDER BY
            award_id_piid,
            modification_number,
            action_date,
            federal_action_obligation,
            recipient_name,
            contract_transaction_unique_key
    """


def dedup_matview_index_ddl() -> str:
    return (
        f"CREATE INDEX IF NOT EXISTS idx_intel_dedup_award_key "
        f"ON {DEDUP_MATVIEW}(contract_award_unique_key)"
    )


def analytics_view_statements(*, include_dedup_matview: bool = False) -> list[str]:
    statements = [
        analytics_schema_ddl(),
        prime_awards_view_ddl(),
        subawards_view_ddl(),
    ]
    if include_dedup_matview:
        statements.extend([dedup_matview_ddl(), dedup_matview_index_ddl()])
    return statements


def ensure_intel_analytics_views(
    settings: Settings,
    *,
    include_dedup_matview: bool = False,
) -> None:
    """Create intel_analytics views (idempotent). Optional dedup matview is slow."""
    dsn = _pg_dsn(settings)
    statements = analytics_view_statements(include_dedup_matview=include_dedup_matview)
    _append_log(settings, "building intel_analytics views...")
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", [PRIME_TABLE])
            if cur.fetchone()[0] is None:
                _append_log(settings, "skip analytics views — prime table missing")
                return
            for stmt in statements:
                try:
                    label = stmt.strip().split("\n", 1)[0][:120]
                    _append_log(settings, f"analytics: {label}")
                    cur.execute(stmt)
                except psycopg.Error as exc:
                    if SUB_TABLE in stmt and "does not exist" in str(exc):
                        _append_log(settings, f"skip sub view — table not loaded yet: {exc}")
                        continue
                    raise

    sp = state_path(settings)
    state = _load_state(sp)
    state["views_built"] = True
    state["views_built_at"] = datetime.now(timezone.utc).isoformat()
    if include_dedup_matview:
        state["dedup_matview_built"] = True
        state["dedup_matview_built_at"] = state["views_built_at"]
    _save_state(sp, state)
    _append_log(settings, "intel_analytics views complete")


def views_built_from_state(state: dict[str, Any]) -> bool:
    return bool(state.get("views_built", False))