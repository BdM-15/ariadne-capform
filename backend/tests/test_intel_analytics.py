"""Tests for Phase 23a intel_analytics views and extended index DDL."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from thread.config import Settings
from thread.intel.bulk_fields import PRIME_TABLE, SUB_TABLE
from thread.intel.intel_analytics import (
    analytics_view_statements,
    dedup_matview_ddl,
    ensure_intel_analytics_views,
    prime_awards_view_ddl,
    subawards_view_ddl,
)
from thread.intel.sql_expressions import (
    AGENCY_NORMALIZED_EXPR,
    PRIME_AWARDS_VIEW,
    SET_ASIDE_NORMALIZED_EXPR,
    SUBAWARDS_VIEW,
    agency_normalized_expr,
)


def test_agency_normalized_expr_maps_dept_of():
    expr = agency_normalized_expr("parent_award_agency_name")
    assert "DEPT OF" in expr
    assert "DEPARTMENT OF" in expr
    assert "REGEXP_REPLACE" in expr


def test_prime_view_ddl_exposes_semantics_columns():
    ddl = prime_awards_view_ddl()
    for col in (
        "agency_normalized",
        "agency_raw",
        "is_deobligation",
        "is_zero_obligation",
        "is_positive_obligation",
        "obligation_kind",
        "extent_competed_normalized",
        "set_aside_normalized",
        "set_aside_chart_bucket",
    ):
        assert col in ddl
    assert PRIME_TABLE in ddl
    assert PRIME_AWARDS_VIEW in ddl


def test_sub_view_ddl_coalesces_null_prime():
    ddl = subawards_view_ddl()
    assert "(Unknown Prime)" in ddl
    assert SUBAWARDS_VIEW in ddl
    assert SUB_TABLE in ddl


def test_analytics_statements_idempotent_shape():
    stmts = analytics_view_statements()
    assert len(stmts) == 3
    assert "CREATE SCHEMA IF NOT EXISTS" in stmts[0]
    assert "CREATE OR REPLACE VIEW" in stmts[1]
    assert "CREATE OR REPLACE VIEW" in stmts[2]

    with_dedup = analytics_view_statements(include_dedup_matview=True)
    assert len(with_dedup) == 5
    assert "MATERIALIZED VIEW" in dedup_matview_ddl()


def test_agency_normalized_expr_uses_agency_coalesce():
    assert "parent_award_agency_name" in AGENCY_NORMALIZED_EXPR
    assert "DEPARTMENT OF" in AGENCY_NORMALIZED_EXPR


def test_set_aside_normalized_expr_matches_data_insights_rules():
    assert "NO SET ASIDE USED." in SET_ASIDE_NORMALIZED_EXPR
    assert "FULL AND OPEN COMPETITION" in SET_ASIDE_NORMALIZED_EXPR
    assert "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES" in SET_ASIDE_NORMALIZED_EXPR


def _pg_reachable(settings: Settings) -> bool:
    try:
        import psycopg

        dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="Postgres tests disabled",
)
def test_ensure_intel_analytics_views_idempotent(settings):
    if not _pg_reachable(settings):
        pytest.skip("Postgres unreachable")

    import psycopg

    from thread.intel.bulk_migration import _pg_table_count

    dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            if _pg_table_count(cur, PRIME_TABLE) < 1:
                pytest.skip("Prime table empty — need migrated intel data")

    state_dir = settings.resolve(settings.thread_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    ensure_intel_analytics_views(settings)
    ensure_intel_analytics_views(settings)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agency_normalized, obligation_kind "
                f"FROM {PRIME_AWARDS_VIEW} "
                "WHERE parent_award_agency_name = 'DEPT OF DEFENSE' "
                "LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None:
                assert row[0] == "DEPARTMENT OF DEFENSE"
                assert row[1] in ("obligation", "deobligation", "zero", "unknown")