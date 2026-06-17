from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import get_settings
from thread.db.session import get_db
from thread.intel import pg_queries
from thread.intel.migration import get_migration_status

router = APIRouter(prefix="/intel", tags=["intel"])


@router.get("/migration-status")
async def intel_migration_status() -> dict:
    settings = get_settings()
    status = get_migration_status(settings)
    return {
        "source_path": status.source_path,
        "source_exists": status.source_exists,
        "prime_migrated": status.prime_migrated,
        "prime_source_total": status.prime_source_total,
        "prime_pct": round(
            100 * status.prime_migrated / max(status.prime_source_total, 1), 2
        ),
        "sub_migrated": status.sub_migrated,
        "sub_source_total": status.sub_source_total,
        "phase": status.phase,
        "indexes_built": status.indexes_built,
        "complete": status.complete,
        "state_path": status.state_path,
        "log_path": status.log_path,
        "last_updated": status.last_updated,
    }


@router.get("/health")
async def intel_health(db: AsyncSession = Depends(get_db)) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    settings = get_settings()
    source = settings.resolve(settings.intel_migration_source)
    return {
        **stats,
        "migration_source": str(source),
        "migration_source_exists": source.exists(),
        "auto_migrate_on_start": settings.intel_auto_migrate_on_start,
    }


@router.get("/expiring")
async def intel_expiring(
    months_ahead: int = Query(24, ge=1, le=60),
    limit: int = Query(20, ge=1, le=100),
    naics: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    if not stats["prime_awards_ready"] or stats["prime_award_count"] == 0:
        raise HTTPException(
            503,
            "Intel tables empty — run migration: python backend/scripts/migrate_intel_from_duckdb.py",
        )
    codes = [naics or get_settings().default_naics]
    rows = await pg_queries.get_expiring_contracts(db, codes, months_ahead=months_ahead, limit=limit)
    return {"naics_codes": codes, "months_ahead": months_ahead, "contracts": rows}


@router.get("/snapshot")
async def intel_snapshot(
    naics: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    if not stats["prime_awards_ready"] or stats["prime_award_count"] == 0:
        raise HTTPException(503, "Intel tables empty — run migration first")
    code = naics or get_settings().default_naics
    return await pg_queries.get_quick_opportunity_snapshot(db, code)