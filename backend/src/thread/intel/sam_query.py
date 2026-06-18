"""Operator-defined SAM.gov monitor queries — no platform search defaults."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings


@dataclass(frozen=True)
class SamMonitorQuery:
    id: str
    name: str
    days_back: int = 14
    title: str | None = None
    naics_code: str | None = None
    psc_code: str | None = None
    agency_keyword: str | None = None
    notice_type: str | None = None
    set_aside: str | None = None
    limit: int = 12
    description: str = ""

    def has_filters(self) -> bool:
        return bool(
            self.title
            or self.naics_code
            or self.psc_code
            or self.agency_keyword
            or self.notice_type
            or self.set_aside
        )


def _queries_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "sam_queries.json"


def _active_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "active_sam_query.json"


def query_from_dict(raw: dict[str, Any]) -> SamMonitorQuery | None:
    query_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or query_id).strip()
    if not query_id or not name:
        return None
    days_back = int(raw.get("days_back") or 14)
    limit = int(raw.get("limit") or 12)
    q = SamMonitorQuery(
        id=query_id,
        name=name,
        days_back=max(1, min(days_back, 90)),
        title=(str(raw["title"]).strip() or None) if raw.get("title") else None,
        naics_code=(str(raw["naics_code"]).strip() or None) if raw.get("naics_code") else None,
        psc_code=(str(raw["psc_code"]).strip() or None) if raw.get("psc_code") else None,
        agency_keyword=(str(raw["agency_keyword"]).strip() or None) if raw.get("agency_keyword") else None,
        notice_type=(str(raw["notice_type"]).strip().lower() or None) if raw.get("notice_type") else None,
        set_aside=(str(raw["set_aside"]).strip() or None) if raw.get("set_aside") else None,
        limit=max(1, min(limit, 25)),
        description=str(raw.get("description") or ""),
    )
    return q if q.has_filters() else None


def _slug_id(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "sam"
    candidate = base[:48]
    suffix = 2
    while candidate in existing:
        candidate = f"{base[:40]}-{suffix}"
        suffix += 1
    return candidate


def _write_queries(settings: Settings, queries: list[SamMonitorQuery]) -> None:
    path = _queries_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": q.id,
            "name": q.name,
            "days_back": q.days_back,
            "title": q.title,
            "naics_code": q.naics_code,
            "psc_code": q.psc_code,
            "agency_keyword": q.agency_keyword,
            "notice_type": q.notice_type,
            "set_aside": q.set_aside,
            "limit": q.limit,
            "description": q.description,
        }
        for q in queries
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_sam_query(settings: Settings, query: SamMonitorQuery) -> SamMonitorQuery:
    queries = list(load_sam_queries(settings))
    by_id = {q.id: q for q in queries}
    by_id[query.id] = query
    ordered = sorted(by_id.values(), key=lambda q: q.name.lower())
    _write_queries(settings, ordered)
    return query


def delete_sam_query(settings: Settings, query_id: str) -> bool:
    before = load_sam_queries(settings)
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


def activate_sam_query(settings: Settings, query_id: str) -> bool:
    if not any(q.id == query_id for q in load_sam_queries(settings)):
        return False
    path = _active_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": query_id}, indent=2), encoding="utf-8")
    return True


def new_sam_query_from_form(
    settings: Settings,
    *,
    name: str,
    title: str = "",
    naics_code: str = "",
    psc_code: str = "",
    agency_keyword: str = "",
    notice_type: str = "",
    set_aside: str = "",
    days_back: int = 14,
    limit: int = 12,
    description: str = "",
) -> SamMonitorQuery | None:
    raw = {
        "name": name.strip(),
        "title": title.strip() or None,
        "naics_code": naics_code.strip() or None,
        "psc_code": psc_code.strip() or None,
        "agency_keyword": agency_keyword.strip() or None,
        "notice_type": notice_type.strip().lower() or None,
        "set_aside": set_aside.strip() or None,
        "days_back": days_back,
        "limit": limit,
        "description": description.strip(),
    }
    existing = {q.id for q in load_sam_queries(settings)}
    raw["id"] = _slug_id(raw["name"], existing)
    return query_from_dict(raw)


def load_sam_queries(settings: Settings) -> tuple[SamMonitorQuery, ...]:
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


def resolve_active_sam_query(settings: Settings) -> SamMonitorQuery | None:
    queries = load_sam_queries(settings)
    if not queries:
        return None

    active_id: str | None = None
    active_path = _active_path(settings)
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


def describe_sam_query(query: SamMonitorQuery | None) -> str:
    if query is None:
        return "No active SAM search"
    parts: list[str] = [query.name]
    if query.title:
        parts.append(f'title "{query.title}"')
    if query.naics_code:
        parts.append(f"NAICS {query.naics_code}")
    if query.psc_code:
        parts.append(f"PSC {query.psc_code}")
    if query.agency_keyword:
        parts.append(f"agency {query.agency_keyword}")
    if query.notice_type:
        parts.append(f"type {query.notice_type}")
    if query.set_aside:
        parts.append(f"set-aside {query.set_aside}")
    parts.append(f"{query.days_back}d window")
    return " · ".join(parts)


def build_mcp_arguments(query: SamMonitorQuery, *, today: Any | None = None) -> dict[str, Any]:
    from datetime import date, timedelta

    end = today if isinstance(today, date) else date.today()
    start = end - timedelta(days=query.days_back)
    fmt = "%m/%d/%Y"
    args: dict[str, Any] = {
        "posted_from": start.strftime(fmt),
        "posted_to": end.strftime(fmt),
        "limit": query.limit,
    }
    if query.title:
        args["title"] = query.title
    if query.naics_code:
        args["naics_code"] = query.naics_code
    if query.psc_code:
        args["psc_code"] = query.psc_code
    if query.agency_keyword:
        args["agency_keyword"] = query.agency_keyword
    if query.notice_type:
        args["notice_type"] = query.notice_type
    if query.set_aside:
        args["set_aside"] = query.set_aside
    return args