"""SearXNG JSON search adapter."""

from __future__ import annotations

import httpx

from thread.research.types import SearchHit


async def search(
    base_url: str,
    query: str,
    *,
    limit: int = 5,
    timeout_sec: float = 20,
    client: httpx.AsyncClient | None = None,
) -> list[SearchHit]:
    url = f"{base_url.rstrip('/')}/search"
    params = {"q": query, "format": "json", "categories": "general"}
    owns = client is None
    http = client or httpx.AsyncClient(timeout=timeout_sec)
    try:
        response = await http.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    finally:
        if owns:
            await http.aclose()

    hits: list[SearchHit] = []
    for row in data.get("results", [])[:limit]:
        link = row.get("url") or ""
        if not link:
            continue
        hits.append(
            SearchHit(
                title=(row.get("title") or link)[:500],
                url=link,
                snippet=(row.get("content") or row.get("snippet") or "")[:2000],
            )
        )
    return hits


async def probe(base_url: str, *, timeout_sec: float = 3) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(f"{base_url.rstrip('/')}/healthz")
            if response.status_code == 200:
                return True
            response = await client.get(base_url.rstrip("/"))
            return response.status_code < 500
    except (httpx.HTTPError, OSError):
        return False