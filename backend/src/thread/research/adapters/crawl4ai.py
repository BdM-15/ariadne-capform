"""Crawl4AI docker adapter — markdown extraction."""

from __future__ import annotations

import httpx

from thread.research.types import CrawlResult


async def crawl(
    base_url: str,
    url: str,
    *,
    timeout_sec: float = 60,
    client: httpx.AsyncClient | None = None,
) -> CrawlResult:
    owns = client is None
    http = client or httpx.AsyncClient(timeout=timeout_sec)
    endpoint = f"{base_url.rstrip('/')}/crawl"
    try:
        response = await http.post(endpoint, json={"urls": [url]})
        if response.status_code >= 400:
            return CrawlResult(url=url, ok=False, error=f"HTTP {response.status_code}")
        data = response.json()
        markdown = _extract_markdown(data)
        if not markdown:
            return CrawlResult(url=url, ok=False, error="empty markdown")
        return CrawlResult(url=url, ok=True, markdown=markdown[:12000])
    except (httpx.HTTPError, OSError) as exc:
        return CrawlResult(url=url, ok=False, error=str(exc))
    finally:
        if owns:
            await http.aclose()


def _extract_markdown(data: object) -> str:
    if isinstance(data, dict):
        if md := data.get("markdown"):
            return str(md)
        results = data.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                for key in ("markdown", "md", "extracted_content", "content"):
                    if first.get(key):
                        return str(first[key])
    return ""


async def probe(base_url: str, *, timeout_sec: float = 3) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(base_url.rstrip("/"))
            return response.status_code < 500
    except (httpx.HTTPError, OSError):
        return False