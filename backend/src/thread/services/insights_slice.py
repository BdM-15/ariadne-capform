"""Phase 17e — Insights lens tab panel (shared slice context)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.facet_query import ADVANCED_FACET_FIELDS, InsightFacetQuery
from thread.intel.pg_parallel import run_pg
from thread.services.insights_entity import (
    EntityContext,
    EntityProfileResult,
    agency_overview_brief,
    build_entity_profile,
    fetch_agency_sam_forward,
    resolve_lens_entities,
)
from thread.services.insights_explore import (
    RadarExploreResult,
    SamExploreResult,
    _facet_from_params,
    explore_radar,
)
from thread.intel import pg_queries as intel_queries
from thread.intel.sql_expressions import EXPIRING_MONTHS_AHEAD
from thread.services.insights_overview import OverviewResult, build_overview, overview_capture_verdict
from thread.services.insights_slice_explain import SliceExplainAvailability, slice_explain_availability

INSIGHTS_LENS_TABS: tuple[dict[str, str], ...] = (
    {"id": "overview", "label": "Overview"},
    {"id": "agency", "label": "Agency"},
    {"id": "competitor", "label": "Competitor"},
)
# Phase 2f: {"id": "footprint", "label": "Footprint"} — operator stance vs slice (UEI + vault domain intel)

# ponytail: slice-wide expiring rows live on Overview; entity-scoped rows on Agency/Competitor profiles
_LEGACY_LENS_IDS = frozenset({"trace", "competition", "sam", "recompete"})


@dataclass(frozen=True)
class SlicePanelContext:
    facet_form: dict[str, str]
    active_lens: str
    lens_tabs: tuple[dict[str, str], ...]
    query: InsightFacetQuery | None
    has_slice: bool
    overview: dict[str, Any]
    overview_ready: bool
    overview_idle: bool
    overview_error: str | None
    overview_verdict: dict[str, Any]
    pipeline_stats: dict[str, int | float]
    explore: RadarExploreResult
    sam_explore: SamExploreResult
    sam_form: dict[str, str]
    entity: EntityContext | None
    agency_entity: EntityContext | None
    competitor_entity: EntityContext | None
    agency_overview: dict[str, Any]
    entity_profile: dict[str, Any]
    entity_ready: bool
    entity_idle: bool
    entity_error: str | None
    agency_sam_forward: SamExploreResult
    sam_match_naics: bool
    cache_hit: bool
    cache_age_seconds: float | None
    slice_explain: SliceExplainAvailability | None = None


def facet_form_from_params(
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
    form = {
        "agency": agency.strip(),
        "sub_agency": sub_agency.strip(),
        "recipient": recipient.strip(),
        "naics_codes": naics_codes.strip(),
        "psc_codes": psc_codes.strip(),
        "min_contract_value": min_contract_value.strip(),
        "min_value_basis": min_value_basis.strip(),
    }
    for field in ADVANCED_FACET_FIELDS:
        form[field] = (locals().get(field) or "").strip()
    return form


async def build_slice_panel(
    session: AsyncSession,
    settings: Settings,
    *,
    lens: str = "overview",
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
    run: bool = False,
    sam_title: str = "",
    sam_agency_keyword: str = "",
    sam_naics_code: str = "",
    sam_psc_code: str = "",
    sam_days_back: int = 14,
    sam_run: bool = False,
    entity_kind: str = "",
    entity_value: str = "",
    entity_scope: str = "",
    agency_entity_value: str = "",
    agency_entity_scope: str = "",
    competitor_entity_value: str = "",
    competitor_entity_scope: str = "",
    sam_match_naics: bool = False,
) -> SlicePanelContext:
    if lens in _LEGACY_LENS_IDS:
        lens = "overview"
    elif lens not in {t["id"] for t in INSIGHTS_LENS_TABS}:
        lens = "overview"

    facet_form = facet_form_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        min_contract_value=min_contract_value,
        min_value_basis=min_value_basis,
        awarding_office=awarding_office,
        funding_office=funding_office,
        recipient_uei=recipient_uei,
        pop_state=pop_state,
        extent_competed=extent_competed,
        type_of_set_aside=type_of_set_aside,
        exclude_agencies=exclude_agencies,
    )
    facet_kwargs = {
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

    entity, agency_entity, competitor_entity = resolve_lens_entities(
        lens=lens,
        agency_entity_value=agency_entity_value,
        agency_entity_scope=agency_entity_scope,
        competitor_entity_value=competitor_entity_value,
        competitor_entity_scope=competitor_entity_scope,
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
    )
    slice_query = _facet_from_params(**facet_kwargs)
    has_slice = bool(slice_query and slice_query.has_filters() and run)

    overview_result: OverviewResult
    explore: RadarExploreResult
    entity_result: EntityProfileResult

    if has_slice and lens == "overview":
        overview_result, explore, pipeline_stats, explain_avail = await asyncio.gather(
            build_overview(session, settings, run=run, **facet_kwargs),
            run_pg(
                lambda s: explore_radar(
                    s,
                    settings,
                    run=True,
                    entity_kind=entity_kind,
                    entity_value=entity_value,
                    entity_scope=entity_scope,
                    **facet_kwargs,
                )
            ),
            run_pg(
                lambda s: intel_queries.expiring_pipeline_stats(
                    s,
                    slice_query,
                    months_ahead=EXPIRING_MONTHS_AHEAD,
                )
            ),
            slice_explain_availability(settings),
        )
        entity_result = EntityProfileResult(
            entity=entity or EntityContext(kind=lens, value="", scope="agency"),
            profile={"idle": True},
            status="idle",
        )
    elif has_slice and lens in {"agency", "competitor"}:
        overview_result, entity_result = await asyncio.gather(
            build_overview(session, settings, run=run, **facet_kwargs),
            run_pg(
                lambda s: build_entity_profile(
                    s,
                    settings,
                    slice_query,
                    entity,
                    lens=lens,
                )
            ),
        )
        if entity is None:
            entity_result = EntityProfileResult(
                entity=EntityContext(kind=lens, value="", scope="agency"),
                profile={"idle": True},
                status="idle",
            )
        explore = RadarExploreResult(
            query=slice_query,
            summary="",
            rows=(),
            intel_live=overview_result.intel_live,
            status="idle",
        )
        pipeline_stats = {"count": 0, "millions": 0.0}
        explain_avail = None
    else:
        overview_result = await build_overview(
            session,
            settings,
            run=run,
            **facet_kwargs,
        )
        explore = RadarExploreResult(
            query=slice_query if has_slice else None,
            summary="",
            rows=(),
            intel_live=overview_result.intel_live,
            status="idle",
        )
        entity_result = EntityProfileResult(
            entity=entity or EntityContext(kind=lens, value="", scope="agency"),
            profile={"idle": True},
            status="idle",
        )
        pipeline_stats = {"count": 0, "millions": 0.0}
        explain_avail = None

    query = overview_result.query

    cache_ages = [
        age
        for hit, age in (
            (overview_result.cache_hit, overview_result.cache_age_seconds),
            (explore.cache_hit, explore.cache_age_seconds),
            (entity_result.cache_hit, entity_result.cache_age_seconds),
        )
        if hit and age is not None
    ]
    cache_hit = bool(cache_ages)
    cache_age_seconds = max(cache_ages) if cache_ages else None

    if (
        has_slice
        and lens == "overview"
        and overview_result.status != "ready"
    ):
        pipeline_stats = {"count": 0, "millions": 0.0}
        explain_avail = None
    overview_verdict = (
        overview_capture_verdict(
            overview_result.overview,
            query=query,
            pipeline=pipeline_stats,
            expiring_rows=explore.rows,
        )
        if overview_result.status == "ready" and lens == "overview"
        else {"cards": (), "shipley": ()}
    )

    agency_overview: dict[str, Any] = {}
    agency_sam = SamExploreResult(
        query=None,
        summary="",
        notices=(),
        status="idle",
        error=None,
        configured=False,
    )
    if (
        lens == "agency"
        and entity_result.status == "ready"
        and entity_result.entity
        and entity_result.entity.is_active()
    ):
        agency_overview = agency_overview_brief(
            entity_result.entity,
            entity_result.profile,
            recompete_rows=entity_result.profile.get("recompete_rows"),
        )
        agency_sam = await fetch_agency_sam_forward(
            settings,
            entity_result.entity,
            slice_query,
            match_naics=sam_match_naics,
        )

    return SlicePanelContext(
        facet_form=facet_form,
        active_lens=lens,
        lens_tabs=INSIGHTS_LENS_TABS,
        query=query,
        has_slice=has_slice,
        overview=overview_result.overview,
        overview_ready=overview_result.status == "ready",
        overview_idle=overview_result.status == "idle",
        overview_error=overview_result.error,
        overview_verdict=overview_verdict,
        pipeline_stats=pipeline_stats,
        explore=explore,
        sam_explore=SamExploreResult(
            query=None,
            summary="",
            notices=(),
            status="idle",
            error=None,
            configured=False,
        ),
        sam_form={},
        entity=entity_result.entity if entity_result.entity and entity_result.entity.is_active() else entity,
        agency_entity=agency_entity,
        competitor_entity=competitor_entity,
        agency_overview=agency_overview,
        entity_profile=entity_result.profile,
        entity_ready=entity_result.status == "ready",
        entity_idle=entity_result.status == "idle",
        entity_error=entity_result.error,
        agency_sam_forward=agency_sam,
        sam_match_naics=sam_match_naics,
        cache_hit=cache_hit,
        cache_age_seconds=cache_age_seconds,
        slice_explain=explain_avail,
    )