from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.session import get_db
from thread.domain.schemas import (
    ResearchProviderOut,
    ResearchRunCreate,
    ResearchRunOut,
)
from thread.research.capture_research import load_run, run_capture_research
from thread.research.providers import build_provider_registry

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/providers", response_model=list[ResearchProviderOut])
async def list_providers(settings: Settings = Depends(get_settings)) -> list[ResearchProviderOut]:
    registry = await build_provider_registry(settings)
    return [
        ResearchProviderOut(
            id=p.id,
            name=p.name,
            role=p.role.value,
            priority=p.priority,
            status=p.status.value,
            detail=p.detail,
        )
        for p in registry
    ]


@router.post("/runs", response_model=ResearchRunOut)
async def create_research_run(
    payload: ResearchRunCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResearchRunOut:
    use_fake = os.environ.get("THREAD_RESEARCH_FAKE", "").lower() in ("1", "true", "yes")
    result = await run_capture_research(
        settings,
        db,
        lens=payload.lens,
        query=payload.query,
        max_sources=payload.max_sources,
        opportunity_id=payload.opportunity_id,
        use_fake=use_fake,
    )
    await db.commit()
    return ResearchRunOut(
        run_id=result.run_id,
        status=result.status.value,
        lens=result.lens,
        query=result.query,
        source_count=len([s for s in result.sources if not s.get("meta")]),
        finding_count=len(result.findings),
        interpretation=result.interpretation,
        review_ids=result.review_ids,
        errors=result.errors,
    )


@router.get("/runs/{run_id}", response_model=dict)
async def get_research_run(
    run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict:
    data = load_run(settings, run_id)
    if data is None:
        raise HTTPException(404, "Research run not found")
    return data