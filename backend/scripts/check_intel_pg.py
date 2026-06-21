"""Quick intel PG verification."""
from __future__ import annotations

import psycopg

from thread.config import Settings
from thread.intel.bulk_fields import PRIME_TABLE, SUB_TABLE
from thread.intel.bulk_migration import get_migration_status


def main() -> None:
    settings = Settings()
    dsn = settings.database_url.replace("+asyncpg", "").replace("postgresql://", "postgres://")
    status = get_migration_status(settings)
    print("=== migration status ===")
    print(f"complete={status.complete} indexes_built={status.indexes_built} phase={status.phase}")
    print(f"prime_files={status.prime_files_done}/{status.prime_files_total}")
    print(f"sub_files={status.sub_files_done}/{status.sub_files_total}")
    print(f"prime_migrated={status.prime_migrated:,}")
    print(f"sub_migrated={status.sub_migrated:,}")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for table in (PRIME_TABLE, SUB_TABLE):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"PG COUNT {table}: {cur.fetchone()[0]:,}")
            cur.execute(
                """
                SELECT indexname, tablename FROM pg_indexes
                WHERE tablename IN (%s, %s)
                ORDER BY tablename, indexname
                """,
                [PRIME_TABLE, SUB_TABLE],
            )
            rows = cur.fetchall()
            print(f"indexes: {len(rows)}")
            for name, tbl in rows:
                print(f"  {tbl}: {name}")
            cur.execute(f"SELECT * FROM {PRIME_TABLE} LIMIT 1")
            row = cur.fetchone()
            if row:
                cur.execute(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = %s ORDER BY ordinal_position LIMIT 5",
                    [PRIME_TABLE.split('.')[-1]],
                )
                cols = [r[0] for r in cur.fetchall()]
                print("sample prime row (first cols):", dict(zip(cols, row[:5], strict=False)))


if __name__ == "__main__":
    main()