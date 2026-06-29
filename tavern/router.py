from __future__ import annotations

from pathlib import Path
from typing import List

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from tavern.models import AgentLog, DashboardMetrics, HeroActivity, PwinRecord, Quest

TAVERN_ROOT = Path(__file__).resolve().parent
DASHBOARD_HTML = TAVERN_ROOT / "dashboard" / "tavern-dashboard.html"

router = APIRouter(tags=["Mission Control Tavern"])


async def get_db(request: Request):
    pool: asyncpg.Pool | None = getattr(request.app.state, "tavern_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Tavern database pool not ready")
    async with pool.acquire() as conn:
        yield conn


@router.get("/health")
async def tavern_health() -> dict[str, str]:
    return {"status": "Tavern backend ready", "version": "1.0"}


@router.get("/dashboard", include_in_schema=False)
async def tavern_dashboard() -> FileResponse:
    if not DASHBOARD_HTML.is_file():
        raise HTTPException(status_code=404, detail="Tavern dashboard not found")
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


@router.get("/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM tavern_dashboard_metrics")
    if row is None:
        raise HTTPException(status_code=404, detail="Tavern metrics view unavailable — run tavern schema")
    return DashboardMetrics(**dict(row))


@router.get("/quests", response_model=List[Quest])
async def get_quests(status: str | None = None, db: asyncpg.Connection = Depends(get_db)):
    if status:
        rows = await db.fetch("SELECT * FROM tavern_quests WHERE status = $1", status)
    else:
        rows = await db.fetch("SELECT * FROM tavern_quests")
    return [Quest(**dict(r)) for r in rows]


@router.post("/quests", response_model=Quest)
async def create_quest(quest: Quest, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow(
        """
        INSERT INTO tavern_quests (quest_id, objective, target_hero, status, est_minutes, base_xp, est_pwin_delta)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        quest.quest_id,
        quest.objective,
        quest.target_hero,
        quest.status,
        quest.est_minutes,
        quest.base_xp,
        quest.est_pwin_delta,
    )
    return Quest(**dict(row))


@router.post("/activity", status_code=201)
async def log_hero_activity(activity: HeroActivity, db: asyncpg.Connection = Depends(get_db)):
    await db.execute(
        """
        INSERT INTO tavern_hero_activity (hero, action_type, quest_id, description, xp_gained, pwin_impact)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        activity.hero,
        activity.action_type,
        activity.quest_id,
        activity.description,
        activity.xp_gained,
        activity.pwin_impact,
    )
    return {"status": "logged"}


@router.post("/pwin", status_code=201)
async def record_pwin(record: PwinRecord, db: asyncpg.Connection = Depends(get_db)):
    await db.execute(
        "INSERT INTO tavern_pwin_history (pwin_value, notes) VALUES ($1, $2)",
        record.pwin_value,
        record.notes,
    )
    return {"status": "recorded"}


@router.post("/logs", status_code=201)
async def log_agent_action(log: AgentLog, db: asyncpg.Connection = Depends(get_db)):
    await db.execute(
        """
        INSERT INTO tavern_agent_logs (hero, task, model_used, status, duration_ms, tokens_in, tokens_out)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        log.hero,
        log.task,
        log.model_used,
        log.status,
        log.duration_ms,
        log.tokens_in,
        log.tokens_out,
    )
    return {"status": "logged"}