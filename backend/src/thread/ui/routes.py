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

from thread.config import MCP_ENV_CANONICAL, Settings, apply_env_to_process, get_settings, reload_settings
from thread.mcp.service import MCPService
from thread.services.env_file import upsert_env_var
from thread.db.models import PacketFieldAnswer
from thread.db.session import get_db
from thread.domain.enums import ResearchLens
from thread.domain.schemas import OpportunityCreate
from thread.research.capture_research import run_capture_research
from thread.research.providers import build_provider_registry
from thread.services import opportunities as opp_svc
from thread.services.portfolio import build_portfolio_pulse, signal_opportunity_name
from thread.services.platform_health import build_platform_health_widget
from thread.services.insights_display import build_insights_page_context
from thread.services.quick_actions import build_quick_actions
from thread.intel.facet_query import (
    delete_insight_query,
    new_insight_query_from_form,
    save_insight_query,
)
from thread.intel.sam_query import (
    delete_sam_query,
    new_sam_query_from_form,
    save_sam_query,
)
from thread.services.insights_explore import explore_radar, explore_sam
from thread.ui.insights_guides import guide_for_connect_dots, guide_for_explore
from thread.services.insights_drilldown import build_drilldown
from thread.skills.runner import run_skill
from thread.services.vault_research import ensure_watchlist_research_stubs
from thread.services.watchlist import (
    add_watchlist_item,
    load_watchlist,
    new_recompete_watch_item,
    new_sam_watch_item,
    remove_watchlist_item,
)
from thread.services.review_gate import ReviewGateError, approve_review
from thread.ui.formatters import format_date, format_money, urgency_label
from thread.services.pursuits_display import lifecycle_label, milestone_gate_label, phase_band_label
from thread.ui.settings_health import build_settings_health_context
from thread.ui.tools_context import build_mcp_tools_context, build_skills_tools_context
from thread.ui.review_display import build_pending_reviews_widget
from thread.ui.workspace import (
    list_research_runs,
    load_actions,
    load_global_review_queue,
    load_review_queue,
    normalize_tab,
    research_lenses,
)

UI_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.filters["money"] = format_money
templates.env.filters["datefmt"] = format_date
templates.env.filters["urgency"] = urgency_label
templates.env.filters["phase_band_label"] = phase_band_label
templates.env.filters["milestone_label"] = milestone_gate_label
templates.env.filters["lifecycle_label"] = lifecycle_label

router = APIRouter(tags=["ui"])

WORKSPACE_TABS = [
    ("packet", "Packet"),
    ("actions", "Actions"),
    ("review", "Review"),
    ("research", "Research"),
]

SHELL_STUB_PAGES: dict[str, dict[str, str]] = {
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


async def _render_insights_body(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    *,
    flash: str | None = None,
    radar_form: dict | None = None,
    sam_form: dict | None = None,
) -> HTMLResponse:
    ctx = await build_insights_page_context(db, settings)
    explore = await explore_radar(db, settings)
    sam_explore = await explore_sam(settings)
    drilldown = await build_drilldown(db, settings)
    return templates.TemplateResponse(
        request,
        "partials/insights_body.html",
        {
            "ctx": ctx,
            "flash": flash,
            "explore": explore,
            "sam_explore": sam_explore,
            "drilldown": drilldown,
            "radar_form": radar_form,
            "sam_form": sam_form,
            "radar_guide": guide_for_explore("usaspending_explore"),
            "sam_guide": guide_for_explore("sam_explore"),
            "connect_dots_guide": guide_for_connect_dots(),
        },
    )


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = await build_insights_page_context(db, settings)
    explore = await explore_radar(db, settings)
    sam_explore = await explore_sam(settings)
    drilldown = await build_drilldown(db, settings)
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "insights",
            "ctx": ctx,
            "flash": None,
            "explore": explore,
            "sam_explore": sam_explore,
            "drilldown": drilldown,
            "radar_form": None,
            "sam_form": None,
            "radar_guide": guide_for_explore("usaspending_explore"),
            "sam_guide": guide_for_explore("sam_explore"),
            "connect_dots_guide": guide_for_connect_dots(),
        },
    )


@router.get("/partials/insights/radar-explore", response_class=HTMLResponse)
async def insights_radar_explore_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    run: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    explore = await explore_radar(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        run=bool(run),
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_radar_explore.html",
        {"explore": explore},
    )


@router.get("/partials/insights/radar-drilldown", response_class=HTMLResponse)
async def insights_radar_drilldown_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    mode: str = Query("money_flow"),
    run: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    drilldown = await build_drilldown(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        run=bool(run),
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_radar_drilldown.html",
        {"drilldown": drilldown},
    )


@router.post("/insights/radar/analyze", response_class=HTMLResponse)
async def insights_radar_analyze(
    request: Request,
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    mode: str = Form("money_flow"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    payload = {
        "mode": mode,
        "agency": agency.strip() or None,
        "sub_agency": sub_agency.strip() or None,
        "recipient": recipient.strip() or None,
        "naics_codes": naics_codes.strip() or None,
        "psc_codes": psc_codes.strip() or None,
    }
    result = await run_skill(settings, db, "datarepublican_intel", payload)
    drilldown = await build_drilldown(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        run=True,
        review_id=result.review_id,
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_radar_drilldown.html",
        {"drilldown": drilldown},
    )


@router.get("/partials/insights/sam-explore", response_class=HTMLResponse)
async def insights_sam_explore_partial(
    request: Request,
    title: str = Query(""),
    agency_keyword: str = Query(""),
    naics_code: str = Query(""),
    psc_code: str = Query(""),
    notice_type: str = Query(""),
    set_aside: str = Query(""),
    days_back: int = Query(14, ge=1, le=90),
    run: int = Query(0, ge=0, le=1),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    explore = await explore_sam(
        settings,
        title=title,
        agency_keyword=agency_keyword,
        naics_code=naics_code,
        psc_code=psc_code,
        notice_type=notice_type,
        set_aside=set_aside,
        days_back=days_back,
        run=bool(run),
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_sam_explore.html",
        {"explore": explore},
    )


@router.post("/insights/radar/save", response_class=HTMLResponse)
async def insights_save_radar_lens(
    request: Request,
    name: str = Form(...),
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    query = new_insight_query_from_form(
        settings,
        name=name,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        description=description,
    )
    if query is None:
        return await _render_insights_body(
            request,
            db,
            settings,
            flash="Radar lens needs at least one facet (agency, recipient, NAICS, PSC, etc.).",
        )
    save_insight_query(settings, query)
    return await _render_insights_body(
        request,
        db,
        settings,
        flash=f"Saved radar bookmark “{query.name}”.",
    )


@router.post("/insights/radar/{query_id}/delete", response_class=HTMLResponse)
async def insights_delete_radar_lens(
    request: Request,
    query_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not delete_insight_query(settings, query_id):
        return await _render_insights_body(request, db, settings, flash="Radar lens not found.")
    return await _render_insights_body(request, db, settings, flash="Radar lens deleted.")


@router.post("/insights/sam/save", response_class=HTMLResponse)
async def insights_save_sam_lens(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    naics_code: str = Form(""),
    psc_code: str = Form(""),
    agency_keyword: str = Form(""),
    notice_type: str = Form(""),
    set_aside: str = Form(""),
    days_back: int = Form(14),
    limit: int = Form(12),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    query = new_sam_query_from_form(
        settings,
        name=name,
        title=title,
        naics_code=naics_code,
        psc_code=psc_code,
        agency_keyword=agency_keyword,
        notice_type=notice_type,
        set_aside=set_aside,
        days_back=days_back,
        limit=limit,
        description=description,
    )
    if query is None:
        return await _render_insights_body(
            request,
            db,
            settings,
            flash="SAM lens needs at least one search facet (title, agency, NAICS, notice type, etc.).",
        )
    save_sam_query(settings, query)
    return await _render_insights_body(
        request,
        db,
        settings,
        flash=f"Saved SAM bookmark “{query.name}”.",
    )


@router.post("/insights/sam/{query_id}/delete", response_class=HTMLResponse)
async def insights_delete_sam_lens(
    request: Request,
    query_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not delete_sam_query(settings, query_id):
        return await _render_insights_body(request, db, settings, flash="SAM lens not found.")
    return await _render_insights_body(request, db, settings, flash="SAM lens deleted.")


@router.get("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    review_items = await load_global_review_queue(db, settings)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "review",
            "review_items": review_items,
            "pending_count": len(review_items),
            "flash": None,
        },
    )


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
    flash: str | None = Query(None),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tools_mcp.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "tools_mcp",
            "mcp": build_mcp_tools_context(settings),
            "flash": flash,
        },
    )


@router.post("/tools/mcp/{server_id}/test", response_class=HTMLResponse)
async def mcp_test_connection(
    request: Request,
    server_id: str,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    service = MCPService(settings)
    result = await service.test_connection(server_id)
    return templates.TemplateResponse(
        request,
        "partials/mcp_test_result.html",
        {"server_id": server_id, "result": result},
    )


@router.post("/tools/mcp/{server_id}/env", response_class=HTMLResponse)
async def mcp_save_env_keys(
    request: Request,
    server_id: str,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    service = MCPService(settings)
    manifest = service.get_manifest(server_id)
    if not manifest:
        return HTMLResponse("Unknown MCP server", status_code=404)

    form = await request.form()
    env_path = settings.repo_root / ".env"
    saved: list[str] = []
    for key in [*manifest.env_required, *manifest.env_optional]:
        raw = form.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        canonical = MCP_ENV_CANONICAL.get(key, key)
        upsert_env_var(env_path, canonical, value)
        apply_env_to_process(canonical, value)
        saved.append(canonical)

    settings = reload_settings()
    flash = f"Saved {', '.join(saved)} for {server_id}" if saved else f"No keys updated for {server_id}"
    return templates.TemplateResponse(
        request,
        "partials/mcp_tools_body.html",
        {
            "mcp": build_mcp_tools_context(settings),
            "flash": flash,
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
    pending_reviews = await build_pending_reviews_widget(db, settings)
    quick_actions = build_quick_actions(
        opportunities=pulse["opportunities"],
        intel_signals=pulse["intel_signals"],
    )
    platform_health = await build_platform_health_widget(db, settings)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "pulse": pulse,
            "phase_band_widget": pulse["phase_band_widget"],
            "pending_reviews": pending_reviews,
            "quick_actions": quick_actions,
            "platform_health": platform_health,
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


async def _render_pulse_body(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    *,
    flash: str | None = None,
) -> HTMLResponse:
    pulse = await build_portfolio_pulse(db, settings)
    return templates.TemplateResponse(
        request,
        "partials/pulse_body.html",
        {"pulse": pulse, "flash": flash},
    )


@router.get("/partials/pulse", response_class=HTMLResponse)
async def pulse_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return await _render_pulse_body(request, db, settings)


@router.post("/watchlist/add/recompete", response_class=HTMLResponse)
async def watchlist_add_recompete(
    request: Request,
    award_key: str = Form(...),
    title: str = Form(""),
    agency: str = Form(""),
    naics_code: str = Form(""),
    end_date: str = Form(""),
    obligation: str = Form(""),
    months_to_end: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    obl: float | None = None
    if obligation.strip():
        try:
            obl = float(obligation.strip())
        except ValueError:
            obl = None
    months: int | None = None
    if months_to_end.strip():
        try:
            months = int(months_to_end.strip())
        except ValueError:
            months = None
    item = new_recompete_watch_item(
        award_key=award_key,
        title=title,
        agency=agency,
        naics_code=naics_code.strip() or None,
        end_date=end_date.strip() or None,
        obligation=obl,
        months_to_end=months,
    )
    add_watchlist_item(settings, item)
    return await _render_insights_body(
        request,
        db,
        settings,
        flash=f"Watching {item.title} — see Pulse watchlist.",
    )


@router.post("/watchlist/add/sam", response_class=HTMLResponse)
async def watchlist_add_sam(
    request: Request,
    notice_id: str = Form(...),
    title: str = Form(""),
    agency: str = Form(""),
    solicitation_number: str = Form(""),
    notice_type: str = Form(""),
    naics_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    item = new_sam_watch_item(
        notice_id=notice_id,
        title=title,
        agency=agency,
        solicitation_number=solicitation_number.strip() or None,
        notice_type=notice_type.strip() or None,
        naics_code=naics_code.strip() or None,
    )
    add_watchlist_item(settings, item)
    return await _render_insights_body(
        request,
        db,
        settings,
        flash=f"Watching SAM notice — see Pulse watchlist.",
    )


@router.post("/watchlist/{item_id}/remove", response_class=HTMLResponse)
async def watchlist_remove(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not remove_watchlist_item(settings, item_id):
        return await _render_pulse_body(request, db, settings, flash="Watchlist item not found.")
    return await _render_pulse_body(request, db, settings, flash="Removed from watchlist.")


@router.post("/watchlist/{item_id}/research", response_class=HTMLResponse)
async def watchlist_research(
    request: Request,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    item = next((i for i in load_watchlist(settings) if i.id == item_id), None)
    if item is None:
        return await _render_pulse_body(request, db, settings, flash="Watchlist item not found.")
    result = ensure_watchlist_research_stubs(
        settings,
        title=item.title,
        agency=item.agency,
        award_key=item.award_key,
        notice_id=item.notice_id,
    )
    if result.created:
        flash = f"Vault stubs created: {', '.join(result.created)}"
    else:
        flash = "Vault entity notes already exist — open Knowledge to enrich."
    return await _render_pulse_body(request, db, settings, flash=flash)


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


@router.post("/sam/track", response_class=HTMLResponse)
async def track_sam_notice_form(
    request: Request,
    notice_id: str = Form(...),
    title: str = Form(""),
    agency: str = Form(""),
    solicitation_number: str = Form(""),
    notice_type: str = Form(""),
    naics_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    clean_title = (title or "").strip() or f"SAM notice {notice_id[:12]}"
    opp = await opp_svc.create_opportunity(
        db,
        OpportunityCreate(
            name=signal_opportunity_name(title=clean_title, agency=agency),
            sam_notice_id=notice_id.strip(),
            solicitation_number=solicitation_number.strip() or None,
            notice_type=notice_type.strip() or None,
            naics_code=naics_code.strip() or None,
            entry_reason="sam_notice",
        ),
    )
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
    opp_id: str | None = Form(None),
    tab: str = Form("review"),
    return_scope: str = Form("workspace"),
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

    if return_scope == "global":
        review_items = await load_global_review_queue(db, settings)
        return templates.TemplateResponse(
            request,
            "partials/global_review_queue.html",
            {
                "review_items": review_items,
                "flash": flash,
            },
        )

    if return_scope == "pulse_inbox":
        pulse = await build_portfolio_pulse(db, settings)
        return templates.TemplateResponse(
            request,
            "partials/pulse_intel_inbox.html",
            {
                "inbox": pulse["intel_inbox"],
                "flash": flash,
            },
        )

    if not opp_id:
        return HTMLResponse("opp_id required for workspace approve", status_code=400)

    parsed_opp_id = uuid.UUID(opp_id)
    ctx = await _panel_context(db, settings, parsed_opp_id, tab=tab, flash=flash)
    return _render_panel(request, ctx)