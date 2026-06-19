"""Answer-source stubs for packet fields — Phase 14f / Phase 20 route-driven fill prep.

Each data element is a candidate for agentic fill. Sources chain: deterministic MCP/PG
outputs may feed Grok synthesis or downstream skills/research.
"""

from __future__ import annotations

from dataclasses import dataclass

from thread.domain.enums import PacketFieldRouteKind

# Stable source identifiers (MCP servers, skills, lanes)
HUMAN = "human_input"
SAM_MCP = "sam_mcp"
USASPENDING_MCP = "usaspending_mcp"
PG_INTEL = "pg_intel"
CLEW = "clew_intel"
VAULT = "vault_knowledge"
WEB_RESEARCH = "web_research"
GROK = "grok_synthesis"
MINERU = "mineru_parse"
CRM = "crm_import"
FINANCE = "finance_model"
COMPUTED = "computed"
ACTION_PLAN = "capture_action_plan"


@dataclass(frozen=True)
class AnswerRouteStub:
    """How agentic flows can fill one packet field (stub — Phase 20 wires execution)."""

    sources: tuple[str, ...]
    hint: str
    deterministic: bool = False
    feeds: tuple[str, ...] = ()


_ROUTE_DEFAULTS: dict[PacketFieldRouteKind, AnswerRouteStub] = {
    PacketFieldRouteKind.SOURCE_BACKED_ANSWER: AnswerRouteStub(
        (HUMAN, SAM_MCP),
        "SAM notice / solicitation evidence or operator entry",
    ),
    PacketFieldRouteKind.SOURCE_PROFILE_LOOKUP: AnswerRouteStub(
        (USASPENDING_MCP, PG_INTEL),
        "USAspending award lookup on opportunity facet",
        deterministic=True,
        feeds=(CLEW,),
    ),
    PacketFieldRouteKind.RESEARCH_OR_MCP: AnswerRouteStub(
        (PG_INTEL, CLEW, WEB_RESEARCH, VAULT),
        "Intel slice + Clew trace + vault entity pages + bounded web research",
        feeds=(GROK,),
    ),
    PacketFieldRouteKind.MODEL_SYNTHESIS: AnswerRouteStub(
        (VAULT, PG_INTEL, CLEW, WEB_RESEARCH, GROK),
        "Evidence bundle → Grok prose/decision synthesis (review-gated)",
        feeds=(GROK,),
    ),
    PacketFieldRouteKind.CUSTOMER_CALL_PLAN: AnswerRouteStub(
        (WEB_RESEARCH, VAULT, GROK),
        "Customer research lens + vault agency notes → call-plan assist",
        feeds=(GROK,),
    ),
    PacketFieldRouteKind.COMPUTED: AnswerRouteStub(
        (COMPUTED,),
        "Derived from other packet fields — no direct fill",
        deterministic=True,
    ),
}


def resolve_answer_route(
    route_kind: PacketFieldRouteKind,
    *,
    sources: tuple[str, ...] = (),
    hint: str = "",
    deterministic: bool = False,
    feeds: tuple[str, ...] = (),
) -> AnswerRouteStub:
    base = _ROUTE_DEFAULTS.get(
        route_kind,
        AnswerRouteStub((HUMAN,), "Operator entry"),
    )
    return AnswerRouteStub(
        sources=sources or base.sources,
        hint=hint or base.hint,
        deterministic=deterministic if deterministic or sources else base.deterministic,
        feeds=feeds or base.feeds,
    )