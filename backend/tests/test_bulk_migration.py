"""Tests for bulk zip/CSV → PostgreSQL COPY migration helpers."""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import pytest

from thread.intel.bulk_fields import (
    PRIME_TARGET_FIELDS,
    prime_insert_from_staging_sql,
    prime_table_ddl,
    sanitize_sub_column,
)
from thread.intel.bulk_migration import discover_bulk_files, open_bulk_csv


def test_sanitize_sub_column_normalizes_headers():
    assert sanitize_sub_column("prime_awardee_name") == "prime_awardee_name"
    assert sanitize_sub_column("Sub-Award Amount") == "sub_award_amount"


def test_prime_ddl_and_insert_sql_cover_all_target_fields():
    ddl = prime_table_ddl()
    for field in PRIME_TARGET_FIELDS:
        assert field in ddl
    insert_sql = prime_insert_from_staging_sql()
    assert "INSERT INTO intel_usaspending_prime_awards" in insert_sql
    assert "fy" in insert_sql
    assert "quarter" in insert_sql


def test_discover_bulk_files_sorted(tmp_path: Path):
    (tmp_path / "prime_2016-01-03_to_2016-01-04.zip").write_bytes(b"")
    (tmp_path / "prime_2015-10-01_to_2015-10-02.zip").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"skip")
    files = discover_bulk_files(tmp_path)
    assert len(files) == 2
    assert files[0].name.startswith("prime_2015")


def test_open_bulk_csv_reads_zip(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PRIME_TARGET_FIELDS[:3])
        writer.writerow(["k1", "k2", "2024"])

    zip_path = tmp_path / "prime_2016-01-01_to_2016-01-02.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(csv_path, arcname="sample.csv")

    with open_bulk_csv(zip_path) as extracted:
        text = extracted.read_text(encoding="utf-8")
    assert "contract_transaction_unique_key" in text


@pytest.mark.skipif(
    __import__("os").environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="Postgres tests disabled",
)
def test_load_prime_file_inserts_row(settings, tmp_path: Path):
    import psycopg

    from thread.config import Settings
    from thread.intel.bulk_migration import _drop_intel_tables, load_prime_file

    csv_path = tmp_path / "one.csv"
    row = {field: "" for field in PRIME_TARGET_FIELDS}
    row.update(
        {
            "contract_transaction_unique_key": "TEST-TXN-001",
            "contract_award_unique_key": "TEST-AWD-001",
            "action_date_fiscal_year": "2024",
            "action_date": "2024-10-15",
            "federal_action_obligation": "1000.50",
            "naics_code": "541512",
            "recipient_name": "ACME TEST LLC",
        }
    )
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PRIME_TARGET_FIELDS)
        writer.writeheader()
        writer.writerow(row)

    test_settings = Settings(
        thread_state_dir=tmp_path / ".thread",
        intel_bulk_prime_dir=tmp_path,
        intel_bulk_sub_dir=tmp_path / "sub",
    )
    dsn = test_settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")

    try:
        with psycopg.connect(dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                _drop_intel_tables(cur)
                rows_in_file, inserted = load_prime_file(cur, csv_path)
                assert rows_in_file == 1
                assert inserted == 1
                cur.execute(
                    "SELECT recipient_name, fy, quarter FROM intel_usaspending_prime_awards "
                    "WHERE contract_transaction_unique_key = %s",
                    ["TEST-TXN-001"],
                )
                name, fy, quarter = cur.fetchone()
                assert name == "ACME TEST LLC"
                assert fy == 2025
                assert quarter == 1
    except OSError:
        pytest.skip("Postgres unreachable")
    except psycopg.OperationalError:
        pytest.skip("Postgres unreachable")