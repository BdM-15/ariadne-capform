"""Phase 17e — Insights lens tab panel (shared slice context)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.facet_query import ADVANCED_FACET_FIELDS, InsightFacetQuery
from thread.services.insights_entity import EntityContext, EntityProfileResult, build_entity_profile, entity_from_params
from thread.services.insights_explore import RadarExploreResult, SamExploreResult, explore_radar, explore_sam
from thread.services.insights_overview import OverviewResult, build_overview

INSIGHTS_LENS_TABS: tuple[dict[str, str], ...] = (
    {"id": "overview", "label": "Overview"},
    {"id": "agency", "label": "Agency"},
    {"id": "competitor", "label": "Competitor"},
    {"id": "recompete", "label": "Recompete"},
    {"id": "competition", "label": "Competition"},
    {"id": "trace", "label": "Trace"},
    {"id": "sam", "label": "Live (SAM)"},
)


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
    explore: RadarExploreResult
    sam_explore: SamExploreResult
    sam_form: dict[str, str]
    entity: EntityContext | None
    entity_profile: dict[str, Any]
    entity_ready: bool
    entity_idle: bool
    entity_error: str | None
    cache_hit: bool
    cache_age_seconds: float | None


def facet_form_from_params(
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
) -> dict[str, str]:
    form = {
        "agency": agency.strip(),
        "sub_agency": sub_agency.strip(),
        "recipient": recipient.strip(),
        "naics_codes": naics_codes.strip(),
        "psc_codes": psc_codes.strip(),
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
    awarding_office: str = "",
    funding_office: str = "",
    recipient_uei: str = "",
    pop_state: str = "",
    extent_competed: str = "",
    type_of_set_aside: str = "",
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
) -> SlicePanelContext:
    if lens not in {t["id"] for t in INSIGHTS_LENS_TABS}:
        lens = "overview"

    facet_form = facet_form_from_params(
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
    )
    facet_kwargs = {
        "agency": agency,
        "sub_agency": sub_agency,
        "recipient": recipient,
        "naics_codes": naics_codes,
        "psc_codes": psc_codes,
        "awarding_office": awarding_office,
        "funding_office": funding_office,
        "recipient_uei": recipient_uei,
        "pop_state": pop_state,
        "extent_competed": extent_competed,
        "type_of_set_aside": type_of_set_aside,
    }

    overview_result: OverviewResult = await build_overview(
        session,
        settings,
        run=run,
        **facet_kwargs,
    )

    entity = entity_from_params(
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
    )
    explore = await explore_radar(
        session,
        settings,
        run=run,
        entity_kind=entity_kind,
        entity_value=entity_value,
        entity_scope=entity_scope,
        **facet_kwargs,
    )

    sam_form = {
        "title": sam_title.strip(),
        "agency_keyword": (sam_agency_keyword or agency).strip(),
        "naics_code": (sam_naics_code or naics_codes.split(",")[0] if naics_codes else "").strip(),
        "psc_code": sam_psc_code.strip(),
        "days_back": str(sam_days_back),
    }
    sam_explore = await explore_sam(
        settings,
        title=sam_form["title"],
        agency_keyword=sam_form["agency_keyword"],
        naics_code=sam_form["naics_code"],
        psc_code=sam_form["psc_code"],
        days_back=sam_days_back,
        run=sam_run and lens == "sam",
    )

    query = overview_result.query
    has_slice = bool(query and query.has_filters())

    entity_result: EntityProfileResult = await build_entity_profile(
        session,
        settings,
        query,
        entity,
        lens=lens,
    )
    if lens in {"agency", "competitor"} and entity is None:
        entity_result = EntityProfileResult(
            entity=EntityContext(kind=lens, value="", scope="agency"),
            profile={"idle": True},
            status="idle",
        )

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
        explore=explore,
        sam_explore=sam_explore,
        sam_form=sam_form,
        entity=entity_result.entity if entity_result.entity and entity_result.entity.is_active() else entity,
        entity_profile=entity_result.profile,
        entity_ready=entity_result.status == "ready",
        entity_idle=entity_result.status == "idle",
        entity_error=entity_result.error,
        cache_hit=cache_hit,
        cache_age_seconds=cache_age_seconds,
    )