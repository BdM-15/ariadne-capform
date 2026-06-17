"""Fake adapter for tests — no network."""

from __future__ import annotations

from thread.research.types import CrawlResult, SearchHit


async def search(query: str, *, limit: int = 5) -> list[SearchHit]:
    return [
        SearchHit(
            title=f"Fake result for {query}",
            url="https://example.com/capture-research",
            snippet="Synthetic snippet for unit tests.",
        )
    ][:limit]


async def crawl(url: str) -> CrawlResult:
    return CrawlResult(
        url=url,
        ok=True,
        markdown=f"# Fake crawl\n\nContent from {url}\n",
    )