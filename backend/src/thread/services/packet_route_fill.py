"""Phase 20 — route-driven packet field fill (PG intel, SAM MCP, Grok synthesis)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from html import unescape
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import Opportunity, PacketFieldAnswer, PacketFieldDefinition
from thread.domain.enums import PacketFieldValueKind
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
from thread.domain.packet_field_seed import DECISION_IMPACT_PRIORITY, FIELD_SEED_BY_KEY
from thread.intel.pg_queries import get_award_profile
from thread.llm.router import CompletionResult, LlmRouterError, LlmTaskKind, complete
from thread.mcp.service import MCPService
from thread.services.opportunities import get_opportunity, update_packet_field
from thread.services.sam_monitor import (
    SAM_SEARCH_TOOL,
    SamNoticeLead,
    parse_notices_from_mcp_output,
)
from thread.ui.formatters import format_money

_PG_FILL_SOURCES = frozenset({PG_INTEL, USASPENDING_MCP})
_SAM_DESCRIPTION_TOOL = "get_opportunity_description"
_SAM_DESCRIPTION_FIELDS = frozenset(
    {"primary_scope_description", "special_considerations", "opportunity_context"}
)

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
    decision_impact: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    blocked: bool = False
    blocked_reason: str = ""


_PREREQ_LABELS: dict[str, str] = {
    "award_key": "award link",
    "notice_id": "SAM notice",
    "mineru": "parsed solicitation",
}


def _impact_sort_key(tags: tuple[str, ...]) -> tuple[int, str]:
    if not tags:
        return (99, "")
    best = min(DECISION_IMPACT_PRIORITY.get(tag, 99) for tag in tags)
    primary = next(tag for tag in tags if DECISION_IMPACT_PRIORITY.get(tag, 99) == best)
    return (best, primary)


def _prerequisite_met(prereq: str, context: dict[str, Any]) -> bool:
    if prereq == "award_key":
        return bool((context.get("award_key") or "").strip())
    if prereq == "notice_id":
        return bool((context.get("notice_id") or "").strip())
    if prereq == "mineru":
        return bool(context.get("has_mineru"))
    return True


def _blocked_reason(missing: tuple[str, ...]) -> str:
    labels = [_PREREQ_LABELS.get(item, item) for item in missing]
    return "Needs " + ", ".join(labels)


def _award_key_from_opp(opp: Opportunity) -> str | None:
    prov = opp.intel_provenance or {}
    key = prov.get("award_key")
    return str(key).strip() if key else None


def _notice_id_from_opp(opp: Opportunity) -> str | None:
    prov = opp.intel_provenance or {}
    notice_id = prov.get("notice_id")
    return str(notice_id).strip() if notice_id else None


def _sam_configured(settings: Settings) -> bool:
    mcp = MCPService(settings)
    sam = next((s for s in mcp.list_servers() if s["id"] == "sam_gov"), None)
    return bool(sam and sam["configured"])


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_description_output(raw: str | dict[str, Any]) -> str:
    payload: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return _strip_html(text)
    if isinstance(payload, dict):
        for key in ("description", "content", "html", "text", "body"):
            val = payload.get(key)
            if val:
                return _strip_html(str(val))
    return _strip_html(str(payload))


def _value_kind_instruction(value_kind: str) -> str:
    try:
        kind = PacketFieldValueKind(value_kind)
    except ValueError:
        return "Return a concise plain-text answer."
    return {
        PacketFieldValueKind.TEXT: "Return a short plain-text phrase (no bullets).",
        PacketFieldValueKind.PROSE: "Return 2–5 sentences of plain prose (no markdown).",
        PacketFieldValueKind.ENTITY: "Return the organization or entity name only.",
        PacketFieldValueKind.DATE: "Return a single date as MM/DD/YYYY when known.",
        PacketFieldValueKind.MONEY: "Return a dollar amount like $1,234,567 (no narrative).",
        PacketFieldValueKind.PERCENTAGE: "Return a percent like 35% (number + %).",
        PacketFieldValueKind.DECISION: "Return one of: Proceed, Hold, or No-bid.",
        PacketFieldValueKind.BOOLEAN: "Return Yes or No.",
    }.get(kind, "Return a concise plain-text answer.")


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


def build_data_needs(
    fields: list[dict[str, Any]],
    *,
    limit: int = 12,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MS-critical open elements for workspace data-needs strip."""
    ctx = context or {}
    open_items: list[DataNeedItem] = []
    for field in fields:
        value = (field.get("value") or "").strip()
        status = field.get("status", "")
        if value and status not in ("unanswered", "gap"):
            continue
        prereqs = tuple(field.get("prerequisites") or ())
        missing = tuple(p for p in prereqs if not _prerequisite_met(p, ctx))
        open_items.append(
            DataNeedItem(
                field_key=field["field_key"],
                label=field.get("label") or field["field_key"],
                slide=field.get("reference_slide") or "",
                route_kind=field.get("route_kind") or "",
                deterministic=bool(field.get("deterministic")),
                decision_impact=tuple(field.get("decision_impact") or ()),
                prerequisites=prereqs,
                blocked=bool(missing),
                blocked_reason=_blocked_reason(missing) if missing else "",
            )
        )
    open_items.sort(
        key=lambda item: (
            1 if item.blocked else 0,
            0 if item.deterministic else 1,
            _impact_sort_key(item.decision_impact),
            item.label,
        )
    )
    ready_count = sum(1 for item in open_items if not item.blocked)
    blocked_count = len(open_items) - ready_count
    return {
        "count": len(open_items),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "gaps": [
            {
                "field_key": item.field_key,
                "label": item.label,
                "slide": item.slide,
                "route_kind": item.route_kind,
                "deterministic": item.deterministic,
                "decision_impact": list(item.decision_impact),
                "blocked": item.blocked,
                "blocked_reason": item.blocked_reason,
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
    if source == SAM_MCP:
        return await _fill_from_sam_mcp(settings, opp, field_key)
    if source == GROK:
        return await _fill_from_grok(session, settings, opp, field_key, seed)
    if source == WEB_RESEARCH:
        return RouteFillResult(
            ok=True,
            message="Open Insights to research this element",
            redirect_url="/insights",
        )
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


async def _fetch_sam_notice(settings: Settings, notice_id: str) -> SamNoticeLead | None:
    end = date.today()
    start = end - timedelta(days=364)
    fmt = "%m/%d/%Y"
    mcp = MCPService(settings)
    result = await mcp.invoke(
        "sam_gov",
        SAM_SEARCH_TOOL,
        {
            "posted_from": start.strftime(fmt),
            "posted_to": end.strftime(fmt),
            "notice_id": notice_id,
            "limit": 5,
        },
    )
    if not result.get("ok"):
        return None
    output = result.get("output")
    raw = json.dumps(output) if isinstance(output, dict) else str(output or "")
    leads = parse_notices_from_mcp_output(raw)
    for lead in leads:
        if lead.notice_id == notice_id:
            return lead
    return leads[0] if leads else None


async def _fetch_sam_description(settings: Settings, notice_id: str) -> str | None:
    mcp = MCPService(settings)
    result = await mcp.invoke("sam_gov", _SAM_DESCRIPTION_TOOL, {"notice_id": notice_id})
    if not result.get("ok"):
        return None
    output = result.get("output")
    if isinstance(output, dict):
        text = _parse_description_output(output)
    else:
        text = _parse_description_output(str(output or ""))
    return text[:8000] if text else None


def _format_sam_notice_value(field_key: str, notice: SamNoticeLead, description: str | None) -> str | None:
    if field_key == "opportunity_name":
        return notice.title
    if field_key == "proposal_due_date":
        return notice.response_deadline
    if field_key in ("rfp_release_date", "draft_rfp_date"):
        return notice.posted_date
    if field_key == "customer_name":
        return notice.agency
    if field_key == "small_business_goal":
        return notice.set_aside
    if field_key == "kbr_role":
        if notice.set_aside:
            return f"Sub teaming likely — {notice.set_aside} set-aside"
        return "Prime contractor posture (no set-aside on notice)"
    if field_key in _SAM_DESCRIPTION_FIELDS and description:
        if field_key == "special_considerations" and notice.set_aside:
            return f"Set-aside: {notice.set_aside}. {description[:3500]}"
        return description[:4000]
    return None


async def _fill_from_sam_mcp(
    settings: Settings,
    opp: Opportunity,
    field_key: str,
) -> RouteFillResult:
    if not settings.enable_live_mcps:
        return RouteFillResult(ok=False, message="Live MCP disabled — set ENABLE_LIVE_MCPS=true")
    if not _sam_configured(settings):
        return RouteFillResult(ok=False, message="SAM.gov MCP not configured — add SAM_GOV_API_KEY")

    notice_id = _notice_id_from_opp(opp)
    if not notice_id:
        return RouteFillResult(
            ok=False,
            message="No notice_id on opportunity — Track from SAM notice on Insights first",
        )

    notice = await _fetch_sam_notice(settings, notice_id)
    if notice is None:
        return RouteFillResult(
            ok=False,
            message=f"SAM MCP returned no notice for {notice_id[:16]}…",
        )

    description: str | None = None
    if field_key in _SAM_DESCRIPTION_FIELDS:
        description = await _fetch_sam_description(settings, notice_id)

    value = _format_sam_notice_value(field_key, notice, description)
    if not value:
        return RouteFillResult(
            ok=False,
            message=f"SAM notice has no mapped value for {field_key}",
        )

    provenance = (
        {
            "kind": "sam_mcp",
            "ref": notice_id,
            "excerpt": f"{field_key} from SAM.gov notice {notice.solicitation_number or notice_id[:12]}",
        },
    )
    return RouteFillResult(ok=True, value=value, provenance=provenance, message="Filled from SAM.gov")


async def _filled_packet_context(
    session: AsyncSession,
    opp_id: uuid.UUID,
    *,
    limit: int = 24,
) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(PacketFieldAnswer, PacketFieldDefinition)
            .join(PacketFieldDefinition, PacketFieldDefinition.key == PacketFieldAnswer.field_key)
            .where(PacketFieldAnswer.opportunity_id == opp_id)
        )
    ).all()
    filled: list[dict[str, str]] = []
    for answer, defn in rows:
        value = (answer.value or "").strip()
        if not value:
            continue
        filled.append({"field_key": answer.field_key, "label": defn.label, "value": value[:500]})
    filled.sort(key=lambda item: item["label"])
    return filled[:limit]


async def _grok_context_bundle(
    session: AsyncSession,
    settings: Settings,
    opp: Opportunity,
    field_key: str,
    seed: Any,
) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "opportunity_name": opp.name,
        "field_key": field_key,
        "field_label": seed.label,
        "question": seed.question,
        "value_kind": seed.value_kind.value,
        "route_hint": seed.answer_route.hint if seed.answer_route else "",
        "intel_provenance": opp.intel_provenance or {},
        "filled_fields": await _filled_packet_context(session, opp.id),
    }
    award_key = _award_key_from_opp(opp)
    if award_key:
        profile = await get_award_profile(session, award_key)
        if profile:
            bundle["award_profile"] = {
                key: profile.get(key)
                for key in ("recipient", "agency", "obligation", "pricing", "end_date", "naics")
                if profile.get(key) is not None
            }
    notice_id = _notice_id_from_opp(opp)
    if notice_id and settings.enable_live_mcps and _sam_configured(settings):
        notice = await _fetch_sam_notice(settings, notice_id)
        if notice:
            bundle["sam_notice"] = {
                "notice_id": notice.notice_id,
                "title": notice.title,
                "agency": notice.agency,
                "response_deadline": notice.response_deadline,
                "set_aside": notice.set_aside,
                "naics_code": notice.naics_code,
            }
    return bundle


def _build_grok_messages(bundle: dict[str, Any]) -> list[dict[str, str]]:
    context_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "You fill one field of a federal capture briefing packet — the living decision document. "
                "Return ONLY the field value with no preamble, labels, or markdown fences. "
                f"{_value_kind_instruction(bundle['value_kind'])} "
                "Use provided evidence; state uncertainty briefly inline only when evidence is thin. "
                "Output is a CANDIDATE pending human review."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Field: {bundle['field_label']} ({bundle['field_key']})\n"
                f"Question: {bundle['question']}\n"
                f"Route hint: {bundle.get('route_hint') or 'n/a'}\n\n"
                f"Context JSON:\n{context_json[:12000]}"
            ),
        },
    ]


async def _fill_from_grok(
    session: AsyncSession,
    settings: Settings,
    opp: Opportunity,
    field_key: str,
    seed: Any,
) -> RouteFillResult:
    try:
        bundle = await _grok_context_bundle(session, settings, opp, field_key, seed)
        result: CompletionResult = await complete(
            settings,
            task_kind=LlmTaskKind.REASONING,
            messages=_build_grok_messages(bundle),
            max_tokens=min(settings.llm_max_output_tokens, 2048),
        )
    except LlmRouterError as exc:
        return RouteFillResult(ok=False, message=str(exc))

    value = (result.text or "").strip()
    if not value:
        return RouteFillResult(ok=False, message="Grok returned an empty synthesis")

    if value.startswith("```"):
        value = re.sub(r"^```[a-z]*\s*", "", value)
        value = re.sub(r"\s*```$", "", value).strip()

    provenance = (
        {
            "kind": "grok_synthesis",
            "ref": f"{result.provider.value}:{result.model}",
            "excerpt": f"{field_key} synthesized from packet context",
        },
    )
    return RouteFillResult(ok=True, value=value, provenance=provenance, message="Synthesized by Grok")


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
    label = {
        PG_INTEL: "USAspending intel",
        USASPENDING_MCP: "USAspending MCP",
        SAM_MCP: "SAM.gov",
        GROK: "Grok synthesis",
    }.get(source, source)
    return RouteFillResult(
        ok=True,
        value=result.value,
        provenance=result.provenance,
        message=f"Filled {field_key} from {label} — pending review",
    )