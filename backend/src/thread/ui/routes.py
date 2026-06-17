"""HTMX command center routes — server-rendered, Theseus skin."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.models import PacketFieldAnswer
from thread.db.session import get_db
from thread.domain.schemas import OpportunityCreate
from thread.services import opportunities as opp_svc
from thread.services.portfolio import build_portfolio_pulse, signal_opportunity_name
from thread.services.review_gate import ReviewGateError, approve_review, list_pending_reviews
from thread.ui.formatters import format_date, format_money, urgency_label

UI_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.filters["money"] = format_money
templates.env.filters["datefmt"] = format_date
templates.env.filters["urgency"] = urgency_label

router = APIRouter(tags=["ui"])


def _htmx_redirect(url: str) -> Response:
    return Response(status_code=200, headers={"HX-Redirect": url})


@router.get("/", response_class=HTMLResponse)
async def pulse_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    pulse = await build_portfolio_pulse(db, settings)
    return templates.TemplateResponse(
        request,
        "pulse.html",
        {
            "pulse": pulse,
            "app_name": settings.public_app_name,
            "active_nav": "pulse",
            "flash": None,
        },
    )


@router.get("/partials/pulse", response_class=HTMLResponse)
async def pulse_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    pulse = await build_portfolio_pulse(db, settings)
    return templates.TemplateResponse(
        request,
        "partials/pulse_body.html",
        {"pulse": pulse, "flash": None},
    )


@router.post("/opportunities", response_class=HTMLResponse)
async def create_opportunity_form(
    request: Request,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    name = name.strip()
    if not name:
        return _htmx_redirect("/")
    opp = await opp_svc.create_opportunity(db, OpportunityCreate(name=name))
    await db.commit()
    if request.headers.get("HX-Request"):
        return _htmx_redirect(f"/opportunities/{opp.id}")
    return RedirectResponse(url=f"/opportunities/{opp.id}", status_code=303)


@router.post("/signals/track", response_class=HTMLResponse)
async def track_signal_form(
    request: Request,
    award_key: str = Form(...),
    title: str = Form(""),
    agency: str = Form(""),
    naics_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    opp = await opp_svc.create_opportunity(
        db,
        OpportunityCreate(
            name=signal_opportunity_name(title=title, agency=agency),
            award_key=award_key,
            naics_code=naics_code or None,
            entry_reason="intel_signal",
        ),
    )
    await db.commit()
    if request.headers.get("HX-Request"):
        return _htmx_redirect(f"/opportunities/{opp.id}")
    return RedirectResponse(url=f"/opportunities/{opp.id}", status_code=303)


@router.get("/opportunities/{opp_id}", response_class=HTMLResponse)
async def opportunity_workspace(
    request: Request,
    opp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    opp = await opp_svc.get_opportunity(db, opp_id)
    if not opp:
        return HTMLResponse("Opportunity not found", status_code=404)

    answers = (
        await db.execute(select(PacketFieldAnswer).where(PacketFieldAnswer.opportunity_id == opp_id))
    ).scalars().all()
    reviews = await list_pending_reviews(db)
    packet_reviews = [r for r in reviews if r.entity_type == "packet_field_answer"]

    return templates.TemplateResponse(
        request,
        "opportunity.html",
        {
            "opp": opp,
            "fields": answers,
            "reviews": packet_reviews,
            "app_name": settings.public_app_name,
            "active_nav": "pulse",
            "flash": None,
        },
    )


@router.post("/opportunities/{opp_id}/packet/{field_key}", response_class=HTMLResponse)
async def save_packet_field(
    request: Request,
    opp_id: uuid.UUID,
    field_key: str,
    value: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    answer = await opp_svc.update_packet_field(db, opp_id, field_key, value, as_candidate=True)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "partials/packet_field.html",
        {"field": answer, "opp_id": opp_id},
    )


@router.post("/review/{review_id}/approve", response_class=HTMLResponse)
async def approve_review_form(
    request: Request,
    review_id: uuid.UUID,
    opp_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    try:
        await approve_review(db, review_id)
        await db.commit()
    except ReviewGateError as exc:
        await db.rollback()
        reviews = await list_pending_reviews(db)
        return templates.TemplateResponse(
            request,
            "partials/review_queue.html",
            {
                "reviews": [r for r in reviews if r.entity_type == "packet_field_answer"],
                "opp_id": opp_id,
                "flash": str(exc),
            },
        )

    reviews = await list_pending_reviews(db)
    return templates.TemplateResponse(
        request,
        "partials/review_queue.html",
        {
            "reviews": [r for r in reviews if r.entity_type == "packet_field_answer"],
            "opp_id": opp_id,
            "flash": None,
        },
    )