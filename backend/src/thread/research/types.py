from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProviderRole(StrEnum):
    SEARCH = "search_discovery"
    CRAWL = "page_crawl_extraction"


class ProviderStatus(StrEnum):
    AVAILABLE = "available"
    MISSING_CONFIG = "missing_config"
    REQUIRES_APPROVAL = "requires_approval"
    UNREACHABLE = "unreachable"


class ResearchRunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass
class CrawlResult:
    url: str
    ok: bool
    markdown: str = ""
    error: str | None = None


@dataclass
class ResearchFinding:
    title: str
    summary: str
    provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ResearchRunResult:
    run_id: str
    status: ResearchRunStatus
    lens: str
    query: str
    sources: list[dict[str, Any]]
    findings: list[ResearchFinding]
    interpretation: str | None = None
    review_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)