"""Flexible insight queries — any facet combo; no default NAICS or preset dimension."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings
from thread.intel.sql_expressions import AGENCY_EXPR, naics_filter


@dataclass(frozen=True)
class InsightFacetQuery:
    """Operator-defined search — NAICS is one optional facet among many."""

    id: str
    name: str
    naics_codes: tuple[str, ...] = ()
    agency: str | None = None
    sub_agency: str | None = None
    recipient: str | None = None
    psc_codes: tuple[str, ...] = ()
    description: str = ""

    def has_filters(self) -> bool:
        return bool(
            self.naics_codes or self.agency or self.sub_agency or self.recipient or self.psc_codes
        )


def _queries_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "insight_queries.json"


def _active_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "active_insight_query.json"


def _parse_codes(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [c.strip() for c in re.split(r"[,;\s]+", raw) if c.strip()]
    elif isinstance(raw, list):
        items = [str(c).strip() for c in raw if str(c).strip()]
    else:
        return ()
    return tuple(items)


def query_from_dict(raw: dict[str, Any]) -> InsightFacetQuery | None:
    query_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or query_id).strip()
    if not query_id or not name:
        return None
    naics = _parse_codes(raw.get("naics_codes") or raw.get("naics"))
    psc = _parse_codes(raw.get("psc_codes") or raw.get("psc"))
    agency = (str(raw["agency"]).strip() or None) if raw.get("agency") else None
    sub_agency = (str(raw["sub_agency"]).strip() or None) if raw.get("sub_agency") else None
    recipient = (
        (str(raw["recipient"]).strip() or None)
        if raw.get("recipient")
        else (str(raw["incumbent"]).strip() or None) if raw.get("incumbent") else None
    )
    q = InsightFacetQuery(
        id=query_id,
        name=name,
        naics_codes=naics,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        psc_codes=psc,
        description=str(raw.get("description") or ""),
    )
    return q if q.has_filters() else None


def load_insight_queries(settings: Settings) -> tuple[InsightFacetQuery, ...]:
    path = _queries_path(settings)
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    parsed = [query_from_dict(item) for item in data if isinstance(item, dict)]
    return tuple(q for q in parsed if q is not None)


def resolve_active_radar_query(settings: Settings) -> InsightFacetQuery | None:
    """Active query for Pulse radar — None until operator defines one. No builtins, no NAICS default."""
    queries = load_insight_queries(settings)
    if not queries:
        return None

    active_path = _active_path(settings)
    active_id: str | None = None
    if active_path.is_file():
        try:
            payload = json.loads(active_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                active_id = str(payload.get("id") or "").strip() or None
        except (OSError, json.JSONDecodeError):
            pass

    if active_id:
        for q in queries:
            if q.id == active_id:
                return q

    if len(queries) == 1:
        return queries[0]
    return None


def describe_query(query: InsightFacetQuery | None) -> str:
    if query is None or not query.has_filters():
        return "No active search"
    parts: list[str] = []
    if query.agency:
        parts.append(f"Agency: {query.agency}")
    if query.sub_agency:
        parts.append(f"Sub-agency: {query.sub_agency}")
    if query.recipient:
        parts.append(f"Recipient: {query.recipient}")
    if query.naics_codes:
        parts.append(f"NAICS: {', '.join(query.naics_codes)}")
    if query.psc_codes:
        parts.append(f"PSC: {', '.join(query.psc_codes)}")
    return " · ".join(parts) if parts else query.name


def build_facet_sql(query: InsightFacetQuery) -> tuple[str, dict[str, Any]]:
    """WHERE fragments for facet query. Caller must ensure query.has_filters()."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if query.naics_codes:
        naics_sql, naics_params = naics_filter(list(query.naics_codes), prefix="AND")
        if naics_sql:
            clauses.append(naics_sql.strip())
            params.update(naics_params)

    if query.psc_codes:
        placeholders = ", ".join(f":psc_{i}" for i in range(len(query.psc_codes)))
        clauses.append(f"AND product_or_service_code IN ({placeholders})")
        for i, code in enumerate(query.psc_codes):
            params[f"psc_{i}"] = code

    if query.agency:
        clauses.append(
            f"AND ({AGENCY_EXPR} ILIKE :agency OR awarding_sub_agency_name ILIKE :agency "
            f"OR funding_agency_name ILIKE :agency)"
        )
        params["agency"] = f"%{query.agency}%"

    if query.sub_agency:
        clauses.append(
            "AND (awarding_sub_agency_name ILIKE :sub_agency OR funding_sub_agency_name ILIKE :sub_agency)"
        )
        params["sub_agency"] = f"%{query.sub_agency}%"

    if query.recipient:
        clauses.append("AND recipient_name ILIKE :recipient")
        params["recipient"] = f"%{query.recipient}%"

    return " ".join(clauses), params