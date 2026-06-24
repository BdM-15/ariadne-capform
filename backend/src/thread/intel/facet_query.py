"""Flexible insight queries — any facet combo; no default NAICS or preset dimension."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings
from thread.intel.sql_expressions import AGENCY_EXPR, naics_filter


ADVANCED_FACET_FIELDS: tuple[str, ...] = (
    "awarding_office",
    "funding_office",
    "recipient_uei",
    "pop_state",
    "extent_competed",
    "type_of_set_aside",
    "exclude_agencies",
)

MAIN_FACET_FIELDS: tuple[str, ...] = (
    "agency",
    "sub_agency",
    "recipient",
    "naics_codes",
    "psc_codes",
    "min_obligation",
)


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
    awarding_office: str | None = None
    funding_office: str | None = None
    recipient_uei: str | None = None
    pop_state: str | None = None
    extent_competed: str | None = None
    type_of_set_aside: str | None = None
    min_obligation: float | None = None
    exclude_agencies: tuple[str, ...] = ()
    description: str = ""

    def has_filters(self) -> bool:
        return bool(
            self.naics_codes
            or self.agency
            or self.sub_agency
            or self.recipient
            or self.psc_codes
            or self.awarding_office
            or self.funding_office
            or self.recipient_uei
            or self.pop_state
            or self.extent_competed
            or self.type_of_set_aside
        )


def _queries_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "insight_queries.json"


def _active_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "active_insight_query.json"


def _parse_min_obligation(raw: Any) -> float | None:
    """Parse minimum prime-action obligation in raw USD (supports 1M, 500K, $250000)."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    multiplier = 1.0
    suffix = text[-1]
    if suffix in "Kk":
        multiplier = 1_000.0
        text = text[:-1]
    elif suffix in "Mm":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif suffix in "Bb":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    try:
        value = float(text) * multiplier
    except ValueError:
        return None
    return value if value > 0 else None


def _parse_phrase_list(raw: Any) -> tuple[str, ...]:
    """Comma/semicolon-separated phrases — preserves spaces (agency names)."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [c.strip() for c in re.split(r"[,;]+", raw) if c.strip()]
    elif isinstance(raw, list):
        items = [str(c).strip() for c in raw if str(c).strip()]
    else:
        return ()
    return tuple(items)


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
    exclude_agencies = _parse_phrase_list(raw.get("exclude_agencies"))
    min_obligation = _parse_min_obligation(raw.get("min_obligation"))
    agency = (str(raw["agency"]).strip() or None) if raw.get("agency") else None
    sub_agency = (str(raw["sub_agency"]).strip() or None) if raw.get("sub_agency") else None
    recipient = (
        (str(raw["recipient"]).strip() or None)
        if raw.get("recipient")
        else (str(raw["incumbent"]).strip() or None) if raw.get("incumbent") else None
    )
    def _opt_str(key: str) -> str | None:
        val = raw.get(key)
        if val is None:
            return None
        text = str(val).strip()
        return text or None

    q = InsightFacetQuery(
        id=query_id,
        name=name,
        naics_codes=naics,
        agency=agency,
        sub_agency=sub_agency,
        recipient=recipient,
        psc_codes=psc,
        awarding_office=_opt_str("awarding_office"),
        funding_office=_opt_str("funding_office"),
        recipient_uei=_opt_str("recipient_uei"),
        pop_state=_opt_str("pop_state"),
        extent_competed=_opt_str("extent_competed"),
        type_of_set_aside=_opt_str("type_of_set_aside"),
        min_obligation=min_obligation,
        exclude_agencies=exclude_agencies,
        description=str(raw.get("description") or ""),
    )
    return q if q.has_filters() else None


def _slug_id(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "lens"
    candidate = base[:48]
    suffix = 2
    while candidate in existing:
        candidate = f"{base[:40]}-{suffix}"
        suffix += 1
    return candidate


def _write_queries(settings: Settings, queries: list[InsightFacetQuery]) -> None:
    path = _queries_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": q.id,
            "name": q.name,
            "naics_codes": list(q.naics_codes),
            "agency": q.agency,
            "sub_agency": q.sub_agency,
            "recipient": q.recipient,
            "psc_codes": list(q.psc_codes),
            "awarding_office": q.awarding_office,
            "funding_office": q.funding_office,
            "recipient_uei": q.recipient_uei,
            "pop_state": q.pop_state,
            "extent_competed": q.extent_competed,
            "type_of_set_aside": q.type_of_set_aside,
            "min_obligation": q.min_obligation,
            "exclude_agencies": list(q.exclude_agencies),
            "description": q.description,
        }
        for q in queries
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_insight_query(settings: Settings, query: InsightFacetQuery) -> InsightFacetQuery:
    queries = list(load_insight_queries(settings))
    by_id = {q.id: q for q in queries}
    by_id[query.id] = query
    ordered = sorted(by_id.values(), key=lambda q: q.name.lower())
    _write_queries(settings, ordered)
    return query


def delete_insight_query(settings: Settings, query_id: str) -> bool:
    before = load_insight_queries(settings)
    queries = [q for q in before if q.id != query_id]
    if len(queries) == len(before):
        return False
    _write_queries(settings, list(queries))
    active_path = _active_path(settings)
    if active_path.is_file():
        try:
            payload = json.loads(active_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("id") == query_id:
                active_path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass
    return True


def activate_insight_query(settings: Settings, query_id: str) -> bool:
    if not any(q.id == query_id for q in load_insight_queries(settings)):
        return False
    path = _active_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": query_id}, indent=2), encoding="utf-8")
    return True


def new_insight_query_from_form(
    settings: Settings,
    *,
    name: str,
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
    min_obligation: str = "",
    exclude_agencies: str = "",
    description: str = "",
) -> InsightFacetQuery | None:
    raw = {
        "name": name.strip(),
        "agency": agency.strip() or None,
        "sub_agency": sub_agency.strip() or None,
        "recipient": recipient.strip() or None,
        "naics_codes": naics_codes.strip(),
        "psc_codes": psc_codes.strip(),
        "awarding_office": awarding_office.strip() or None,
        "funding_office": funding_office.strip() or None,
        "recipient_uei": recipient_uei.strip() or None,
        "pop_state": pop_state.strip() or None,
        "extent_competed": extent_competed.strip() or None,
        "type_of_set_aside": type_of_set_aside.strip() or None,
        "min_obligation": min_obligation.strip() or None,
        "exclude_agencies": exclude_agencies.strip(),
        "description": description.strip(),
    }
    existing = {q.id for q in load_insight_queries(settings)}
    raw["id"] = _slug_id(raw["name"], existing)
    return query_from_dict(raw)


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
    if query.awarding_office:
        parts.append(f"Awarding office: {query.awarding_office}")
    if query.funding_office:
        parts.append(f"Funding office: {query.funding_office}")
    if query.recipient_uei:
        parts.append(f"UEI: {query.recipient_uei}")
    if query.pop_state:
        parts.append(f"POP state: {query.pop_state}")
    if query.extent_competed:
        parts.append(f"Competition: {query.extent_competed}")
    if query.type_of_set_aside:
        parts.append(f"Set-aside: {query.type_of_set_aside}")
    if query.min_obligation:
        parts.append(f"Min obligation: ${query.min_obligation:,.0f}")
    if query.exclude_agencies:
        parts.append(f"Exclude: {', '.join(query.exclude_agencies)}")
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

    if query.awarding_office:
        clauses.append("AND awarding_office_name ILIKE :awarding_office")
        params["awarding_office"] = f"%{query.awarding_office}%"

    if query.funding_office:
        clauses.append("AND funding_office_name ILIKE :funding_office")
        params["funding_office"] = f"%{query.funding_office}%"

    if query.recipient_uei:
        clauses.append("AND recipient_uei ILIKE :recipient_uei")
        params["recipient_uei"] = f"%{query.recipient_uei}%"

    if query.pop_state:
        clauses.append(
            "AND primary_place_of_performance_state_code ILIKE :pop_state"
        )
        params["pop_state"] = f"%{query.pop_state}%"

    if query.extent_competed:
        clauses.append("AND extent_competed ILIKE :extent_competed")
        params["extent_competed"] = f"%{query.extent_competed}%"

    if query.type_of_set_aside:
        clauses.append("AND type_of_set_aside ILIKE :type_of_set_aside")
        params["type_of_set_aside"] = f"%{query.type_of_set_aside}%"

    if query.min_obligation:
        clauses.append("AND COALESCE(federal_action_obligation, 0) >= :min_obligation")
        params["min_obligation"] = query.min_obligation

    if query.exclude_agencies:
        for i, excluded in enumerate(query.exclude_agencies):
            clauses.append(
                f"AND NOT ({AGENCY_EXPR} ILIKE :exclude_agency_{i} "
                f"OR awarding_sub_agency_name ILIKE :exclude_agency_{i} "
                f"OR funding_agency_name ILIKE :exclude_agency_{i})"
            )
            params[f"exclude_agency_{i}"] = f"%{excluded}%"

    return " ".join(clauses), params