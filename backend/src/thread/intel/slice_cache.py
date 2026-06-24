"""Disk-backed TTL cache for Insights facet slice queries (overview, explore, entity)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery

SLICE_CACHE_TTL_SECONDS = 600.0
_MEMORY: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class SliceCacheHit:
    age_seconds: float
    overview: dict[str, Any] | None = None
    explore_rows: tuple[dict[str, Any], ...] | None = None
    entity_profile: dict[str, Any] | None = None


def clear_slice_cache() -> None:
    """Test helper — drop in-memory slice cache."""
    _MEMORY.clear()


def _cache_dir(settings: Settings) -> Path:
    path = settings.resolve(settings.thread_state_dir) / "insights_slice_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def facet_cache_key(query: InsightFacetQuery) -> str:
    payload = {
        "naics": list(query.naics_codes),
        "agency": query.agency,
        "sub_agency": query.sub_agency,
        "recipient": query.recipient,
        "psc": list(query.psc_codes),
        "awarding_office": query.awarding_office,
        "funding_office": query.funding_office,
        "recipient_uei": query.recipient_uei,
        "pop_state": query.pop_state,
        "extent_competed": query.extent_competed,
        "type_of_set_aside": query.type_of_set_aside,
        "min_contract_value": query.min_contract_value,
        "min_value_basis": query.min_value_basis,
        "exclude_agencies": list(query.exclude_agencies),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def entity_profile_cache_key(*, kind: str, scope: str, value: str) -> str:
    return f"{kind}:{scope}:{value}"


def _bundle_path(settings: Settings, facet_key: str) -> Path:
    return _cache_dir(settings) / f"{facet_key}.json"


def _read_bundle(settings: Settings, facet_key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    mem = _MEMORY.get(facet_key)
    if mem and (now - mem[0]) < SLICE_CACHE_TTL_SECONDS:
        return dict(mem[1])

    path = _bundle_path(settings, facet_key)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    cached_at = float(raw.get("cached_at_mono") or 0)
    if cached_at <= 0 or (now - cached_at) >= SLICE_CACHE_TTL_SECONDS:
        return None
    _MEMORY[facet_key] = (cached_at, dict(raw))
    return raw


def _write_bundle(settings: Settings, facet_key: str, bundle: dict[str, Any]) -> None:
    bundle["cached_at_mono"] = time.monotonic()
    _MEMORY[facet_key] = (bundle["cached_at_mono"], dict(bundle))
    path = _bundle_path(settings, facet_key)
    path.write_text(json.dumps(bundle, default=str), encoding="utf-8")


def get_cached_overview(
    settings: Settings,
    query: InsightFacetQuery,
) -> SliceCacheHit | None:
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key)
    if not bundle:
        return None
    overview = bundle.get("overview")
    if not isinstance(overview, dict):
        return None
    age = time.monotonic() - float(bundle.get("cached_at_mono") or time.monotonic())
    return SliceCacheHit(age_seconds=age, overview=dict(overview))


def store_cached_overview(
    settings: Settings,
    query: InsightFacetQuery,
    overview: dict[str, Any],
) -> None:
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key) or {}
    bundle["overview"] = overview
    _write_bundle(settings, key, bundle)


def get_cached_explore_rows(
    settings: Settings,
    query: InsightFacetQuery,
    *,
    entity_kind: str = "",
    entity_scope: str = "",
    entity_value: str = "",
) -> SliceCacheHit | None:
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key)
    if not bundle:
        return None
    explore = bundle.get("explore")
    if not isinstance(explore, dict):
        return None
    if entity_value.strip():
        entity_key = entity_profile_cache_key(
            kind=entity_kind or "agency",
            scope=entity_scope or "agency",
            value=entity_value.strip(),
        )
        rows = explore.get("entity_rows", {}).get(entity_key)
    else:
        rows = explore.get("rows")
    if rows is None:
        return None
    age = time.monotonic() - float(bundle.get("cached_at_mono") or time.monotonic())
    return SliceCacheHit(age_seconds=age, explore_rows=tuple(rows))


def store_cached_explore_rows(
    settings: Settings,
    query: InsightFacetQuery,
    rows: list[dict[str, Any]],
    *,
    entity_kind: str = "",
    entity_scope: str = "",
    entity_value: str = "",
) -> None:
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key) or {}
    explore = bundle.get("explore")
    if not isinstance(explore, dict):
        explore = {"rows": [], "entity_rows": {}}
    if entity_value.strip():
        entity_rows = explore.get("entity_rows")
        if not isinstance(entity_rows, dict):
            entity_rows = {}
        entity_rows[
            entity_profile_cache_key(
                kind=entity_kind or "agency",
                scope=entity_scope or "agency",
                value=entity_value.strip(),
            )
        ] = rows
        explore["entity_rows"] = entity_rows
    else:
        explore["rows"] = rows
    bundle["explore"] = explore
    _write_bundle(settings, key, bundle)


def get_cached_entity_profile(
    settings: Settings,
    query: InsightFacetQuery,
    *,
    kind: str,
    scope: str,
    value: str,
) -> SliceCacheHit | None:
    if not value.strip():
        return None
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key)
    if not bundle:
        return None
    profiles = bundle.get("entity_profiles")
    if not isinstance(profiles, dict):
        return None
    profile = profiles.get(entity_profile_cache_key(kind=kind, scope=scope, value=value.strip()))
    if not isinstance(profile, dict):
        return None
    age = time.monotonic() - float(bundle.get("cached_at_mono") or time.monotonic())
    return SliceCacheHit(age_seconds=age, entity_profile=dict(profile))


def store_cached_entity_profile(
    settings: Settings,
    query: InsightFacetQuery,
    *,
    kind: str,
    scope: str,
    value: str,
    profile: dict[str, Any],
) -> None:
    if not value.strip():
        return
    key = facet_cache_key(query)
    bundle = _read_bundle(settings, key) or {}
    profiles = bundle.get("entity_profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    profiles[entity_profile_cache_key(kind=kind, scope=scope, value=value.strip())] = profile
    bundle["entity_profiles"] = profiles
    _write_bundle(settings, key, bundle)