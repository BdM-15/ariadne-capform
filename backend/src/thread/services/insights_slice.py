"""Phase 17e — Insights lens tab panel (shared slice context)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery
from thread.services.insights_explore import RadarExploreResult, SamExploreResult, explore_radar, explore_sam
from thread.services.insights_overview import OverviewResult, build_overview

INSIGHTS_LENS_TABS: tuple[dict[str, str], ...] = (
    {"id": "overview", "label": "Overview"},
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


def facet_form_from_params(
    *,
    agency: str = "",
    sub_agency: str = "",
    recipient: str = "",
    naics_codes: str = "",
    psc_codes: str = "",
) -> dict[str, str]:
    return {
        "agency": agency.strip(),
        "sub_agency": sub_agency.strip(),
        "recipient": recipient.strip(),
        "naics_codes": naics_codes.strip(),
        "psc_codes": psc_codes.strip(),
    }


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
    run: bool = False,
    sam_title: str = "",
    sam_agency_keyword: str = "",
    sam_naics_code: str = "",
    sam_psc_code: str = "",
    sam_days_back: int = 14,
    sam_run: bool = False,
) -> SlicePanelContext:
    if lens not in {t["id"] for t in INSIGHTS_LENS_TABS}:
        lens = "overview"

    facet_form = facet_form_from_params(
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
    )

    overview_result: OverviewResult = await build_overview(
        session,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        run=run,
    )

    explore = await explore_radar(
        session,
        settings,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        naics_codes=naics_codes,
        psc_codes=psc_codes,
        run=run,
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
    )