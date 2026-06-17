"""HTMX command center routes — server-rendered, Theseus skin."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.models import PacketFieldAnswer
from thread.db.session import get_db
from thread.domain.enums import ResearchLens
from thread.domain.schemas import OpportunityCreate
from thread.research.capture_research import run_capture_research
from thread.research.providers import build_provider_registry
from thread.services import opportunities as opp_svc
from thread.services.portfolio import build_portfolio_pulse, signal_opportunity_name
from thread.services.review_gate import ReviewGateError, approve_review
from thread.ui.formatters import format_date, format_money, urgency_label
from thread.ui.settings_health import build_settings_health_context
from thread.ui.tools_context import build_mcp_tools_context, build_skills_tools_context
from thread.ui.workspace import (
    list_research_runs,
    load_actions,
    load_review_queue,
    normalize_tab,
    research_lenses,
)

UI_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.filters["money"] = format_money
templates.env.filters["datefmt"] = format_date
templates.env.filters["urgency"] = urgency_label

router = APIRouter(tags=["ui"])

WORKSPACE_TABS = [
    ("packet", "Packet"),
    ("actions", "Actions"),
    ("review", "Review"),
    ("research", "Research"),
]

SHELL_STUB_PAGES: dict[str, dict[str, str]] = {
    "insights": {
        "page_title": "Data Insights",
        "page_subtitle": "Opportunity identification",
        "product_lane": "Identify",
        "page_description": (
            "Market deep dives over USAspending — agency, competitor, NAICS, PSC, and combos. "
            "Not NAICS-only. Successor to capture-insights exploration."
        ),
        "next_phase": "17",
        "stub_message": "Phase 12a shell only. Phase 17 wires multi-facet queries and saved lenses.",
    },
    "review": {
        "page_title": "Review Queue",
        "page_subtitle": "Trust promotion",
        "product_lane": "All lanes",
        "page_description": (
            "Global queue for candidate outputs — packet edits, research, skills. "
            "Nothing auto-promotes to trusted."
        ),
        "next_phase": "12c",
        "stub_message": "Phase 12c lists pending reviews with human titles and approve actions.",
    },
    "knowledge": {
        "page_title": "Knowledge",
        "page_subtitle": "Capture development",
        "product_lane": "Capture",
        "page_description": (
            "Obsidian vault browser, domain_intel, entities. "
            "MinerU ingest will land parsed docs and wiki drafts here."
        ),
        "next_phase": "15",
        "stub_message": "Phase 15 wires vault browser. Phase 19 adds MinerU document upload.",
    },
    "settings": {
        "page_title": "Settings",
        "page_subtitle": "Platform health",
        "product_lane": "Operate",
        "page_description": (
            "Postgres, intel migration, research providers, vault path, saved insight lenses."
        ),
        "next_phase": "12b",
        "stub_message": "Phase 12b shows read-only health from existing /api/health and intel endpoints.",
    },
}


def _render_stub_page(request: Request, settings: Settings, nav_key: str) -> HTMLResponse:
    meta = SHELL_STUB_PAGES[nav_key]
    return templates.TemplateResponse(
        request,
        "stub_page.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": nav_key,
            **meta,
        },
    )


def _htmx_redirect(url: str) -> Response:
    return Response(status_code=200, headers={"HX-Redirect": url})


async def _panel_context(
    db: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
    *,
    tab: str,
    flash: str | None = None,
) -> dict:
    answers = (
        await db.execute(select(PacketFieldAnswer).where(PacketFieldAnswer.opportunity_id == opp_id))
    ).scalars().all()
    active_tab = normalize_tab(tab)
    ctx: dict = {
        "opp_id": opp_id,
        "fields": answers,
        "active_tab": active_tab,
        "flash": flash,
    }
    if active_tab == "actions":
        ctx["actions"] = await load_actions(db, opp_id)
    elif active_tab == "review":
        ctx["review_items"] = await load_review_queue(db, settings, opp_id)
    elif active_tab == "research":
        ctx["lenses"] = research_lenses()
        ctx["runs"] = list_research_runs(settings, opp_id)
        ctx["providers"] = await build_provider_registry(settings)
    return ctx


def _render_panel(request: Request, ctx: dict) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/workspace_panel.html", ctx)


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return _render_stub_page(request, settings, "insights")


@router.get("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return _render_stub_page(request, settings, "review")


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return _render_stub_page(request, settings, "knowledge")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    health = await build_settings_health_context(db, settings)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "settings",
            "health": health,
        },
    )


@router.get("/tools/mcp", response_class=HTMLResponse)
async def tools_mcp_page(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tools_mcp.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "tools_mcp",
            "mcp": build_mcp_tools_context(settings),
        },
    )


@router.get("/tools/skills", response_class=HTMLResponse)
async def tools_skills_page(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tools_skills.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "tools_skills",
            "skills": build_skills_tools_context(settings),
        },
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    pulse = await build_portfolio_pulse(db, settings)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "pulse": pulse,
            "app_name": settings.public_app_name,
            "active_nav": "dashboard",
            "flash": None,
        },
    )


@router.get("/pulse", response_class=HTMLResponse)
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
        return _htmx_redirect("/pulse")
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
    tab: str = Query("packet"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    opp = await opp_svc.get_opportunity(db, opp_id)
    if not opp:
        return HTMLResponse("Opportunity not found", status_code=404)

    panel = await _panel_context(db, settings, opp_id, tab=tab)
    return templates.TemplateResponse(
        request,
        "opportunity.html",
        {
            "opp": opp,
            "tabs": WORKSPACE_TABS,
            "app_name": settings.public_app_name,
            "active_nav": "",
            "flash": None,
            **panel,
        },
    )


@router.get("/opportunities/{opp_id}/panel", response_class=HTMLResponse)
async def opportunity_panel(
    request: Request,
    opp_id: uuid.UUID,
    tab: str = Query("packet"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not await opp_svc.get_opportunity(db, opp_id):
        return HTMLResponse("Opportunity not found", status_code=404)
    ctx = await _panel_context(db, settings, opp_id, tab=tab)
    return _render_panel(request, ctx)


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


@router.post("/opportunities/{opp_id}/actions", response_class=HTMLResponse)
async def create_action_form(
    request: Request,
    opp_id: uuid.UUID,
    action: str = Form(...),
    owner: str = Form(""),
    due_date: str = Form(""),
    linked_field_keys: str = Form(""),
    tab: str = Form("actions"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    parsed_due: date | None = None
    if due_date.strip():
        parsed_due = date.fromisoformat(due_date.strip())
    keys = [k.strip() for k in linked_field_keys.split(",") if k.strip()]
    await opp_svc.add_action_item(db, opp_id, action.strip(), owner.strip() or None, parsed_due, keys)
    await db.commit()
    ctx = await _panel_context(db, settings, opp_id, tab=tab)
    return _render_panel(request, ctx)


@router.post("/opportunities/{opp_id}/research", response_class=HTMLResponse)
async def run_research_form(
    request: Request,
    opp_id: uuid.UUID,
    lens: str = Form(...),
    query: str = Form(...),
    max_sources: int = Form(5),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not await opp_svc.get_opportunity(db, opp_id):
        return HTMLResponse("Opportunity not found", status_code=404)
    try:
        research_lens = ResearchLens(lens)
    except ValueError:
        return HTMLResponse("Invalid lens", status_code=400)

    result = await run_capture_research(
        settings,
        db,
        lens=research_lens,
        query=query.strip(),
        max_sources=max(1, min(max_sources, 10)),
        opportunity_id=opp_id,
    )
    await db.commit()
    return templates.TemplateResponse(
        request,
        "partials/research_result.html",
        {
            "result": {
                "run_id": result.run_id,
                "status": result.status.value,
                "finding_count": len(result.findings),
                "source_count": len([s for s in result.sources if not s.get("meta")]),
                "interpretation": result.interpretation,
                "errors": result.errors,
            }
        },
    )


@router.post("/review/{review_id}/approve", response_class=HTMLResponse)
async def approve_review_form(
    request: Request,
    review_id: uuid.UUID,
    opp_id: uuid.UUID = Form(...),
    tab: str = Form("review"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    flash: str | None = None
    try:
        await approve_review(db, review_id)
        await db.commit()
    except ReviewGateError as exc:
        await db.rollback()
        flash = str(exc)

    ctx = await _panel_context(db, settings, opp_id, tab=tab, flash=flash)
    return _render_panel(request, ctx)