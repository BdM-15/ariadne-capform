"""Packet fill workflows — agent route chips for open data elements (Phase 14j / 20 prep)."""

from __future__ import annotations

import uuid
from typing import Any

from thread.domain.packet_answer_sources import (
    ACTION_PLAN,
    CLEW,
    CRM,
    FINANCE,
    GROK,
    HUMAN,
    MINERU,
    PG_INTEL,
    SAM_MCP,
    USASPENDING_MCP,
    VAULT,
    WEB_RESEARCH,
)

_EXECUTABLE_FILL_SOURCES = frozenset({PG_INTEL, USASPENDING_MCP})

_SOURCE_META: dict[str, dict[str, str]] = {
    HUMAN: {"label": "Operator entry", "icon": "pen-line"},
    SAM_MCP: {"label": "SAM.gov", "icon": "file-search"},
    USASPENDING_MCP: {"label": "USAspending MCP", "icon": "landmark"},
    PG_INTEL: {"label": "USAspending intel", "icon": "chart-no-axes-combined"},
    CLEW: {"label": "Clew trace", "icon": "git-branch"},
    VAULT: {"label": "Vault knowledge", "icon": "book-open"},
    WEB_RESEARCH: {"label": "Web research", "icon": "globe"},
    GROK: {"label": "Grok synthesis", "icon": "sparkles"},
    MINERU: {"label": "MinerU parse", "icon": "file-text"},
    CRM: {"label": "CRM import", "icon": "database"},
    FINANCE: {"label": "Finance model", "icon": "calculator"},
    ACTION_PLAN: {"label": "Action plan", "icon": "list-checks"},
}


def _field_is_open(field: dict[str, Any]) -> bool:
    value = (field.get("value") or "").strip()
    status = field.get("status", "")
    return not value or status in ("unanswered", "gap")


def workflow_actions_for_field(
    field: dict[str, Any],
    *,
    opp_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    """Action chips an operator (or Phase 20 agent) can run to fill one element."""
    oid = str(opp_id)
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for src in field.get("answer_sources") or ():
        if src in seen:
            continue
        seen.add(src)
        meta = _SOURCE_META.get(src, {"label": src.replace("_", " ").title(), "icon": "plug"})
        href = "#"
        enabled = True
        stub = False
        executable = src in _EXECUTABLE_FILL_SOURCES and bool(field.get("deterministic"))
        if src == SAM_MCP:
            href = "/insights"
        elif src in (PG_INTEL, USASPENDING_MCP):
            href = "/insights"
            executable = executable or field.get("field_key") in (
                "prime_name",
                "customer_name",
                "total_contract_value",
                "financial_contract_type",
                "contract_end_date",
                "competition_company_1_name",
            )
        elif src == CLEW:
            href = "/clew"
        elif src == VAULT:
            href = "/knowledge"
        elif src == WEB_RESEARCH:
            href = "/insights"
        elif src == GROK:
            href = "/insights"
            stub = True
        elif src == MINERU:
            href = "/"
            stub = not executable
        elif src == CRM:
            enabled = False
            stub = True
        elif src == FINANCE:
            enabled = False
            stub = True
        elif src == ACTION_PLAN:
            href = f"/capture/{oid}?slide=slide_14_actions#action-matrix"
        elif src == HUMAN:
            href = f"#field-{field['field_key']}"
        actions.append(
            {
                "id": src,
                "label": meta["label"],
                "icon": meta["icon"],
                "href": href,
                "enabled": enabled,
                "stub": stub,
                "anchor": href.startswith("#"),
                "executable": executable,
            }
        )

    if field.get("route_kind") == "research_or_mcp" and not any(a["id"] == WEB_RESEARCH for a in actions):
        actions.append(
            {
                "id": "research_lane",
                "label": "Run research",
                "icon": "search",
                "href": "/insights",
                "enabled": True,
                "stub": False,
                "anchor": False,
            }
        )

    actions.append(
        {
            "id": "inspector",
            "label": "Edit in inspector",
            "icon": "pencil",
            "href": f"#field-{field['field_key']}",
            "enabled": True,
            "stub": False,
            "anchor": True,
        }
    )
    return actions


def build_slide_fill_workflows(
    fields: list[dict[str, Any]],
    *,
    opp_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    """Open data elements on the active slide with agentic fill routes."""
    workflows: list[dict[str, Any]] = []
    for field in fields:
        if not _field_is_open(field):
            continue
        workflows.append(
            {
                "field_key": field["field_key"],
                "label": field["label"],
                "question": field.get("question") or "",
                "route_kind": field.get("route_kind", ""),
                "route_hint": field.get("route_hint") or "",
                "deterministic": field.get("deterministic", False),
                "status": field.get("status", "unanswered"),
                "actions": workflow_actions_for_field(field, opp_id=opp_id),
            }
        )
    return workflows