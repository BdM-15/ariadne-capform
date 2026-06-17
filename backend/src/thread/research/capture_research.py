"""Bounded capture research — discover, crawl, interpret, review-gate."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.domain.enums import ResearchLens, TrustLevel
from thread.llm.router import LlmTaskKind, complete as llm_complete
from thread.research.adapters import crawl4ai as crawl4ai_adapter
from thread.research.adapters import fake as fake_adapter
from thread.research.adapters import searxng as searxng_adapter
from thread.research.lenses import system_prompt_for
from thread.research.types import (
    ResearchFinding,
    ResearchRunResult,
    ResearchRunStatus,
)
from thread.services.review_gate import create_review_record


def _runs_dir(settings: Settings) -> Path:
    path = settings.resolve(settings.thread_state_dir) / "research"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run(settings: Settings, result: ResearchRunResult) -> Path:
    path = _runs_dir(settings) / f"{result.run_id}.json"
    payload = {
        "run_id": result.run_id,
        "status": result.status.value,
        "lens": result.lens,
        "query": result.query,
        "sources": result.sources,
        "findings": [
            {"title": f.title, "summary": f.summary, "provenance": f.provenance}
            for f in result.findings
        ],
        "interpretation": result.interpretation,
        "review_ids": result.review_ids,
        "errors": result.errors,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_run(settings: Settings, run_id: str) -> dict[str, Any] | None:
    path = _runs_dir(settings) / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


async def run_capture_research(
    settings: Settings,
    session: AsyncSession,
    *,
    lens: ResearchLens,
    query: str,
    max_sources: int = 5,
    opportunity_id: uuid.UUID | None = None,
    use_fake: bool = False,
) -> ResearchRunResult:
    run_id = str(uuid.uuid4())
    errors: list[str] = []
    sources: list[dict[str, Any]] = []

    if use_fake:
        hits = await fake_adapter.search(query, limit=max_sources)
    else:
        try:
            hits = await searxng_adapter.search(
                settings.searxng_base_url, query, limit=max_sources
            )
        except Exception as exc:
            errors.append(f"searxng: {exc}")
            hits = []

    for hit in hits:
        crawl = (
            await fake_adapter.crawl(hit.url)
            if use_fake
            else await crawl4ai_adapter.crawl(
                settings.crawl4ai_base_url,
                hit.url,
                api_token=settings.crawl4ai_api_token,
            )
        )
        sources.append(
            {
                "title": hit.title,
                "url": hit.url,
                "snippet": hit.snippet,
                "crawled": crawl.ok,
                "markdown_excerpt": crawl.markdown[:1500] if crawl.ok else "",
                "crawl_error": crawl.error,
            }
        )
        if not crawl.ok and crawl.error:
            errors.append(f"crawl {hit.url}: {crawl.error}")

    findings = _build_findings(sources)
    interpretation = await _interpret(settings, lens, query, sources, errors)

    review_ids: list[str] = []
    for idx, finding in enumerate(findings):
        entity_id = f"{run_id}:finding:{idx}"
        record = await create_review_record(
            session,
            entity_type="research_finding",
            entity_id=entity_id,
            trust_level=TrustLevel.CANDIDATE,
            provenance=finding.provenance,
        )
        review_ids.append(str(record.id))

    if interpretation:
        record = await create_review_record(
            session,
            entity_type="research_interpretation",
            entity_id=f"{run_id}:interpretation",
            trust_level=TrustLevel.CANDIDATE,
            provenance=[{"kind": "web_research", "ref": run_id, "excerpt": interpretation[:500]}],
        )
        review_ids.append(str(record.id))

    status = ResearchRunStatus.COMPLETED
    if errors and sources:
        status = ResearchRunStatus.PARTIAL
    elif errors and not sources:
        status = ResearchRunStatus.FAILED

    result = ResearchRunResult(
        run_id=run_id,
        status=status,
        lens=lens.value,
        query=query,
        sources=sources,
        findings=findings,
        interpretation=interpretation,
        review_ids=review_ids,
        errors=errors,
    )
    if opportunity_id:
        result.sources.insert(
            0,
            {"meta": "opportunity_id", "value": str(opportunity_id)},
        )
    save_run(settings, result)
    return result


def _build_findings(sources: list[dict[str, Any]]) -> list[ResearchFinding]:
    findings: list[ResearchFinding] = []
    for src in sources:
        if src.get("meta"):
            continue
        excerpt = src.get("markdown_excerpt") or src.get("snippet") or ""
        if not excerpt.strip():
            continue
        findings.append(
            ResearchFinding(
                title=src.get("title") or src.get("url", "source"),
                summary=excerpt[:800],
                provenance=[
                    {
                        "kind": "url",
                        "ref": src.get("url", ""),
                        "excerpt": excerpt[:300],
                    }
                ],
            )
        )
    return findings


async def _interpret(
    settings: Settings,
    lens: ResearchLens,
    query: str,
    sources: list[dict[str, Any]],
    errors: list[str],
) -> str | None:
    if not settings.xai_api_key:
        return None
    if not any(s.get("markdown_excerpt") or s.get("snippet") for s in sources if not s.get("meta")):
        return None

    blocks = []
    for src in sources:
        if src.get("meta"):
            continue
        blocks.append(
            f"### {src.get('title')}\nURL: {src.get('url')}\n"
            f"{src.get('markdown_excerpt') or src.get('snippet', '')[:2000]}"
        )
    user_content = f"Research query: {query}\n\nSources:\n\n" + "\n\n".join(blocks)
    if errors:
        user_content += f"\n\nCollection notes: {'; '.join(errors[:5])}"

    try:
        result = await llm_complete(
            settings,
            task_kind=LlmTaskKind.REASONING,
            messages=[
                {"role": "system", "content": system_prompt_for(lens)},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2048,
        )
        return result.text
    except Exception:
        return None