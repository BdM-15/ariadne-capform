"""LangSmith / LangChain tracing env bootstrap for orchestration subgraphs."""

from __future__ import annotations

import os

from thread.config import Settings


def apply_langsmith_env(settings: Settings) -> None:
    """Mirror Thread settings into process env for LangGraph / LangChain SDKs."""
    api_key = settings.resolved_langchain_api_key
    if api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)

    project = settings.resolved_langchain_project
    os.environ.setdefault("LANGCHAIN_PROJECT", project)
    os.environ.setdefault("LANGSMITH_PROJECT", project)

    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)

    tracing_on = settings.langsmith_tracing or settings.langchain_tracing_v2
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_on else "false"
    os.environ["LANGSMITH_TRACING"] = "true" if tracing_on else "false"