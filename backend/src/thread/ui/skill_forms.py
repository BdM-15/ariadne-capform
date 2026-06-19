"""Skill run form helpers for Tools → Agent Skills (Phase 12l)."""

from __future__ import annotations

import json
from typing import Any

from starlette.datastructures import FormData

WIRED_SKILL_IDS = frozenset({"clew_intel", "mcp_federal_tools", "skill-creator", "idea_capturer"})

CLEW_MODES = (
    ("money_flow", "Money flow"),
    ("spend_trend", "Spend trend"),
    ("teaming", "Teaming (prime→sub)"),
    ("recipient_landscape", "Recipient landscape"),
    ("snapshot", "Snapshot (legacy NAICS)"),
    ("expiring", "Expiring contracts"),
    ("market", "Market summary"),
)


def skill_is_wired(skill_id: str) -> bool:
    return skill_id in WIRED_SKILL_IDS


def payload_from_form(skill_id: str, form: FormData) -> dict[str, Any]:
    if skill_id == "clew_intel":
        payload: dict[str, Any] = {"mode": str(form.get("mode") or "money_flow")}
        for key in ("agency", "sub_agency", "recipient", "naics_codes", "psc_codes", "naics"):
            raw = form.get(key)
            if raw is None:
                continue
            value = str(raw).strip()
            if value:
                payload[key] = value
        limit = form.get("limit")
        if limit and str(limit).strip().isdigit():
            payload["limit"] = int(str(limit).strip())
        return payload

    if skill_id == "mcp_federal_tools":
        payload = {
            "server": str(form.get("server") or "").strip(),
            "tool": str(form.get("tool") or "").strip(),
        }
        args_raw = str(form.get("arguments") or "").strip()
        if args_raw:
            try:
                payload["arguments"] = json.loads(args_raw)
            except json.JSONDecodeError as exc:
                payload["arguments"] = {}
                payload["_parse_error"] = str(exc)
        else:
            payload["arguments"] = {}
        return payload

    if skill_id == "idea_capturer":
        payload = {"dump": str(form.get("dump") or "").strip()}
        tags = str(form.get("tags") or "").strip()
        context = str(form.get("context") or "").strip()
        if tags:
            payload["tags"] = tags
        if context:
            payload["context"] = context
        return payload

    return {}