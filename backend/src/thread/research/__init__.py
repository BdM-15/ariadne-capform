"""Bounded web research — SearXNG + Crawl4AI first; review-gated findings."""

__all__ = ["build_provider_registry", "run_capture_research"]


def __getattr__(name: str):
    if name == "run_capture_research":
        from thread.research.capture_research import run_capture_research

        return run_capture_research
    if name == "build_provider_registry":
        from thread.research.providers import build_provider_registry

        return build_provider_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")