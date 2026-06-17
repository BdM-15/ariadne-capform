"""Live research adapter smoke — skipped unless THREAD_INTEGRATION_TESTS=1.

Unit tests use fake adapters for speed and CI reliability.
Run real checks locally when Docker research profile is up:

    set THREAD_INTEGRATION_TESTS=1
    pytest tests/test_research_integration.py -v
"""

from __future__ import annotations

import os

import pytest

from thread.config import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="Set THREAD_INTEGRATION_TESTS=1 to hit live SearXNG/Crawl4AI",
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.mark.asyncio
async def test_searxng_live_search(settings: Settings):
    from thread.research.adapters import searxng

    assert await searxng.probe(settings.searxng_base_url), "SearXNG unreachable — start research docker profile"
    hits = await searxng.search(settings.searxng_base_url, "federal IT services contract", limit=3)
    assert hits, "SearXNG returned no results"
    assert hits[0].url.startswith("http")


@pytest.mark.asyncio
async def test_crawl4ai_live_crawl(settings: Settings):
    from thread.research.adapters import crawl4ai

    assert await crawl4ai.probe(settings.crawl4ai_base_url), "Crawl4AI unreachable — start research docker profile"
    result = await crawl4ai.crawl(
        settings.crawl4ai_base_url,
        "https://example.com",
        api_token=settings.crawl4ai_api_token,
    )
    assert result.ok, result.error
    assert "example" in result.markdown.lower()