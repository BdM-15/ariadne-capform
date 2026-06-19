"""Ollama catalog helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from thread.config import Settings
from thread.llm.router import _normalize_ollama_tag, ollama_model_available


def test_normalize_ollama_tag_strips_digest():
    assert _normalize_ollama_tag("qwen3:8b@sha256-abc") == "qwen3:8b"


@pytest.mark.asyncio
async def test_ollama_model_available_matches_tag():
    settings = Settings(local_daily_model="qwen3:8b")
    with patch("thread.llm.router.list_ollama_models", new_callable=AsyncMock) as listed:
        listed.return_value = ["llama3.1:8b", "qwen3:8b"]
        assert await ollama_model_available(settings, "qwen3:8b") is True
        assert await ollama_model_available(settings, "missing:7b") is False