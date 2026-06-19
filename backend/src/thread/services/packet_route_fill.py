"""Phase 20 — route-driven packet field fill (PG intel MVP)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import Opportunity
from thread.domain.packet_answer_sources import (
    CLEW,
    GROK,
    MINERU,
    PG_INTEL,
    SAM_MCP,
    USASPENDING_MCP,
    VAULT,
    WEB_RESEARCH,
)
from thread.domain.packet_field_seed import FIELD_SEED_BY_KEY
from thread.intel.pg_queries import get_award_profile
from thread.services.opportunities import get_opportunity, update_packet_field
from thread.ui.formatters import format_money

_PG_FILL_SOURCES = frozenset({PG_INTEL, USASPENDING_MCP})

_FIELD_FROM_AWARD: dict[str, str] = {
    "prime_name": "recipient",
    "customer_name": "agency",
    "total_contract_value": "obligation",
    "financial_contract_type": "pricing",
    "contract_end_date": "end_date",
    "award_date": "end_date",
    "competition_company_1_name": "recipient",
    "opportunity_name": "recipient",
}


@dataclass(frozen=True)
class RouteFillResult:
    ok: bool
    message: str = ""
    value: str = ""
    provenance: tuple[dict[str, str], ...] = ()
    redirect_url: str | None = None


@dataclass(frozen=True)
class DataNeedItem:
    field_key: str
    label: str
    slide: str
    route_kind: str
    deterministic: bool


def _award_key_from_opp(opp: Opportunity) -> str | None:
    prov = opp.intel_provenance or {}
    key = prov.get("award_key")
    return str(key).strip() if key else None


def _format_award_value(field_key: str, profile: dict[str, Any]) -> str | None:
    attr = _FIELD_FROM_AWARD.get(field_key)
    if not attr:
        return None
    raw = profile.get(attr)
    if raw is None or raw == "":
        return None
    if field_key == "total_contract_value":
        return format_money(raw if isinstance(raw, (int, float)) else float(raw))
    return str(raw).strip()


def build_data_needs(fields: list[dict[str, Any]], *, limit: int = 12) -> dict[str, Any]:
    """MS-critical open elements for workspace data-needs strip."""
    open_items: list[DataNeedItem] = []
    for field in fields:
        value = (field.get("value") or "").strip()
        status = field.get("status", "")
        if value and status not in ("unanswered", "gap"):
            continue
        open_items.append(
            DataNeedItem(
                field_key=field["field_key"],
                label=field.get("label") or field["field_key"],
                slide=field.get("reference_slide") or "",
                route_kind=field.get("route_kind") or "",
                deterministic=bool(field.get("deterministic")),
            )
        )
    open_items.sort(key=lambda item: (0 if item.deterministic else 1, item.label))
    return {
        "count": len(open_items),
        "gaps": [
            {
                "field_key": item.field_key,
                "label": item.label,
                "slide": item.slide,
                "route_kind": item.route_kind,
                "deterministic": item.deterministic,
            }
            for item in open_items[:limit]
        ],
        "overflow": max(0, len(open_items) - limit),
    }


def _clew_prefill_url(opp_id: uuid.UUID, field_key: str) -> str:
    params = urlencode({"opp": str(opp_id), "field": field_key})
    return f"/clew?{params}"


async def run_packet_route_fill(
    session: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
    field_key: str,
    source: str,
) -> RouteFillResult:
    opp = await get_opportunity(session, opp_id)
    if opp is None:
        return RouteFillResult(ok=False, message="Opportunity not found")

    seed = FIELD_SEED_BY_KEY.get(field_key)
    if seed is None:
        return RouteFillResult(ok=False, message=f"Unknown field: {field_key}")

    if source in _PG_FILL_SOURCES:
        return await _fill_from_pg_intel(session, opp, field_key)

    if source == CLEW:
        return RouteFillResult(
            ok=True,
            message="Open Clew to trace money path for this element",
            redirect_url=_clew_prefill_url(opp_id, field_key),
        )
    if source == VAULT:
        return RouteFillResult(
            ok=True,
            message="Open Knowledge vault to cite entity notes",
            redirect_url="/knowledge",
        )
    if source in (SAM_MCP, WEB_RESEARCH):
        return RouteFillResult(
            ok=True,
            message="Open Insights to research this element",
            redirect_url="/insights",
        )
    if source == GROK:
        return RouteFillResult(ok=False, message="Grok synthesis fill — wire in Phase 20b")
    if source == MINERU:
        if settings.mineru_enabled:
            return RouteFillResult(
                ok=True,
                message="Drop solicitation PDF in global capture FAB",
                redirect_url="/",
            )
        return RouteFillResult(ok=False, message="Enable MINERU_ENABLED and attach docs via capture FAB")

    return RouteFillResult(ok=False, message=f"Fill route not wired for source: {source}")


async def _fill_from_pg_intel(
    session: AsyncSession,
    opp: Opportunity,
    field_key: str,
) -> RouteFillResult:
    award_key = _award_key_from_opp(opp)
    if not award_key:
        return RouteFillResult(
            ok=False,
            message="No award_key on opportunity — Track from Insights signal first",
        )

    profile = await get_award_profile(session, award_key)
    if profile is None:
        return RouteFillResult(
            ok=False,
            message=f"No PG intel row for award_key {award_key[:24]}… (migration may still be running)",
        )

    value = _format_award_value(field_key, profile)
    if not value:
        return RouteFillResult(
            ok=False,
            message=f"PG award profile has no value for {field_key}",
        )

    provenance = (
        {
            "kind": "pg_intel",
            "ref": award_key,
            "excerpt": f"{field_key} from intel_usaspending_prime",
        },
    )
    return RouteFillResult(ok=True, value=value, provenance=provenance, message="Filled from PG intel")


async def apply_route_fill(
    session: AsyncSession,
    settings: Settings,
    opp_id: uuid.UUID,
    field_key: str,
    source: str,
) -> RouteFillResult:
    """Execute fill and persist candidate answer when value produced."""
    result = await run_packet_route_fill(session, settings, opp_id, field_key, source)
    if not result.ok or not result.value:
        return result

    await update_packet_field(
        session,
        opp_id,
        field_key,
        result.value,
        as_candidate=True,
        provenance=list(result.provenance),
    )
    return RouteFillResult(
        ok=True,
        value=result.value,
        provenance=result.provenance,
        message=f"Filled {field_key} from USAspending intel — pending review",
    )