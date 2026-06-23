"""Insights slice cache — facet keys and TTL."""

from __future__ import annotations

import time

from thread.config import Settings
from thread.intel.facet_query import InsightFacetQuery
from thread.intel.slice_cache import (
    SLICE_CACHE_TTL_SECONDS,
    clear_slice_cache,
    facet_cache_key,
    get_cached_overview,
    store_cached_overview,
)


def test_facet_cache_key_includes_advanced_facets():
    a = InsightFacetQuery(
        id="a",
        name="a",
        naics_codes=("561210",),
        awarding_office="W075 ENDIST",
    )
    b = InsightFacetQuery(
        id="b",
        name="b",
        naics_codes=("561210",),
        awarding_office="Other office",
    )
    assert facet_cache_key(a) != facet_cache_key(b)


def test_overview_cache_roundtrip(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    clear_slice_cache()
    query = InsightFacetQuery(id="q", name="q", naics_codes=("561210",))
    payload = {"status": "ready", "kpis": {"millions": 12.5}}
    store_cached_overview(settings, query, payload)
    hit = get_cached_overview(settings, query)
    assert hit is not None
    assert hit.overview == payload
    assert hit.age_seconds >= 0


def test_overview_cache_expires(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    clear_slice_cache()
    query = InsightFacetQuery(id="q", name="q", naics_codes=("561210",))
    store_cached_overview(settings, query, {"status": "ready"})
    from thread.intel import slice_cache as mod

    old_ttl = mod.SLICE_CACHE_TTL_SECONDS
    monkeypatch.setattr(mod, "SLICE_CACHE_TTL_SECONDS", 0.01)
    time.sleep(0.02)
    assert get_cached_overview(settings, query) is None
    monkeypatch.setattr(mod, "SLICE_CACHE_TTL_SECONDS", old_ttl)