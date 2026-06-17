"""Bounded web research — SearXNG + Crawl4AI first; review-gated findings."""

from thread.research.capture_research import run_capture_research
from thread.research.providers import build_provider_registry

__all__ = ["build_provider_registry", "run_capture_research"]