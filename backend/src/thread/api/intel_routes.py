from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.session import get_db
from thread.domain.schemas import MCPInvokeCreate, MCPInvokeOut, MCPServerOut
from thread.intel import pg_queries
from thread.intel.facet_query import InsightFacetQuery, describe_query
from thread.intel.sql_expressions import EXPIRING_MONTHS_AHEAD
from thread.intel.migration import get_migration_status
from thread.mcp.service import MCPService

router = APIRouter(prefix="/intel", tags=["intel"])


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _facet_query_from_params(
    *,
    naics: str | None,
    agency: str | None,
    sub_agency: str | None,
    recipient: str | None,
    psc: str | None,
) -> InsightFacetQuery:
    return InsightFacetQuery(
        id="api",
        name="API query",
        naics_codes=_parse_csv(naics),
        agency=agency.strip() if agency else None,
        sub_agency=sub_agency.strip() if sub_agency else None,
        recipient=recipient.strip() if recipient else None,
        psc_codes=_parse_csv(psc),
    )


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
        "views_built": status.views_built,
        "complete": status.complete,
        "state_path": status.state_path,
        "log_path": status.log_path,
        "last_updated": status.last_updated,
    }


@router.get("/health")
async def intel_health(db: AsyncSession = Depends(get_db)) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    settings = get_settings()
    from thread.intel.bulk_migration import bulk_prime_dir, bulk_sub_dir

    prime_dir = bulk_prime_dir(settings)
    sub_dir = bulk_sub_dir(settings)
    return {
        **stats,
        "migration_source": f"{prime_dir} + {sub_dir}",
        "migration_source_exists": prime_dir.is_dir() and sub_dir.is_dir(),
        "auto_migrate_on_start": settings.intel_auto_migrate_on_start,
    }


@router.get("/expiring")
async def intel_expiring(
    months_ahead: int = Query(24, ge=1, le=60),
    limit: int = Query(20, ge=1, le=100),
    naics: str | None = Query(None, description="Comma-separated NAICS codes (optional facet)"),
    agency: str | None = Query(None),
    sub_agency: str | None = Query(None),
    recipient: str | None = Query(None, description="Recipient / incumbent name (optional facet)"),
    psc: str | None = Query(None, description="Comma-separated PSC codes (optional facet)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    if not stats["prime_awards_ready"] or stats["prime_award_count"] == 0:
        raise HTTPException(
            503,
            "Intel tables empty — run migration: python backend/scripts/migrate_intel_from_bulk.py",
        )
    query = _facet_query_from_params(
        naics=naics,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        psc=psc,
    )
    if not query.has_filters():
        raise HTTPException(
            400,
            "At least one search facet required (naics, agency, sub_agency, recipient, or psc). "
            "No platform default filter.",
        )
    rows = await pg_queries.get_expiring_contracts_for_query(
        db, query, months_ahead=months_ahead, limit=limit
    )
    return {
        "query": describe_query(query),
        "months_ahead": months_ahead,
        "contracts": rows,
    }


@router.get("/snapshot")
async def intel_snapshot(
    naics: str | None = Query(None),
    agency: str | None = Query(None),
    recipient: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await pg_queries.get_intel_stats(db)
    if not stats["prime_awards_ready"] or stats["prime_award_count"] == 0:
        raise HTTPException(503, "Intel tables empty — run migration first")
    query = _facet_query_from_params(
        naics=naics,
        agency=agency,
        sub_agency=None,
        recipient=recipient,
        psc=None,
    )
    if not query.has_filters():
        raise HTTPException(400, "At least one search facet required. No platform default filter.")
    codes = list(query.naics_codes)
    return {
        "query": describe_query(query),
        "summary": await pg_queries.get_market_summary(db, codes) if codes else {},
        "top_agencies": await pg_queries.get_top_agencies(db, codes, limit=5) if codes else [],
        "expiring_soon": await pg_queries.get_expiring_contracts_for_query(
            db, query, months_ahead=EXPIRING_MONTHS_AHEAD, limit=5
        ),
    }


@router.get("/mcp", response_model=list[MCPServerOut])
async def mcp_catalog(settings: Settings = Depends(get_settings)) -> list[MCPServerOut]:
    service = MCPService(settings)
    return [MCPServerOut(**row) for row in service.list_servers()]


@router.get("/mcp/{server_id}/tools")
async def mcp_tools(server_id: str, settings: Settings = Depends(get_settings)) -> dict:
    service = MCPService(settings)
    try:
        tools = await service.list_tools(server_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"server": server_id, "tools": tools}


@router.post("/mcp/{server_id}/invoke", response_model=MCPInvokeOut)
async def mcp_invoke(
    server_id: str,
    payload: MCPInvokeCreate,
    settings: Settings = Depends(get_settings),
) -> MCPInvokeOut:
    service = MCPService(settings)
    try:
        result = await service.invoke(server_id, payload.tool, payload.arguments)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return MCPInvokeOut(
        server=result["server"],
        tool=result["tool"],
        ok=bool(result.get("ok")),
        output=result.get("output"),
        error=result.get("error"),
    )