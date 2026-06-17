"""Crawl4AI docker adapter — markdown extraction."""

from __future__ import annotations

import asyncio
import time

import httpx

from thread.research.types import CrawlResult


def _auth_headers(api_token: str | None) -> dict[str, str]:
    if not api_token:
        return {}
    return {"Authorization": f"Bearer {api_token}"}


async def crawl(
    base_url: str,
    url: str,
    *,
    api_token: str | None = None,
    timeout_sec: float = 60,
    client: httpx.AsyncClient | None = None,
) -> CrawlResult:
    owns = client is None
    http = client or httpx.AsyncClient(timeout=timeout_sec)
    root = base_url.rstrip("/")
    headers = _auth_headers(api_token)
    try:
        response = await http.post(f"{root}/crawl", json={"urls": [url]}, headers=headers)
        if response.status_code >= 400:
            return CrawlResult(url=url, ok=False, error=f"HTTP {response.status_code}")
        data = response.json()
        markdown = _extract_markdown(data)
        if markdown:
            return CrawlResult(url=url, ok=True, markdown=markdown[:12000])

        task_id = data.get("task_id") if isinstance(data, dict) else None
        if task_id:
            markdown = await _poll_task(http, root, str(task_id), headers=headers, timeout_sec=timeout_sec)
            if markdown:
                return CrawlResult(url=url, ok=True, markdown=markdown[:12000])
            return CrawlResult(url=url, ok=False, error="crawl task returned no markdown")

        return CrawlResult(url=url, ok=False, error="empty markdown")
    except (httpx.HTTPError, OSError) as exc:
        return CrawlResult(url=url, ok=False, error=str(exc))
    finally:
        if owns:
            await http.aclose()


async def _poll_task(
    http: httpx.AsyncClient,
    root: str,
    task_id: str,
    *,
    headers: dict[str, str],
    timeout_sec: float,
) -> str:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        response = await http.get(f"{root}/task/{task_id}", headers=headers)
        if response.status_code >= 400:
            return ""
        data = response.json()
        if isinstance(data, dict):
            status = data.get("status")
            if status == "completed":
                return _extract_markdown(data)
            if status in ("failed", "error"):
                return ""
        await asyncio.sleep(0.5)
    return ""


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
            for path in ("/health", ""):
                response = await client.get(f"{base_url.rstrip('/')}{path}")
                if response.status_code < 500:
                    return True
    except (httpx.HTTPError, OSError):
        return False
    return False