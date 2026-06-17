from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread import __version__
from thread.config import get_settings
from thread.db.models import ActionMatrixItem, PacketFieldAnswer, PacketFieldDefinition
from thread.db.session import get_db
from thread.domain.enums import MilestoneGate, ReviewState, TrustLevel
from thread.domain.schemas import (
    ActionMatrixItemCreate,
    ActionMatrixItemOut,
    HealthOut,
    OpportunityCreate,
    OpportunityOut,
    PacketFieldAnswerOut,
    PacketView,
    ReviewDecision,
    ReviewRecordOut,
)
from thread.intel import pg_queries as intel_queries
from thread.llm.router import probe_ollama
from thread.services import opportunities as opp_svc
from thread.services.portfolio import build_portfolio_pulse
from thread.services.review_gate import approve_review, list_pending_reviews

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)) -> HealthOut:
    settings = get_settings()
    try:
        await db.execute(select(1))
        postgres_ready = True
    except Exception:
        postgres_ready = False
    intel_row_count = None
    if postgres_ready:
        try:
            stats = await intel_queries.get_intel_stats(db)
            intel_row_count = stats.get("prime_award_count")
        except Exception:
            pass

    ollama_reachable = False
    if postgres_ready:
        try:
            ollama_reachable = await probe_ollama(settings)
        except Exception:
            pass

    return HealthOut(
        status="ok" if postgres_ready else "degraded",
        version=__version__,
        postgres_ready=postgres_ready,
        intel_row_count=intel_row_count,
        grok_configured=bool(settings.xai_api_key),
        ollama_reachable=ollama_reachable,
        vault_healthy=False,
        research_providers={
            "searxng": settings.searxng_base_url,
            "crawl4ai": settings.crawl4ai_base_url,
        },
        langgraph_enabled=settings.langgraph_enabled,
        langgraph_studio_port=settings.langgraph_studio_port,
        langsmith_configured=bool(settings.resolved_langchain_api_key),
        langsmith_tracing=settings.langsmith_tracing or settings.langchain_tracing_v2,
    )


@router.get("/portfolio/pulse")
async def portfolio_pulse(db: AsyncSession = Depends(get_db)) -> dict:
    return await build_portfolio_pulse(db, get_settings())


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(db: AsyncSession = Depends(get_db)) -> list[OpportunityOut]:
    opps = await opp_svc.list_opportunities(db)
    out = []
    for opp in opps:
        pending = await opp_svc.pending_review_count(db, opp.id)
        out.append(
            OpportunityOut(
                id=opp.id,
                name=opp.name,
                slug=opp.slug,
                lifecycle_state=opp.lifecycle_state,
                current_milestone_gate=opp.current_milestone_gate,
                capture_phase_band=opp.capture_phase_band,
                urgency_score=opp.urgency_score,
                freshness_at=opp.freshness_at,
                pending_review_count=pending,
                intel_provenance=opp.intel_provenance,
            )
        )
    return out


@router.post("/opportunities", response_model=OpportunityOut)
async def create_opportunity(payload: OpportunityCreate, db: AsyncSession = Depends(get_db)) -> OpportunityOut:
    opp = await opp_svc.create_opportunity(db, payload)
    await db.commit()
    return OpportunityOut(
        id=opp.id,
        name=opp.name,
        slug=opp.slug,
        lifecycle_state=opp.lifecycle_state,
        current_milestone_gate=opp.current_milestone_gate,
        capture_phase_band=opp.capture_phase_band,
        urgency_score=opp.urgency_score,
        freshness_at=opp.freshness_at,
        intel_provenance=opp.intel_provenance,
    )


@router.get("/opportunities/{opp_id}/packet", response_model=PacketView)
async def get_packet(opp_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PacketView:
    opp = await opp_svc.get_opportunity(db, opp_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    answers = (
        await db.execute(
            select(PacketFieldAnswer).where(PacketFieldAnswer.opportunity_id == opp_id)
        )
    ).scalars().all()
    fields = [
        PacketFieldAnswerOut(
            field_key=a.field_key,
            value=a.value,
            status=a.status,
            trust_level=a.trust_level,
            review_state=a.review_state,
            provenance=a.provenance or [],
        )
        for a in answers
    ]
    return PacketView(
        opportunity_id=opp_id,
        milestone_gate=MilestoneGate(opp.current_milestone_gate),
        fields=fields,
    )


@router.patch("/opportunities/{opp_id}/packet/{field_key}")
async def patch_packet_field(
    opp_id: uuid.UUID,
    field_key: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> PacketFieldAnswerOut:
    value = body.get("value", "")
    answer = await opp_svc.update_packet_field(db, opp_id, field_key, value, as_candidate=True)
    await db.commit()
    return PacketFieldAnswerOut(
        field_key=answer.field_key,
        value=answer.value,
        status=answer.status,
        trust_level=answer.trust_level,
        review_state=answer.review_state,
        provenance=answer.provenance or [],
    )


@router.get("/opportunities/{opp_id}/actions", response_model=list[ActionMatrixItemOut])
async def list_actions(opp_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ActionMatrixItemOut]:
    rows = (
        await db.execute(select(ActionMatrixItem).where(ActionMatrixItem.opportunity_id == opp_id))
    ).scalars().all()
    return [
        ActionMatrixItemOut(
            id=r.id,
            action=r.action,
            owner=r.owner,
            due_date=r.due_date,
            linked_field_keys=r.linked_field_keys or [],
            status=r.status,
        )
        for r in rows
    ]


@router.post("/opportunities/{opp_id}/actions", response_model=ActionMatrixItemOut)
async def create_action(
    opp_id: uuid.UUID,
    payload: ActionMatrixItemCreate,
    db: AsyncSession = Depends(get_db),
) -> ActionMatrixItemOut:
    item = await opp_svc.add_action_item(
        db,
        opp_id,
        payload.action,
        payload.owner,
        payload.due_date,
        payload.linked_field_keys,
    )
    await db.commit()
    return ActionMatrixItemOut(
        id=item.id,
        action=item.action,
        owner=item.owner,
        due_date=item.due_date,
        linked_field_keys=item.linked_field_keys or [],
        status=item.status,
    )


@router.get("/review/pending", response_model=list[ReviewRecordOut])
async def review_pending(db: AsyncSession = Depends(get_db)) -> list[ReviewRecordOut]:
    records = await list_pending_reviews(db)
    return [
        ReviewRecordOut(
            id=r.id,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            trust_level=r.trust_level,
            review_state=r.review_state,
            reviewer_note=r.reviewer_note,
        )
        for r in records
    ]


@router.post("/review/{review_id}/approve", response_model=ReviewRecordOut)
async def review_approve(
    review_id: uuid.UUID,
    body: ReviewDecision,
    db: AsyncSession = Depends(get_db),
) -> ReviewRecordOut:
    try:
        record = await approve_review(
            db, review_id, note=body.note, edited_value=body.edited_value
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return ReviewRecordOut(
        id=record.id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        trust_level=record.trust_level,
        review_state=record.review_state,
        reviewer_note=record.reviewer_note,
    )


@router.get("/packet/definitions")
async def packet_definitions(db: AsyncSession = Depends(get_db)) -> list[dict]:
    await opp_svc.seed_packet_definitions(db)
    await db.commit()
    defs = (await db.execute(select(PacketFieldDefinition))).scalars().all()
    return [
        {
            "key": d.key,
            "label": d.label,
            "question": d.question,
            "section": d.section,
            "route_kind": d.route_kind,
            "reference_slide": d.reference_slide,
            "required_gates": d.required_gates,
        }
        for d in defs
    ]