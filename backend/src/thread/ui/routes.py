"""HTMX command center routes — server-rendered, Theseus skin."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import MCP_ENV_CANONICAL, Settings, apply_env_to_process, get_settings, reload_settings
from thread.mcp.service import MCPService
from thread.services.env_file import upsert_env_var
from thread.db.models import PacketFieldAnswer, ReviewRecord
from thread.db.session import get_db
from thread.domain.enums import ResearchLens
from thread.domain.enums import LifecycleState
from thread.domain.schemas import OpportunityCreate
from thread.research.capture_research import run_capture_research
from thread.research.providers import build_provider_registry
from thread.services import opportunities as opp_svc
from thread.domain.packet_answer_sources import GROK, PG_INTEL, SAM_MCP, USASPENDING_MCP
from thread.services.packet_route_fill import apply_route_fill, run_packet_route_fill
from thread.services.packet_workspace import build_packet_workspace, enrich_packet_field_card
from thread.services.capture_display import build_capture_home
from thread.services.capture_intent import CaptureIntent, classify_capture_intent
from thread.services.capture_fab import (
    format_document_status_note,
    CaptureFabError,
    build_capture_context,
    ingest_quick_capture,
    parse_opp_id,
)
from thread.services.idea_capturer import IdeaCaptureError, capture_idea_to_vault
from thread.services.portfolio import build_portfolio_pulse, signal_opportunity_name
from thread.services.platform_health import build_platform_health_widget
from thread.services.insights_display import build_insights_page_context
from thread.services import opportunities as opp_svc
from thread.services.operator_tasks import (
    append_task_note,
    build_open_tasks_widget,
    complete_operator_task,
    count_open_tasks,
    get_task_detail,
    get_task_list_item,
    ingest_fab_task,
    link_task_to_opportunity,
    list_operator_tasks,
    toggle_checklist_item,
    update_operator_task_status,
)
from thread.services.task_display import build_tasks_page_context, task_actions_for
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
from thread.clew.path_link import clew_path_href
from thread.clew.saved_traces import (
    clew_trace_href,
    delete_clew_trace,
    describe_trace,
    load_clew_traces,
    new_clew_trace_from_form,
    save_clew_trace,
)
from thread.ui.insights_guides import guide_for_clew, guide_for_data_insights, guide_for_explore
from thread.services.insights_drilldown import build_drilldown
from thread.services.insights_slice import build_slice_panel
from thread.intel.operator_profile import save_naics_portfolio_from_text
from thread.skills.runner import run_skill
from thread.services.knowledge_browser import (
    build_vault_browser_context,
    child_dir_href,
    child_file_href,
    vault_href,
)
from thread.services.education_studio import (
    EducationStudioError,
    EducationStudioWidget,
    education_vault_review_href,
    explain_education_topic,
    queue_education_lesson_draft,
    save_education_studio_snapshot,
)
from thread.services.operator_learning import (
    build_education_page_context,
    education_href,
    set_lesson_completed,
)
from thread.services.vault_research import ensure_watchlist_research_stubs
from thread.services.watchlist import (
    add_watchlist_item,
    load_watchlist,
    new_recompete_watch_item,
    new_sam_watch_item,
    remove_watchlist_item,
)
from thread.services.review_gate import ReviewGateError, approve_review, reject_review
from thread.services.vault_candidate_enrich import CandidateEnrichError, enrich_candidate_note
from thread.services.vault_candidate_polish import (
    CandidatePolishError,
    apply_polished_candidate,
    build_polish_diff,
    polish_candidate_note,
    rules_polish_candidate,
)
from thread.services.vault_dedup import patch_provenance_target, validate_promote_target
from thread.services.vault_review_queue import (
    build_stale_vault_review_widget,
    build_vault_review_widget,
    load_candidate_edit_form,
    reject_vault_candidate,
)
from thread.services.vault_ops import run_vault_op
from thread.services.system_restart import schedule_restart
from thread.services.vault_write import (
    VaultWriteError,
    ingest_approved_review,
    queue_vault_candidate_review,
    save_candidate_note,
    write_candidate_note,
)
from thread.ui.formatters import format_date, format_money, urgency_label
from thread.services.pursuits_display import lifecycle_label, milestone_gate_label, phase_band_label
from thread.ui.knowledge_guides import guide_for_knowledge, guide_for_vault_ops
from thread.ui.tasks_guides import guide_for_tasks
from thread.ui.settings_health import build_settings_health_context
from thread.ui.skill_forms import CLEW_MODES, payload_from_form, skill_is_wired
from thread.ui.tools_context import build_mcp_tools_context, build_skills_tools_context
from thread.ui.review_display import build_pending_reviews_widget
from thread.ui.workspace import (
    legacy_tab_redirect,
    load_actions,
    load_global_review_queue,
    normalize_tab,
)

UI_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.filters["money"] = format_money
templates.env.filters["datefmt"] = format_date
templates.env.filters["urgency"] = urgency_label
templates.env.filters["phase_band_label"] = phase_band_label
templates.env.filters["milestone_label"] = milestone_gate_label
templates.env.globals["vault_href"] = vault_href
templates.env.globals["child_dir_href"] = child_dir_href
templates.env.globals["child_file_href"] = child_file_href
templates.env.filters["lifecycle_label"] = lifecycle_label


def capture_workspace_href(
    opp_id: uuid.UUID | str,
    *,
    tab: str | None = None,
    slide: str | None = None,
) -> str:
    base = f"/capture/{opp_id}"
    params: list[str] = []
    if tab and tab != "packet":
        params.append(f"tab={tab}")
    if slide:
        params.append(f"slide={slide}")
    return f"{base}?{'&'.join(params)}" if params else base


templates.env.globals["capture_href"] = capture_workspace_href
templates.env.globals["task_actions"] = task_actions_for
templates.env.globals["clew_path_href"] = clew_path_href
templates.env.globals["education_href"] = education_href


def _static_asset_version() -> str:
    from thread.config import get_settings

    return get_settings().app_version.replace(" ", "-")


templates.env.globals["asset_v"] = _static_asset_version

router = APIRouter(tags=["ui"])


async def _task_drawer_context(
    db: AsyncSession,
    task_id: uuid.UUID,
    *,
    filter_key: str,
    view_mode: str,
    note_flash: str | None = None,
    opp_flash: str | None = None,
    checklist_flash: str | None = None,
):
    detail = await get_task_detail(db, task_id)
    if detail is None:
        return None
    pursuits = await opp_svc.list_opportunities(db)
    return {
        "task": detail,
        "actions": task_actions_for(detail.status),
        "filter_key": filter_key,
        "view_mode": view_mode,
        "pursuits": pursuits,
        "note_flash": note_flash,
        "opp_flash": opp_flash,
        "checklist_flash": checklist_flash,
    }


async def _tasks_page_context(
    db: AsyncSession,
    *,
    filter_key: str,
    view_mode: str,
):
    items = await list_operator_tasks(db, filter_key=filter_key)
    open_count = await count_open_tasks(db)
    return build_tasks_page_context(
        items,
        filter_key=filter_key,
        view_mode=view_mode,
        open_count=open_count,
    )

SHELL_STUB_PAGES: dict[str, dict[str, str]] = {
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
    slide: str | None = None,
) -> dict:
    opp = await opp_svc.get_opportunity(db, opp_id)
    resolved_slide = slide
    if tab == "actions" and not resolved_slide:
        resolved_slide = "slide_14_actions"
    packet = await build_packet_workspace(
        db,
        opp_id,
        active_slide=resolved_slide,
        milestone_gate=opp.current_milestone_gate if opp else None,
    )
    return {
        "opp_id": opp_id,
        "active_tab": "packet",
        "flash": flash,
        "packet": packet,
        "fields": packet["fields"],
        "actions": await load_actions(db, opp_id),
        "expand_action_drawer": tab == "actions" or resolved_slide == "slide_14_actions",
    }


def _render_panel(request: Request, ctx: dict) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/workspace_panel.html", ctx)


async def _render_insights_body(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    *,
    flash: str | None = None,
    facet_form: dict | None = None,
    active_lens: str = "overview",
    slice_panel: bool = False,
    slice_ctx: dict | None = None,
) -> HTMLResponse:
    ctx = await build_insights_page_context(db, settings)
    from thread.services.insights_slice import INSIGHTS_LENS_TABS

    template_ctx: dict = {
        "ctx": ctx,
        "flash": flash,
        "facet_form": facet_form or {},
        "active_lens": active_lens,
        "slice_panel": slice_panel,
        "has_slice": slice_panel,
        "lens_tabs": INSIGHTS_LENS_TABS,
        "insights_guide": guide_for_data_insights(),
        "radar_guide": guide_for_explore("usaspending_explore"),
        "sam_guide": guide_for_explore("sam_explore"),
        "clew_guide": guide_for_clew(),
    }
    if slice_ctx:
        template_ctx.update(slice_ctx)
    return templates.TemplateResponse(
        request,
        "partials/insights_body.html",
        template_ctx,
    )


def _slice_template_ctx(
    panel,
    *,
    slice_flash: str | None = None,
    htmx_request: bool = False,
) -> dict:
    return {
        "facet_form": panel.facet_form,
        "active_lens": panel.active_lens,
        "lens_tabs": panel.lens_tabs,
        "htmx_request": htmx_request,
        "query": panel.query,
        "has_slice": panel.has_slice,
        "overview": panel.overview,
        "overview_ready": panel.overview_ready,
        "overview_idle": panel.overview_idle,
        "overview_error": panel.overview_error,
        "overview_verdict": panel.overview_verdict,
        "explore": panel.explore,
        "sam_explore": panel.sam_explore,
        "sam_form": panel.sam_form,
        "entity": panel.entity,
        "entity_profile": panel.entity_profile,
        "entity_ready": panel.entity_ready,
        "entity_idle": panel.entity_idle,
        "entity_error": panel.entity_error,
        "cache_hit": panel.cache_hit,
        "cache_age_seconds": panel.cache_age_seconds,
        "slice_flash": slice_flash,
        "slice_panel": True,
        "slice_explain": panel.slice_explain,
    }


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    from thread.services.insights_slice import INSIGHTS_LENS_TABS

    ctx = await build_insights_page_context(db, settings)
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "insights",
            "ctx": ctx,
            "flash": None,
            "facet_form": {},
            "active_lens": "overview",
            "slice_panel": False,
            "has_slice": False,
            "lens_tabs": INSIGHTS_LENS_TABS,
            "insights_guide": guide_for_data_insights(),
            "radar_guide": guide_for_explore("usaspending_explore"),
            "sam_guide": guide_for_explore("sam_explore"),
            "clew_guide": guide_for_clew(),
        },
    )


@router.get("/partials/insights/slice", response_class=HTMLResponse)
async def insights_slice_partial(
    request: Request,
    lens: str = Query("overview"),
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    awarding_office: str = Query(""),
    funding_office: str = Query(""),
    recipient_uei: str = Query(""),
    pop_state: str = Query(""),
    extent_competed: str = Query(""),
    type_of_set_aside: str = Query(""),
    min_contract_value: str = Query(""),
    min_value_basis: str = Query("potential"),
    exclude_agencies: str = Query(""),
    run: int = Query(0, ge=0, le=1),
    entity_kind: str = Query(""),
    entity_value: str = Query(""),
    entity_scope: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    panel = await build_slice_panel(
        db,
        settings,
        lens=lens,
        run=bool(run),
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
        **_advanced_facet_kwargs(
            agency=agency,
            sub_agency=sub_agency,
            recipient=recipient,
            naics_codes=naics_codes,
            psc_codes=psc_codes,
            awarding_office=awarding_office,
            funding_office=funding_office,
            recipient_uei=recipient_uei,
            pop_state=pop_state,
            extent_competed=extent_competed,
            type_of_set_aside=type_of_set_aside,
            min_contract_value=min_contract_value,
            min_value_basis=min_value_basis,
            exclude_agencies=exclude_agencies,
        ),
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_stage_content.html",
        _slice_template_ctx(panel, htmx_request=bool(request.headers.get("HX-Request"))),
    )


@router.post("/partials/insights/explain-slice", response_class=HTMLResponse)
async def insights_explain_slice_partial(
    request: Request,
    lens: str = Form("overview"),
    llm_provider: str = Form("cloud"),
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    awarding_office: str = Form(""),
    funding_office: str = Form(""),
    recipient_uei: str = Form(""),
    pop_state: str = Form(""),
    extent_competed: str = Form(""),
    type_of_set_aside: str = Form(""),
    min_contract_value: str = Form(""),
    min_value_basis: str = Form("potential"),
    exclude_agencies: str = Form(""),
    run: int = Form(1),
    entity_kind: str = Form(""),
    entity_value: str = Form(""),
    entity_scope: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    from thread.services.insights_slice_explain import (
        SliceExplainError,
        build_slice_explain_bundle,
        explain_slice,
    )

    panel = await build_slice_panel(
        db,
        settings,
        lens=lens or "overview",
        run=bool(run),
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
        **_advanced_facet_kwargs(
            agency=agency,
            sub_agency=sub_agency,
            recipient=recipient,
            naics_codes=naics_codes,
            psc_codes=psc_codes,
            awarding_office=awarding_office,
            funding_office=funding_office,
            recipient_uei=recipient_uei,
            pop_state=pop_state,
            extent_competed=extent_competed,
            type_of_set_aside=type_of_set_aside,
            min_contract_value=min_contract_value,
            min_value_basis=min_value_basis,
            exclude_agencies=exclude_agencies,
        ),
    )
    ctx: dict = {
        "slice_explain_text": None,
        "slice_explain_error": None,
        "slice_explain_provider": None,
        "slice_explain_model": None,
    }
    if not panel.has_slice or not panel.overview_ready:
        ctx["slice_explain_error"] = "Run a slice first — Explain needs Overview data."
    else:
        bundle = build_slice_explain_bundle(
            query=panel.query,
            overview_verdict=panel.overview_verdict,
            overview=panel.overview,
            expiring_rows=panel.explore.rows,
        )
        try:
            result = await explain_slice(settings, bundle=bundle, provider_choice=llm_provider)
            ctx["slice_explain_text"] = result.text
            ctx["slice_explain_provider"] = result.provider
            ctx["slice_explain_model"] = result.model
        except SliceExplainError as exc:
            ctx["slice_explain_error"] = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/insights_slice_explain_panel.html",
        ctx,
    )


@router.get("/api/insights/graph-expand")
async def insights_graph_expand(
    node_id: str = Query(""),
    batch: int = Query(3, ge=1, le=12),
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    awarding_office: str = Query(""),
    funding_office: str = Query(""),
    recipient_uei: str = Query(""),
    pop_state: str = Query(""),
    extent_competed: str = Query(""),
    type_of_set_aside: str = Query(""),
    min_contract_value: str = Query(""),
    min_value_basis: str = Query("potential"),
    exclude_agencies: str = Query(""),
    entity_value: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from thread.intel.graph_trace import expand_node_neighbors
    from thread.services.insights_explore import _facet_from_params

    nid = node_id.strip()
    if not nid:
        return JSONResponse({"error": "node_id required"}, status_code=400)
    query = _facet_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        exclude_agencies=exclude_agencies,
    )
    if query is None or not query.has_filters():
        return JSONResponse({"error": "Active facet slice required"}, status_code=400)
    seed = (entity_value or recipient or "").strip() or None
    expansion = await expand_node_neighbors(
        db, query, nid, batch=batch, seed_prime=seed
    )
    return JSONResponse({"expansion": expansion})


@router.get("/partials/insights/award", response_class=HTMLResponse)
async def insights_award_partial(
    request: Request,
    award_key: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    from thread.intel.pg_queries import get_award_profile

    key = award_key.strip()
    award = None
    award_error: str | None = None
    if not key:
        award_error = "Missing award key — re-run slice to refresh expiring rows."
    else:
        try:
            award = await get_award_profile(db, key)
        except Exception as exc:  # pragma: no cover — surfaced in drawer
            award_error = f"Database error loading award: {exc}"
        if award is None and award_error is None:
            award_error = f"Award not found for key {key[:48]}…"
    return templates.TemplateResponse(
        request,
        "partials/insights_award_panel.html",
        {
            "award": award,
            "award_error": award_error,
        },
    )


@router.post("/insights/operator-naics", response_class=HTMLResponse)
async def insights_save_operator_naics(
    request: Request,
    naics_portfolio: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    save_naics_portfolio_from_text(settings, naics_portfolio)
    return await _render_insights_body(
        request,
        db,
        settings,
        flash="Operator NAICS portfolio saved.",
    )


@router.get("/partials/insights/radar-explore", response_class=HTMLResponse)
async def insights_radar_explore_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    awarding_office: str = Query(""),
    funding_office: str = Query(""),
    recipient_uei: str = Query(""),
    pop_state: str = Query(""),
    extent_competed: str = Query(""),
    type_of_set_aside: str = Query(""),
    min_contract_value: str = Query(""),
    min_value_basis: str = Query("potential"),
    exclude_agencies: str = Query(""),
    run: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    explore = await explore_radar(
        db,
        settings,
        run=bool(run),
        **_advanced_facet_kwargs(
            agency=agency,
            sub_agency=sub_agency,
            recipient=recipient,
            naics_codes=naics_codes,
            psc_codes=psc_codes,
            awarding_office=awarding_office,
            funding_office=funding_office,
            recipient_uei=recipient_uei,
            pop_state=pop_state,
            extent_competed=extent_competed,
            type_of_set_aside=type_of_set_aside,
            min_contract_value=min_contract_value,
            min_value_basis=min_value_basis,
            exclude_agencies=exclude_agencies,
        ),
    )
    return templates.TemplateResponse(
        request,
        "partials/insights_radar_explore.html",
        {"explore": explore},
    )


def _advanced_facet_kwargs(
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    min_contract_value: str = "",
    min_value_basis: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
    exclude_agencies: str = "",
) -> dict[str, str]:
    return {
        "agency": agency,
        "sub_agency": sub_agency,
        "recipient": recipient,
        "naics_codes": naics_codes,
        "psc_codes": psc_codes,
        "min_contract_value": min_contract_value,
        "min_value_basis": min_value_basis,
        "awarding_office": awarding_office,
        "funding_office": funding_office,
        "recipient_uei": recipient_uei,
        "pop_state": pop_state,
        "extent_competed": extent_competed,
        "type_of_set_aside": type_of_set_aside,
        "exclude_agencies": exclude_agencies,
    }


def _clew_facet_form(**kwargs: str) -> dict[str, str]:
    return _advanced_facet_kwargs(**kwargs)


@router.get("/partials/clew/drawer", response_class=HTMLResponse)
async def clew_drawer_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    awarding_office: str = Query(""),
    funding_office: str = Query(""),
    recipient_uei: str = Query(""),
    pop_state: str = Query(""),
    extent_competed: str = Query(""),
    type_of_set_aside: str = Query(""),
    min_contract_value: str = Query(""),
    min_value_basis: str = Query("potential"),
    exclude_agencies: str = Query(""),
    mode: str = Query("money_flow"),
    run: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    facets = _advanced_facet_kwargs(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        exclude_agencies=exclude_agencies,
    )
    drilldown = await build_drilldown(db, settings, mode=mode, run=bool(run), **facets)
    return templates.TemplateResponse(
        request,
        "partials/clew_drawer_panel.html",
        {
            "drilldown": drilldown,
            "facet_form": _clew_facet_form(**facets),
            "clew_guide": guide_for_clew(),
        },
    )


@router.post("/partials/clew/queue-review", response_class=HTMLResponse)
async def clew_queue_review(
    request: Request,
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    awarding_office: str = Form(""),
    funding_office: str = Form(""),
    recipient_uei: str = Form(""),
    pop_state: str = Form(""),
    extent_competed: str = Form(""),
    type_of_set_aside: str = Form(""),
    min_contract_value: str = Form(""),
    min_value_basis: str = Form("potential"),
    exclude_agencies: str = Form(""),
    mode: str = Form("money_flow"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    facets = _advanced_facet_kwargs(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        exclude_agencies=exclude_agencies,
    )
    payload = {"mode": mode, **{k: (v.strip() or None) for k, v in facets.items()}}
    result = await run_skill(settings, db, "clew_intel", payload)
    drilldown = await build_drilldown(
        db,
        settings,
        mode=mode,
        run=True,
        review_id=result.review_id,
        **facets,
    )
    return templates.TemplateResponse(
        request,
        "partials/clew_drawer_panel.html",
        {
            "drilldown": drilldown,
            "facet_form": _clew_facet_form(**facets),
            "clew_guide": guide_for_clew(),
        },
    )


@router.get("/partials/insights/radar-drilldown", response_class=HTMLResponse)
async def insights_radar_drilldown_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    awarding_office: str = Query(""),
    funding_office: str = Query(""),
    recipient_uei: str = Query(""),
    pop_state: str = Query(""),
    extent_competed: str = Query(""),
    type_of_set_aside: str = Query(""),
    min_contract_value: str = Query(""),
    min_value_basis: str = Query("potential"),
    exclude_agencies: str = Query(""),
    mode: str = Query("money_flow"),
    run: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    drilldown = await build_drilldown(
        db,
        settings,
        mode=mode,
        run=bool(run),
        **_advanced_facet_kwargs(
            agency=agency,
            sub_agency=sub_agency,
            recipient=recipient,
            naics_codes=naics_codes,
            psc_codes=psc_codes,
            awarding_office=awarding_office,
            funding_office=funding_office,
            recipient_uei=recipient_uei,
            pop_state=pop_state,
            extent_competed=extent_competed,
            type_of_set_aside=type_of_set_aside,
            min_contract_value=min_contract_value,
            min_value_basis=min_value_basis,
            exclude_agencies=exclude_agencies,
        ),
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
    awarding_office: str = Form(""),
    funding_office: str = Form(""),
    recipient_uei: str = Form(""),
    pop_state: str = Form(""),
    extent_competed: str = Form(""),
    type_of_set_aside: str = Form(""),
    min_contract_value: str = Form(""),
    min_value_basis: str = Form("potential"),
    exclude_agencies: str = Form(""),
    mode: str = Form("money_flow"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    facets = _advanced_facet_kwargs(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        exclude_agencies=exclude_agencies,
    )
    payload = {"mode": mode, **{k: (v.strip() or None) for k, v in facets.items()}}
    result = await run_skill(settings, db, "clew_intel", payload)
    drilldown = await build_drilldown(
        db,
        settings,
        mode=mode,
        run=True,
        review_id=result.review_id,
        **facets,
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
    awarding_office: str = Form(""),
    funding_office: str = Form(""),
    recipient_uei: str = Form(""),
    pop_state: str = Form(""),
    extent_competed: str = Form(""),
    type_of_set_aside: str = Form(""),
    min_contract_value: str = Form(""),
    min_value_basis: str = Form("potential"),
    exclude_agencies: str = Form(""),
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
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        exclude_agencies=exclude_agencies,
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


def _knowledge_template_context(
    settings: Settings,
    *,
    path: str = "",
    page: str = "",
    inbox: str = "",
) -> dict:
    vault = build_vault_browser_context(settings, path=path, page=page)
    return {
        "app_name": settings.public_app_name,
        "active_nav": "knowledge",
        "vault": vault,
        "knowledge_guide": guide_for_knowledge(),
        "vault_ops_guide": guide_for_vault_ops(),
        "inbox_highlight": inbox.strip(),
    }


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(
    request: Request,
    path: str = Query(""),
    page: str = Query(""),
    inbox: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "knowledge.html",
        _knowledge_template_context(settings, path=path, page=page, inbox=inbox),
    )


@router.get("/partials/knowledge/tree", response_class=HTMLResponse)
async def knowledge_tree_partial(
    request: Request,
    path: str = Query(""),
    page: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = _knowledge_template_context(settings, path=path, page=page)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_tree_panel.html",
        ctx,
    )


@router.get("/partials/knowledge/page", response_class=HTMLResponse)
async def knowledge_page_partial(
    request: Request,
    path: str = Query(""),
    page: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = _knowledge_template_context(settings, path=path, page=page)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_page_htmx.html",
        ctx,
    )


def _education_template_context(
    settings: Settings,
    *,
    lesson: str = "",
    studio: EducationStudioWidget | None = None,
) -> dict:
    edu = build_education_page_context(settings, lesson=lesson)
    return {
        "app_name": settings.public_app_name,
        "active_nav": "education",
        "edu": edu,
        "studio": studio or EducationStudioWidget.idle(settings),
    }


@router.get("/education", response_class=HTMLResponse)
async def education_page(
    request: Request,
    lesson: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "education.html",
        _education_template_context(settings, lesson=lesson),
    )


@router.get("/partials/education/panel", response_class=HTMLResponse)
async def education_panel_partial(
    request: Request,
    lesson: str = Query(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/education_panel_htmx.html",
        _education_template_context(settings, lesson=lesson),
    )


@router.post("/partials/education/lesson/{lesson_id}/complete", response_class=HTMLResponse)
async def education_lesson_complete(
    request: Request,
    lesson_id: str,
    completed: str = Form(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    raw = completed.strip().lower()
    target: bool | None
    if raw in ("true", "1", "yes"):
        target = True
    elif raw in ("false", "0", "no"):
        target = False
    else:
        target = None
    set_lesson_completed(settings, lesson_id, completed=target)
    return templates.TemplateResponse(
        request,
        "partials/education_panel_htmx.html",
        _education_template_context(settings, lesson=lesson_id),
    )


@router.post("/partials/education/studio/ask", response_class=HTMLResponse)
async def education_studio_ask(
    request: Request,
    suggestion: str = Form(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    clean = suggestion.strip()
    try:
        result = await explain_education_topic(settings, suggestion=clean)
        studio = EducationStudioWidget(
            grok_configured=bool(settings.xai_api_key),
            reasoning_model=settings.reasoning_llm_model,
            suggestion=clean,
            response=result.text,
            response_kind="explain",
            provider=result.provider,
            model_used=result.model,
        )
        save_education_studio_snapshot(settings, studio)
    except EducationStudioError as exc:
        studio = EducationStudioWidget(
            grok_configured=bool(settings.xai_api_key),
            reasoning_model=settings.reasoning_llm_model,
            suggestion=clean,
            error=str(exc),
            flash_ok=False,
        )
    return templates.TemplateResponse(
        request,
        "partials/education_studio.html",
        _education_template_context(settings, studio=studio),
    )


@router.post("/partials/education/studio/draft", response_class=HTMLResponse)
async def education_studio_draft(
    request: Request,
    suggestion: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    clean = suggestion.strip()
    try:
        result = await queue_education_lesson_draft(settings, db, suggestion=clean)
        await db.commit()
        studio = EducationStudioWidget(
            grok_configured=bool(settings.xai_api_key),
            reasoning_model=settings.reasoning_llm_model,
            suggestion=clean,
            response=result.body,
            response_kind="draft",
            provider=result.provider,
            model_used=result.model,
            draft_title=result.title,
            draft_target=result.target_rel,
            review_id=str(result.review_id),
            review_href=education_vault_review_href(result.review_id),
            flash=f"Lesson draft queued — approve on Knowledge → Vault Inbox to publish as {result.target_rel}",
            flash_ok=True,
        )
        save_education_studio_snapshot(settings, studio)
    except EducationStudioError as exc:
        studio = EducationStudioWidget(
            grok_configured=bool(settings.xai_api_key),
            reasoning_model=settings.reasoning_llm_model,
            suggestion=clean,
            error=str(exc),
            flash=str(exc),
            flash_ok=False,
        )
    return templates.TemplateResponse(
        request,
        "partials/education_studio.html",
        _education_template_context(settings, studio=studio),
    )


def _parse_inbox_review_id(raw: str | None) -> uuid.UUID | None:
    clean = (raw or "").strip()
    if not clean:
        return None
    try:
        return uuid.UUID(clean)
    except ValueError:
        return None


async def _capture_studio_template_context(
    db: AsyncSession,
    settings: Settings,
    *,
    edit_review_id: uuid.UUID | None = None,
    highlight_review_id: uuid.UUID | None = None,
    maturity_filter: str = "",
    capture_kind_filter: str = "",
    show_rejected: bool = False,
    polish_result=None,
    flash: str | None = None,
    flash_ok: bool = True,
) -> dict:
    from thread.services.incubator_rejected import list_rejected_seeds

    widget = await build_vault_review_widget(
        db,
        settings,
        highlight_review_id=highlight_review_id,
        maturity_filter=maturity_filter.strip(),
        capture_kind_filter=capture_kind_filter.strip(),
    )
    edit_form = None
    polish_diff = None
    if edit_review_id is not None:
        record = await db.get(ReviewRecord, edit_review_id)
        if record is not None:
            edit_form = load_candidate_edit_form(settings, record)
    if polish_result is not None and edit_form is not None:
        polish_diff = build_polish_diff(polish_result.before, polish_result.after)
    parse_preview = None
    if edit_form is not None and edit_form.ingest_id:
        from thread.services.ingest_parse_view import load_ingest_parse_preview

        parse_preview = load_ingest_parse_preview(settings, edit_form.ingest_id)
    return {
        "widget": widget,
        "edit_form": edit_form,
        "parse_preview": parse_preview,
        "polish_result": polish_result,
        "polish_diff": polish_diff,
        "flash": flash,
        "flash_ok": flash_ok,
        "studio_open": widget.needs_attention or edit_form is not None or polish_result is not None,
        "highlight_review_id": str(highlight_review_id) if highlight_review_id else "",
        "maturity_filter": maturity_filter.strip(),
        "capture_kind_filter": capture_kind_filter.strip(),
        "rejected_seeds": list_rejected_seeds(settings),
        "show_rejected": show_rejected,
    }


def _parse_related_field(raw: str) -> list[str]:
    links: list[str] = []
    for line in raw.replace(",", "\n").splitlines():
        token = line.strip().strip("-").strip()
        if token.startswith("[[") and token.endswith("]]"):
            token = token[2:-2].strip()
        if token and token not in links:
            links.append(token)
    return links


def _merge_related_form(
    *,
    related_stems: list[str] | None = None,
    related_custom: str = "",
    related: str = "",
) -> list[str]:
    links: list[str] = []
    for stem in related_stems or []:
        token = stem.strip()
        if token and token not in links:
            links.append(token)
    for token in _parse_related_field(related_custom):
        if token not in links:
            links.append(token)
    for token in _parse_related_field(related):
        if token not in links:
            links.append(token)
    return links


def _vault_ops_template_context(
    settings: Settings,
    *,
    result: dict | None = None,
    flash: str | None = None,
    flash_ok: bool = True,
    lint_summary: str | None = None,
) -> dict:
    return {
        "sandbox_mode": settings.vault_sandbox_mode,
        "allow_test_promote": settings.vault_allow_test_promote,
        "vault_ops_guide": guide_for_vault_ops(),
        "result": result,
        "flash": flash,
        "flash_ok": flash_ok,
        "lint_summary": lint_summary,
    }


@router.get("/partials/knowledge/vault-review", response_class=HTMLResponse)
async def knowledge_vault_review_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = await _capture_studio_template_context(db, settings)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_capture_studio.html",
        ctx,
    )


@router.get("/partials/knowledge/capture-studio", response_class=HTMLResponse)
async def knowledge_capture_studio_partial(
    request: Request,
    inbox: str = Query(""),
    maturity: str = Query(""),
    capture_kind: str = Query(""),
    rejected: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = await _capture_studio_template_context(
        db,
        settings,
        highlight_review_id=_parse_inbox_review_id(inbox),
        maturity_filter=maturity,
        capture_kind_filter=capture_kind,
        show_rejected=rejected.lower() in ("1", "true", "yes", "open"),
    )
    return templates.TemplateResponse(
        request,
        "partials/knowledge_capture_studio.html",
        ctx,
    )


@router.post("/partials/knowledge/idea-capture", response_class=HTMLResponse)
async def knowledge_idea_capture_partial(
    request: Request,
    dump: str = Form(""),
    tags: str = Form(""),
    context: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        result = await capture_idea_to_vault(
            settings,
            db,
            dump=dump,
            tags=tags,
            context_note=context,
        )
        await db.commit()
        flash = f"Idea captured — {result.title}"
        if not result.gate.ok:
            flash = f"Captured with gate warnings — {', '.join(result.gate.issues)}"
        ctx = await _capture_studio_template_context(
            db,
            settings,
            highlight_review_id=result.review_id,
            flash=flash,
            flash_ok=result.gate.ok,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)
    except IdeaCaptureError as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)


@router.get("/partials/knowledge/candidate-edit", response_class=HTMLResponse)
async def knowledge_candidate_edit_partial(
    request: Request,
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = await _capture_studio_template_context(db, settings, edit_review_id=review_id)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_capture_studio.html",
        ctx,
    )


@router.get("/partials/knowledge/vault-ops", response_class=HTMLResponse)
async def knowledge_vault_ops_partial(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    lint = run_vault_op(settings, "lint", apply=False)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_vault_ops.html",
        _vault_ops_template_context(settings, lint_summary=lint.summary),
    )


@router.post("/partials/knowledge/vault-op", response_class=HTMLResponse)
async def knowledge_vault_op(
    request: Request,
    action: str = Form(...),
    apply: str = Form("false"),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    apply_flag = apply.lower() in ("true", "1", "yes", "on")
    op = run_vault_op(settings, action, apply=apply_flag)
    return templates.TemplateResponse(
        request,
        "partials/knowledge_vault_ops.html",
        _vault_ops_template_context(
            settings,
            result=op.to_context(),
            flash_ok=op.ok,
        ),
    )


@router.get("/partials/capture/fab", response_class=HTMLResponse)
async def capture_fab_drawer(
    request: Request,
    opp_id: str = Query(""),
    opp_name: str = Query(""),
    award_key: str = Query(""),
    signal_title: str = Query(""),
    agency: str = Query(""),
    entity: str = Query(""),
    entity_title: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    parsed_opp = parse_opp_id(opp_id)
    if parsed_opp and not opp_name.strip():
        opp = await opp_svc.get_opportunity(db, parsed_opp)
        if opp:
            opp_name = opp.name
    context = build_capture_context(
        opp_id=opp_id,
        opp_name=opp_name,
        award_key=award_key,
        signal_title=signal_title,
        agency=agency,
        entity=entity,
        entity_title=entity_title,
    )
    return templates.TemplateResponse(
        request,
        "partials/capture_fab_drawer.html",
        {"context": context, "flash": None, "flash_ok": True, "studio_href": None},
    )


def _capture_error_message(exc: BaseException) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    name = type(exc).__name__
    if name in {"ReadTimeout", "ConnectTimeout", "TimeoutException", "ConnectError"}:
        return f"{name} — Ollama may be down or slow. Check Settings → LLM or retry."
    return f"{name} — unexpected error; check server logs."


@router.post("/partials/capture/quick", response_class=HTMLResponse)
async def capture_fab_quick(
    request: Request,
    dump: str = Form(""),
    opp_id: str = Form(""),
    opp_name: str = Form(""),
    award_key: str = Form(""),
    signal_title: str = Form(""),
    agency: str = Form(""),
    entity: str = Form(""),
    entity_title: str = Form(""),
    attachment: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    context = build_capture_context(
        opp_id=opp_id,
        opp_name=opp_name,
        award_key=award_key,
        signal_title=signal_title,
        agency=agency,
        entity=entity,
        entity_title=entity_title,
    )
    attachment_name = ""
    attachment_bytes = b""
    if attachment and attachment.filename:
        attachment_name = attachment.filename
        attachment_bytes = await attachment.read()
    try:
        has_attachment = bool(attachment_name and attachment_bytes)
        intent, intent_provider = await classify_capture_intent(settings, dump)
        if intent == CaptureIntent.ADMIN_TASK and not has_attachment:
            task_result = await ingest_fab_task(
                settings,
                db,
                raw_dump=dump,
                context=context,
                intent_provider=intent_provider,
            )
            return templates.TemplateResponse(
                request,
                "partials/capture_fab_drawer.html",
                {
                    "context": context,
                    "flash_ok": True,
                    "capture_lane": "task",
                    "task_href": "/tasks#today",
                    "inferred_title": task_result.title,
                    "dump_snippet": task_result.description[:160] if task_result.description else "",
                    "polish_provider": task_result.polish_provider,
                    "title_provider": task_result.intent_provider,
                },
            )

        result = await ingest_quick_capture(
            settings,
            db,
            raw_dump=dump,
            context=context,
            attachment_name=attachment_name,
            attachment_bytes=attachment_bytes,
        )
        doc_note = ""
        if result.document_name:
            doc_note = format_document_status_note(
                filename=result.document_name,
                mineru_status=result.mineru_status,
                parse_summary=result.parse_summary,
            )
        studio_href = "/knowledge#knowledge-vault-inbox"
        if result.review_id:
            studio_href = f"/knowledge?inbox={result.review_id}#knowledge-vault-inbox"
        return templates.TemplateResponse(
            request,
            "partials/capture_fab_drawer.html",
            {
                "context": context,
                "flash_ok": True,
                "capture_lane": "knowledge",
                "studio_href": studio_href,
                "queue_position": result.queue_position,
                "queue_total": result.queue_total,
                "inbox_lane": result.inbox_lane,
                "inferred_title": result.inferred_title,
                "dump_snippet": result.dump_snippet,
                "polish_provider": result.polish_provider,
                "title_provider": result.title_provider,
                "doc_note": doc_note,
                "mineru_status": result.mineru_status,
            },
        )
    except (CaptureFabError, VaultWriteError) as exc:
        return templates.TemplateResponse(
            request,
            "partials/capture_fab_drawer.html",
            {
                "context": context,
                "flash": str(exc),
                "flash_ok": False,
                "flash_title": "Couldn't capture that",
                "studio_href": None,
            },
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "partials/capture_fab_drawer.html",
            {
                "context": context,
                "flash": _capture_error_message(exc),
                "flash_ok": False,
                "flash_title": "Capture failed",
                "studio_href": None,
            },
        )


@router.post("/partials/knowledge/candidate", response_class=HTMLResponse)
async def knowledge_write_candidate(
    request: Request,
    name: str = Form(...),
    body: str = Form(...),
    page_type: str = Form("synthesis"),
    queue_review: bool = Form(True),
    test_mode: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    source = "test" if test_mode or settings.vault_sandbox_mode else "api"
    citations = "source:test" if test_mode else "source:manual"
    try:
        write_result = write_candidate_note(
            settings,
            name=name.strip(),
            body=body.strip(),
            page_type=page_type,
            citations=citations,
            source=source,
        )
        review_id = None
        if queue_review:
            record = await queue_vault_candidate_review(
                db,
                candidate_path=write_result.path,
                target_path=None,
            )
            review_id = str(record.id)
            await db.commit()
        flash = f"Queued {write_result.path} in Vault Inbox below."
        if review_id:
            flash += f" (review {review_id[:8]}…)"
        studio_ctx = await _capture_studio_template_context(db, settings, flash=flash, flash_ok=True)
        return templates.TemplateResponse(
            request,
            "partials/knowledge_vault_ops_refresh.html",
            {
                **_vault_ops_template_context(
                    settings,
                    flash=flash,
                    flash_ok=True,
                    lint_summary=run_vault_op(settings, "lint", apply=False).summary,
                ),
                **studio_ctx,
            },
        )
    except VaultWriteError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request,
            "partials/knowledge_vault_ops.html",
            _vault_ops_template_context(
                settings,
                flash=str(exc),
                flash_ok=False,
                lint_summary=run_vault_op(settings, "lint", apply=False).summary,
            ),
        )


@router.post("/partials/knowledge/candidate-save", response_class=HTMLResponse)
async def knowledge_save_candidate(
    request: Request,
    review_id: uuid.UUID = Form(...),
    candidate_path: str = Form(...),
    name: str = Form(...),
    body: str = Form(...),
    page_type: str = Form("synthesis"),
    related_stems: list[str] = Form(default=[]),
    related_custom: str = Form(""),
    related: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        save_candidate_note(
            settings,
            candidate_path.strip(),
            name=name.strip(),
            body=body.strip(),
            page_type=page_type,
            related=_merge_related_form(
                related_stems=related_stems,
                related_custom=related_custom,
                related=related,
            ),
        )
        flash = f"Saved {candidate_path.strip()}"
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=flash,
            flash_ok=True,
        )
        return templates.TemplateResponse(
            request,
            "partials/knowledge_capture_studio.html",
            ctx,
        )
    except VaultWriteError as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(
            request,
            "partials/knowledge_capture_studio.html",
            ctx,
        )


@router.post("/partials/knowledge/candidate-polish", response_class=HTMLResponse)
async def knowledge_polish_candidate(
    request: Request,
    review_id: uuid.UUID = Form(...),
    candidate_path: str | None = Form(None),
    name: str | None = Form(None),
    body: str | None = Form(None),
    page_type: str | None = Form(None),
    related_stems: list[str] | None = Form(None),
    related_custom: str | None = Form(None),
    related: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    record = await db.get(ReviewRecord, review_id)
    rel = (candidate_path or (record.entity_id if record else "") or "").strip()
    if not rel:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash="Candidate path missing for polish",
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)

    try:
        if name is not None and body is not None and name.strip() and body.strip():
            save_candidate_note(
                settings,
                rel,
                name=name.strip(),
                body=body.strip(),
                page_type=page_type or "synthesis",
                related=_merge_related_form(
                    related_stems=related_stems,
                    related_custom=related_custom or "",
                    related=related or "",
                ),
            )
        polish_result = await polish_candidate_note(settings, rel)
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            polish_result=polish_result,
            flash=f"Polish ready ({polish_result.provider}) — review diff before accept",
            flash_ok=True,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)
    except (VaultWriteError, CandidatePolishError) as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)


@router.post("/partials/knowledge/candidate-reparse", response_class=HTMLResponse)
async def knowledge_reparse_candidate(
    request: Request,
    review_id: uuid.UUID = Form(...),
    candidate_path: str = Form(...),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    from thread.services.mineru_reparse import MineruReparseError, reparse_candidate_document

    try:
        result = reparse_candidate_document(settings, candidate_path.strip())
        if result.mineru_ready:
            flash = (
                f"MinerU re-parsed {result.filename}"
                + (f" — {result.glance_summary}" if result.glance_summary else "")
            )
            flash_ok = True
        else:
            flash = f"MinerU re-parse failed: {result.error}"
            flash_ok = False
        ctx = await _capture_studio_template_context(
            db,
            settings,
            highlight_review_id=review_id,
            flash=flash,
            flash_ok=flash_ok,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)
    except MineruReparseError as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            highlight_review_id=review_id,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)


@router.post("/partials/knowledge/candidate-enrich", response_class=HTMLResponse)
async def knowledge_enrich_candidate(
    request: Request,
    review_id: uuid.UUID = Form(...),
    candidate_path: str = Form(...),
    enrich_source: str = Form("clew"),
    clew_mode: str = Form("spend_trend"),
    agency: str = Form(""),
    recipient: str = Form(""),
    research_run_id: str = Form(""),
    research_query: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        result = await enrich_candidate_note(
            settings,
            candidate_path.strip(),
            source=enrich_source,
            research_run_id=research_run_id.strip() or None,
            research_query=research_query.strip() or None,
            clew_mode=clew_mode,
            agency=agency,
            recipient=recipient,
        )
        flash = f"Enrichment appended — {result.section_title}"
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=flash,
            flash_ok=True,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)
    except (VaultWriteError, CandidateEnrichError) as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)


@router.post("/partials/knowledge/candidate-polish-accept", response_class=HTMLResponse)
async def knowledge_polish_accept(
    request: Request,
    review_id: uuid.UUID = Form(...),
    candidate_path: str = Form(...),
    name: str = Form(...),
    body: str = Form(...),
    page_type: str = Form("synthesis"),
    related: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        from thread.services.vault_candidate_polish import PolishedCandidate

        apply_polished_candidate(
            settings,
            candidate_path.strip(),
            PolishedCandidate(
                name=name.strip(),
                page_type=page_type,
                body=body.strip(),
                related=tuple(_parse_related_field(related)),
            ),
        )
        flash = f"Polish accepted — saved {candidate_path.strip()}"
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=flash,
            flash_ok=True,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)
    except VaultWriteError as exc:
        ctx = await _capture_studio_template_context(
            db,
            settings,
            edit_review_id=review_id,
            flash=str(exc),
            flash_ok=False,
        )
        return templates.TemplateResponse(request, "partials/knowledge_capture_studio.html", ctx)


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


def _vault_controls_context(
    settings: Settings,
    *,
    flash: str = "",
    flash_ok: bool = True,
) -> dict:
    return {
        "vault_sandbox_mode": settings.vault_sandbox_mode,
        "vault_allow_test_promote": settings.vault_allow_test_promote,
        "flash": flash,
        "flash_ok": flash_ok,
    }


def _persist_env_bool(settings: Settings, key: str, enabled: bool) -> Settings:
    value = "true" if enabled else "false"
    upsert_env_var(settings.repo_root / ".env", key, value)
    apply_env_to_process(key, value)
    return reload_settings()


@router.post("/settings/vault-sandbox", response_class=HTMLResponse)
async def settings_toggle_vault_sandbox(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    form = await request.form()
    enabled = form.get("enabled") == "true"
    settings = _persist_env_bool(settings, "THREAD_VAULT_SANDBOX", enabled)
    if not enabled and settings.vault_allow_test_promote:
        settings = _persist_env_bool(settings, "THREAD_ALLOW_TEST_PROMOTE", False)
    label = "enabled" if settings.vault_sandbox_mode else "disabled"
    return templates.TemplateResponse(
        request,
        "partials/settings_vault_controls.html",
        _vault_controls_context(
            settings,
            flash=f"Vault sandbox {label}. Saved to .env — takes effect immediately.",
        ),
    )


@router.post("/settings/vault-allow-test-promote", response_class=HTMLResponse)
async def settings_toggle_vault_allow_test_promote(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not settings.vault_sandbox_mode:
        return templates.TemplateResponse(
            request,
            "partials/settings_vault_controls.html",
            _vault_controls_context(
                settings,
                flash="Enable vault sandbox first.",
                flash_ok=False,
            ),
        )
    form = await request.form()
    enabled = form.get("enabled") == "true"
    settings = _persist_env_bool(settings, "THREAD_ALLOW_TEST_PROMOTE", enabled)
    label = "enabled" if settings.vault_allow_test_promote else "disabled"
    return templates.TemplateResponse(
        request,
        "partials/settings_vault_controls.html",
        _vault_controls_context(
            settings,
            flash=f"Test promote {label}. Saved to .env.",
        ),
    )


@router.post("/system/restart")
async def system_restart() -> dict[str, str]:
    schedule_restart(0.75)
    return {
        "status": "restarting",
        "message": "Server is restarting. The UI will reconnect automatically.",
    }


def _clew_form_from_params(
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    mode: str = "money_flow",
    include_mcp: bool = False,
) -> dict[str, str | bool]:
    return {
        "agency": agency,
        "sub_agency": sub_agency,
        "recipient": recipient,
        "naics_codes": naics_codes,
        "psc_codes": psc_codes,
        "mode": mode if mode in {"money_flow", "spend_trend", "teaming", "recipient_landscape"} else "money_flow",
        "include_mcp": include_mcp,
    }


async def _clew_page_context(
    db: AsyncSession,
    settings: Settings,
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    mode: str = "money_flow",
    run: bool = False,
    review_id: str | None = None,
    include_mcp: bool = False,
    path: str = "",
) -> dict:
    ctx = await build_insights_page_context(db, settings)
    clew_form = _clew_form_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        include_mcp=include_mcp,
    )
    drilldown = await build_drilldown(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=str(clew_form["mode"]),
        run=run,
        review_id=review_id,
        include_mcp=include_mcp,
        path=path,
    )
    return {
        "ctx": ctx,
        "clew_form": clew_form,
        "drilldown": drilldown,
        "clew_guide": guide_for_clew(),
        "clew_path": path,
        "clew_traces": _clew_traces_for_template(settings),
    }


def _clew_traces_for_template(settings: Settings) -> list[dict]:
    return [
        {
            "trace": trace,
            "summary": describe_trace(trace),
            "href": clew_trace_href(trace),
        }
        for trace in load_clew_traces(settings)
    ]


async def _render_clew_saved_traces_panel(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    *,
    flash: str | None = None,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    mode: str = "money_flow",
) -> HTMLResponse:
    page = await _clew_page_context(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        run=False,
    )
    return templates.TemplateResponse(
        request,
        "partials/clew_saved_traces.html",
        {
            "clew_traces": _clew_traces_for_template(settings),
            "clew_flash": flash,
            "drilldown": page["drilldown"],
            "ctx": page["ctx"],
        },
    )


@router.post("/clew/save", response_class=HTMLResponse)
async def clew_save_trace(
    request: Request,
    name: str = Form(...),
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    mode: str = Form("money_flow"),
    include_mcp: str = Form(""),
    description: str = Form(""),
    last_summary: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    mcp_on = include_mcp in ("1", "on", "true", "yes")
    trace = new_clew_trace_from_form(
        settings,
        name=name,
        mode=mode,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        include_mcp=mcp_on,
        description=description,
        last_summary=last_summary,
    )
    if trace is None:
        return await _render_clew_saved_traces_panel(
            request,
            db,
            settings,
            flash="Trace needs at least one facet (agency, recipient, NAICS, PSC, etc.).",
            agency=agency,
            sub_agency=sub_agency,
            recipient=recipient,
            naics_codes=naics_codes,
            psc_codes=psc_codes,
            mode=mode,
        )
    save_clew_trace(settings, trace)
    return await _render_clew_saved_traces_panel(
        request,
        db,
        settings,
        flash=f"Saved trace “{trace.name}”.",
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
    )


@router.post("/clew/{trace_id}/delete", response_class=HTMLResponse)
async def clew_delete_trace(
    request: Request,
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not delete_clew_trace(settings, trace_id):
        return await _render_clew_saved_traces_panel(
            request, db, settings, flash="Saved trace not found."
        )
    return await _render_clew_saved_traces_panel(request, db, settings, flash="Saved trace deleted.")


@router.get("/clew", response_class=HTMLResponse)
async def clew_page(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    mode: str = Query("money_flow"),
    run: int = Query(0, ge=0, le=1),
    include_mcp: int = Query(0, ge=0, le=1),
    path: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    page = await _clew_page_context(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        run=bool(run),
        include_mcp=bool(include_mcp),
        path=path,
    )
    return templates.TemplateResponse(
        request,
        "clew.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "clew",
            "from_insights": (request.query_params.get("from") or "").strip().lower() == "insights",
            **page,
        },
    )


@router.get("/partials/clew/results", response_class=HTMLResponse)
async def clew_results_partial(
    request: Request,
    agency: str = Query(""),
    sub_agency: str = Query(""),
    recipient: str = Query(""),
    naics_codes: str = Query(""),
    psc_codes: str = Query(""),
    mode: str = Query("money_flow"),
    run: int = Query(0, ge=0, le=1),
    include_mcp: int = Query(0, ge=0, le=1),
    path: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    page = await _clew_page_context(
        db,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        mode=mode,
        run=bool(run),
        include_mcp=bool(include_mcp),
        path=path,
    )
    return templates.TemplateResponse(
        request,
        "partials/clew_results.html",
        page,
    )


@router.post("/clew/analyze", response_class=HTMLResponse)
async def clew_analyze(
    request: Request,
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    mode: str = Form("money_flow"),
    include_mcp: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    mcp_on = include_mcp in ("1", "on", "true", "yes")
    payload = {
        "mode": mode,
        "agency": agency.strip() or None,
        "sub_agency": sub_agency.strip() or None,
        "recipient": recipient.strip() or None,
        "naics_codes": naics_codes.strip() or None,
        "psc_codes": psc_codes.strip() or None,
    }
    result = await run_skill(settings, db, "clew_intel", payload)
    page = await _clew_page_context(
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
        include_mcp=mcp_on,
    )
    return templates.TemplateResponse(
        request,
        "partials/clew_results.html",
        page,
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
    mcp = build_mcp_tools_context(settings)
    return templates.TemplateResponse(
        request,
        "tools_skills.html",
        {
            "app_name": settings.public_app_name,
            "active_nav": "tools_skills",
            "skills": build_skills_tools_context(settings),
            "mcp_servers": mcp["servers"],
            "clew_modes": CLEW_MODES,
        },
    )


@router.get("/partials/tools/skills/{skill_id}/panel", response_class=HTMLResponse)
async def skills_run_panel_partial(
    request: Request,
    skill_id: str,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    ctx = build_skills_tools_context(settings)
    skill = next((s for s in ctx["skills"] if s["id"] == skill_id), None)
    if not skill:
        return HTMLResponse("Unknown skill", status_code=404)
    mcp = build_mcp_tools_context(settings)
    return templates.TemplateResponse(
        request,
        "partials/skills_run_panel.html",
        {
            "skill": skill,
            "mcp_servers": mcp["servers"],
            "clew_modes": CLEW_MODES,
        },
    )


@router.post("/tools/skills/{skill_id}/run", response_class=HTMLResponse)
async def tools_skill_run(
    request: Request,
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not skill_is_wired(skill_id):
        return HTMLResponse("Skill handler not wired", status_code=404)

    form = await request.form()
    payload = payload_from_form(skill_id, form)
    parse_error = payload.pop("_parse_error", None)
    if parse_error:
        return templates.TemplateResponse(
            request,
            "partials/skills_run_result.html",
            {
                "result": {
                    "status": "error",
                    "run_id": "—",
                    "review_id": None,
                    "errors": [f"Invalid arguments JSON: {parse_error}"],
                    "output_json": "",
                }
            },
        )

    try:
        run_result = await run_skill(settings, db, skill_id, payload)
    except KeyError:
        return HTMLResponse("Unknown skill", status_code=404)

    await db.commit()

    output_json = json.dumps(run_result.output, indent=2, default=str) if run_result.output else ""
    return templates.TemplateResponse(
        request,
        "partials/skills_run_result.html",
        {
            "result": {
                "status": run_result.status,
                "run_id": run_result.run_id,
                "review_id": run_result.review_id,
                "errors": run_result.errors,
                "output_json": output_json,
            }
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
    vault_stale = await build_stale_vault_review_widget(db, settings)
    open_tasks = await build_open_tasks_widget(db)
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
            "vault_stale": vault_stale,
            "open_tasks": open_tasks,
            "quick_actions": quick_actions,
            "platform_health": platform_health,
            "app_name": settings.public_app_name,
            "active_nav": "dashboard",
            "flash": None,
        },
    )


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    filter: str = Query("open", alias="filter"),
    view: str = Query("board"),
    task: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    page = await _tasks_page_context(db, filter_key=filter_key, view_mode=view)
    open_task_id: str | None = None
    if task:
        try:
            tid = uuid.UUID(task)
            if await get_task_detail(db, tid) is not None:
                open_task_id = str(tid)
        except ValueError:
            pass
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {
            "page": page,
            "filter_key": filter_key,
            "view_mode": page.view_mode,
            "open_task_id": open_task_id,
            "tasks_guide": guide_for_tasks(),
            "app_name": settings.public_app_name,
            "active_nav": "tasks",
            "flash": None,
        },
    )


@router.get("/partials/tasks/{task_id}/drawer", response_class=HTMLResponse)
async def tasks_drawer_partial(
    request: Request,
    task_id: uuid.UUID,
    filter: str = Query("open", alias="filter"),
    view: str = Query("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    view_mode = view if view in ("board", "list") else "board"
    ctx = await _task_drawer_context(db, task_id, filter_key=filter_key, view_mode=view_mode)
    if ctx is None:
        return HTMLResponse('<p class="text-neon-amber text-xs p-4">Task not found</p>', status_code=404)
    return templates.TemplateResponse(request, "partials/task_drawer_panel.html", ctx)


@router.post("/partials/tasks/{task_id}/notes", response_class=HTMLResponse)
async def tasks_note_partial(
    request: Request,
    task_id: uuid.UUID,
    body: str = Form(...),
    filter: str = Form("open"),
    view: str = Form("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    view_mode = view if view in ("board", "list") else "board"
    try:
        await append_task_note(db, task_id, body)
        await db.commit()
        ctx = await _task_drawer_context(
            db,
            task_id,
            filter_key=filter_key,
            view_mode=view_mode,
            note_flash="Note saved",
        )
        if ctx is None:
            return HTMLResponse('<p class="text-neon-amber text-xs p-4">Task not found</p>', status_code=404)
        return templates.TemplateResponse(request, "partials/task_drawer_panel.html", ctx)
    except ValueError as exc:
        return HTMLResponse(f'<p class="text-neon-amber text-xs p-4">{exc}</p>', status_code=400)


@router.post("/partials/tasks/{task_id}/checklist", response_class=HTMLResponse)
async def tasks_checklist_partial(
    request: Request,
    task_id: uuid.UUID,
    index: int = Form(...),
    filter: str = Form("open"),
    view: str = Form("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    view_mode = view if view in ("board", "list") else "board"
    try:
        await toggle_checklist_item(db, task_id, index)
        await db.commit()
        ctx = await _task_drawer_context(
            db,
            task_id,
            filter_key=filter_key,
            view_mode=view_mode,
            checklist_flash="Checklist updated",
        )
        if ctx is None:
            return HTMLResponse('<p class="text-neon-amber text-xs p-4">Task not found</p>', status_code=404)
        return templates.TemplateResponse(request, "partials/task_drawer_panel.html", ctx)
    except ValueError as exc:
        return HTMLResponse(f'<p class="text-neon-amber text-xs p-4">{exc}</p>', status_code=400)


@router.post("/partials/tasks/{task_id}/opportunity", response_class=HTMLResponse)
async def tasks_opportunity_partial(
    request: Request,
    task_id: uuid.UUID,
    opportunity_id: str = Form(""),
    filter: str = Form("open"),
    view: str = Form("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    view_mode = view if view in ("board", "list") else "board"
    try:
        opp_uuid: uuid.UUID | None = None
        clean = opportunity_id.strip()
        if clean:
            opp_uuid = uuid.UUID(clean)
        await link_task_to_opportunity(db, task_id, opp_uuid)
        await db.commit()
        ctx = await _task_drawer_context(
            db,
            task_id,
            filter_key=filter_key,
            view_mode=view_mode,
            opp_flash="Opportunity link saved" if opp_uuid else "Opportunity unlinked",
        )
        if ctx is None:
            return HTMLResponse('<p class="text-neon-amber text-xs p-4">Task not found</p>', status_code=404)
        return templates.TemplateResponse(request, "partials/task_drawer_panel.html", ctx)
    except ValueError as exc:
        return HTMLResponse(f'<p class="text-neon-amber text-xs p-4">{exc}</p>', status_code=400)


@router.get("/partials/tasks/body", response_class=HTMLResponse)
async def tasks_body_partial(
    request: Request,
    filter: str = Query("open", alias="filter"),
    view: str = Query("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    page = await _tasks_page_context(db, filter_key=filter_key, view_mode=view)
    return templates.TemplateResponse(
        request,
        "partials/tasks_body.html",
        {"page": page, "filter_key": filter_key, "view_mode": page.view_mode},
    )


@router.post("/partials/tasks/{task_id}/status", response_class=HTMLResponse)
async def tasks_status_partial(
    request: Request,
    task_id: uuid.UUID,
    status: str = Form(...),
    filter: str = Form("open"),
    view: str = Form("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filter_key = filter if filter in ("open", "today", "overdue", "done") else "open"
    try:
        await update_operator_task_status(db, task_id, status)
        await db.commit()
        page = await _tasks_page_context(db, filter_key=filter_key, view_mode=view)
        return templates.TemplateResponse(
            request,
            "partials/tasks_body.html",
            {"page": page, "filter_key": filter_key, "view_mode": page.view_mode},
        )
    except ValueError as exc:
        return HTMLResponse(f'<p class="text-neon-amber text-xs p-4">{exc}</p>', status_code=400)


@router.post("/partials/tasks/{task_id}/complete", response_class=HTMLResponse)
async def tasks_complete_partial(
    request: Request,
    task_id: uuid.UUID,
    filter: str = Form("open"),
    view: str = Form("board"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    return await tasks_status_partial(
        request,
        task_id,
        status="done",
        filter=filter,
        view=view,
        db=db,
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
    watch_agency: str = Form(""),
    naics_code: str = Form(""),
    end_date: str = Form(""),
    obligation: str = Form(""),
    months_to_end: str = Form(""),
    return_lens: str = Form("overview"),
    agency: str = Form(""),
    sub_agency: str = Form(""),
    recipient: str = Form(""),
    naics_codes: str = Form(""),
    psc_codes: str = Form(""),
    awarding_office: str = Form(""),
    funding_office: str = Form(""),
    recipient_uei: str = Form(""),
    pop_state: str = Form(""),
    extent_competed: str = Form(""),
    type_of_set_aside: str = Form(""),
    min_contract_value: str = Form(""),
    min_value_basis: str = Form("potential"),
    exclude_agencies: str = Form(""),
    entity_kind: str = Form(""),
    entity_value: str = Form(""),
    entity_scope: str = Form(""),
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
        agency=watch_agency,
        naics_code=naics_code.strip() or None,
        end_date=end_date.strip() or None,
        obligation=obl,
        months_to_end=months,
    )
    add_watchlist_item(settings, item)
    flash = f"Watching {item.title} — see Pulse watchlist."
    hx_target = (request.headers.get("HX-Target") or "").strip()
    if hx_target in {"insights-slice-panel", "insights-stage-content"}:
        lens = (return_lens or "overview").strip() or "overview"
        panel = await build_slice_panel(
            db,
            settings,
            lens=lens,
            run=True,
            entity_kind=entity_kind,
            entity_value=entity_value,
            entity_scope=entity_scope,
            **_advanced_facet_kwargs(
                agency=agency,
                sub_agency=sub_agency,
                recipient=recipient,
                naics_codes=naics_codes,
                psc_codes=psc_codes,
                awarding_office=awarding_office,
                funding_office=funding_office,
                recipient_uei=recipient_uei,
                pop_state=pop_state,
                extent_competed=extent_competed,
                type_of_set_aside=type_of_set_aside,
                min_contract_value=min_contract_value,
            min_value_basis=min_value_basis,
                exclude_agencies=exclude_agencies,
            ),
        )
        return templates.TemplateResponse(
            request,
            "partials/insights_stage_content.html",
            _slice_template_ctx(panel, slice_flash=flash),
        )
    return await _render_insights_body(
        request,
        db,
        settings,
        flash=flash,
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
    opp = await opp_svc.create_opportunity(
        db,
        OpportunityCreate(name=name, lifecycle_state=LifecycleState.PURSUING, entry_reason="manual_commit"),
    )
    await db.commit()
    target = capture_workspace_href(opp.id)
    if request.headers.get("HX-Request"):
        return _htmx_redirect(target)
    return RedirectResponse(url=target, status_code=303)


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
            lifecycle_state=LifecycleState.PURSUING,
        ),
    )
    await db.commit()
    target = capture_workspace_href(opp.id)
    if request.headers.get("HX-Request"):
        return _htmx_redirect(target)
    return RedirectResponse(url=target, status_code=303)


@router.post("/signals/track", response_class=HTMLResponse)
async def track_signal_form(
    request: Request,
    award_key: str = Form(...),
    title: str = Form(""),
    agency: str = Form(""),
    naics_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    existing = await opp_svc.get_opportunity_by_award_key(db, award_key)
    if existing is not None:
        opp = existing
    else:
        opp = await opp_svc.create_opportunity(
            db,
            OpportunityCreate(
                name=signal_opportunity_name(title=title, agency=agency),
                award_key=award_key,
                naics_code=naics_code or None,
                entry_reason="intel_signal",
                lifecycle_state=LifecycleState.PURSUING,
            ),
        )
    await db.commit()
    target = capture_workspace_href(opp.id)
    if request.headers.get("HX-Request"):
        return _htmx_redirect(target)
    return RedirectResponse(url=target, status_code=303)


async def _render_capture_workspace(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
    *,
    tab: str = "packet",
    slide: str = "",
    flash: str | None = None,
) -> HTMLResponse:
    opp = await opp_svc.get_opportunity(db, opp_id)
    if not opp:
        return HTMLResponse("Opportunity not found", status_code=404)

    redirect_url = legacy_tab_redirect(tab)
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=302)

    panel = await _panel_context(db, settings, opp_id, tab=tab, slide=slide or None, flash=flash)
    return templates.TemplateResponse(
        request,
        "opportunity.html",
        {
            "opp": opp,
            "app_name": settings.public_app_name,
            "active_nav": "filament",
            "flash": flash,
            **panel,
        },
    )


@router.get("/capture", response_class=HTMLResponse)
async def capture_home_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    capture = await build_capture_home(db, settings)
    return templates.TemplateResponse(
        request,
        "capture.html",
        {
            "capture": capture,
            "app_name": settings.public_app_name,
            "active_nav": "filament",
            "flash": None,
        },
    )


@router.get("/capture/{opp_id}", response_class=HTMLResponse)
async def capture_workspace(
    request: Request,
    opp_id: uuid.UUID,
    tab: str = Query("packet"),
    slide: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return await _render_capture_workspace(
        request, db, settings, opp_id, tab=tab, slide=slide or ""
    )


@router.get("/opportunities/{opp_id}", response_class=HTMLResponse)
async def opportunity_workspace_redirect(
    opp_id: uuid.UUID,
    tab: str = Query("packet"),
    slide: str = Query(""),
) -> RedirectResponse:
    return RedirectResponse(
        url=capture_workspace_href(opp_id, tab=tab or None, slide=slide or None),
        status_code=307,
    )


@router.post("/opportunities/{opp_id}/milestone-gate", response_class=HTMLResponse)
async def set_milestone_gate(
    request: Request,
    opp_id: uuid.UUID,
    milestone_gate: str = Form(...),
    tab: str = Form("packet"),
    slide: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    opp = await opp_svc.update_milestone_gate(db, opp_id, milestone_gate)
    if not opp:
        return HTMLResponse("Opportunity not found", status_code=404)
    await db.commit()
    await db.refresh(opp)
    ctx = await _panel_context(db, settings, opp_id, tab=tab, slide=slide or None)
    panel_html = _render_panel(request, ctx).body.decode("utf-8")
    packet = ctx.get("packet")
    gate_html = templates.get_template("partials/milestone_gate_selector.html").render(
        {
            "request": request,
            "opp": opp,
            "opp_id": opp_id,
            "active_tab": ctx.get("active_tab", tab),
            "packet": packet,
        }
    )
    gate_oob = gate_html.replace(
        'id="ms-gate-shell"',
        'id="ms-gate-shell" hx-swap-oob="true"',
        1,
    )
    return HTMLResponse(panel_html + gate_oob)


@router.get("/opportunities/{opp_id}/panel", response_class=HTMLResponse)
async def opportunity_panel(
    request: Request,
    opp_id: uuid.UUID,
    tab: str = Query("packet"),
    slide: str = Query(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not await opp_svc.get_opportunity(db, opp_id):
        return HTMLResponse("Opportunity not found", status_code=404)
    ctx = await _panel_context(db, settings, opp_id, tab=tab, slide=slide or None)
    return _render_panel(request, ctx)


@router.post("/opportunities/{opp_id}/packet/{field_key}/fill", response_class=HTMLResponse)
async def fill_packet_field_route(
    request: Request,
    opp_id: uuid.UUID,
    field_key: str,
    source: str = Form(...),
    slide: str = Form(""),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not await opp_svc.get_opportunity(db, opp_id):
        return HTMLResponse("Opportunity not found", status_code=404)

    if source in (PG_INTEL, USASPENDING_MCP, SAM_MCP, GROK):
        result = await apply_route_fill(db, settings, opp_id, field_key, source)
    else:
        result = await run_packet_route_fill(db, settings, opp_id, field_key, source)

    if result.redirect_url:
        return _htmx_redirect(result.redirect_url)

    if result.ok and result.value:
        await db.commit()

    flash = result.message if result.message else None
    if not result.ok and not flash:
        flash = "Fill route did not produce a value"
    ctx = await _panel_context(
        db,
        settings,
        opp_id,
        tab="packet",
        flash=flash,
        slide=slide or None,
    )
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
    field = await enrich_packet_field_card(db, answer)
    return templates.TemplateResponse(
        request,
        "partials/packet_field_compact.html",
        {"field": field, "opp_id": opp_id},
    )


@router.post("/opportunities/{opp_id}/actions", response_class=HTMLResponse)
async def create_action_form(
    request: Request,
    opp_id: uuid.UUID,
    action: str = Form(...),
    owner: str = Form(""),
    due_date: str = Form(""),
    linked_field_keys: str = Form(""),
    tab: str = Form("packet"),
    slide: str = Form("slide_14_actions"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    parsed_due: date | None = None
    if due_date.strip():
        parsed_due = date.fromisoformat(due_date.strip())
    keys = [k.strip() for k in linked_field_keys.split(",") if k.strip()]
    await opp_svc.add_action_item(db, opp_id, action.strip(), owner.strip() or None, parsed_due, keys)
    await db.commit()
    ctx = await _panel_context(db, settings, opp_id, tab=tab, slide=slide or "slide_14_actions")
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
    promote_target: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    flash: str | None = None
    try:
        pending = await db.get(ReviewRecord, review_id)
        if pending is None:
            raise ReviewGateError("Review record not found")
        if promote_target and promote_target.strip() and pending.entity_type == "vault_candidate":
            validated = validate_promote_target(promote_target)
            pending.provenance = patch_provenance_target(pending.provenance, validated)
            await db.flush()
        record = await approve_review(db, review_id)
        vault_result = await ingest_approved_review(db, settings, record)
        await db.commit()
        if vault_result and vault_result.paths:
            flash = f"Approved — vault: {', '.join(vault_result.paths)}"
            if vault_result.semantic:
                flash += (
                    f" · semantic +{vault_result.semantic.get('links_added', 0)} links"
                )
        elif record.entity_type in ("vault_candidate", "skill_run", "research_finding", "research_interpretation"):
            flash = "Approved — no vault write (check sandbox / test markers)"
    except (ReviewGateError, VaultWriteError) as exc:
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

    if return_scope in ("knowledge_vault_review", "knowledge_capture_studio"):
        flash_ok = bool(flash and flash.startswith("Approved — vault:"))
        ctx = await _capture_studio_template_context(db, settings, flash=flash, flash_ok=flash_ok)
        return templates.TemplateResponse(
            request,
            "partials/knowledge_capture_studio.html",
            ctx,
        )

    if not opp_id:
        return HTMLResponse("opp_id required for workspace approve", status_code=400)

    parsed_opp_id = uuid.UUID(opp_id)
    ctx = await _panel_context(db, settings, parsed_opp_id, tab=tab, flash=flash)
    return _render_panel(request, ctx)


@router.post("/review/{review_id}/reject", response_class=HTMLResponse)
async def reject_review_route(
    request: Request,
    review_id: uuid.UUID,
    return_scope: str = Form("global"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    flash: str | None = None
    flash_ok = True
    try:
        record = await reject_review(db, review_id)
        if record.entity_type == "vault_candidate":
            reject_vault_candidate(settings, record.entity_id)
        await db.commit()
        flash = f"Rejected — moved to generated-projections/rejected/{Path(record.entity_id).name}"
    except ReviewGateError as exc:
        await db.rollback()
        flash = str(exc)
        flash_ok = False

    if return_scope in ("knowledge_vault_review", "knowledge_capture_studio"):
        ctx = await _capture_studio_template_context(
            db,
            settings,
            flash=flash,
            flash_ok=flash_ok,
            show_rejected=True,
        )
        return templates.TemplateResponse(
            request,
            "partials/knowledge_capture_studio.html",
            ctx,
        )

    if return_scope == "global":
        review_items = await load_global_review_queue(db, settings)
        return templates.TemplateResponse(
            request,
            "partials/global_review_queue.html",
            {"review_items": review_items, "flash": flash},
        )

    return HTMLResponse(flash or "Rejected", status_code=400 if not flash_ok else 200)