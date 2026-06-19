import pytest

from thread.config import Settings
from thread.llm.router import (
    LlmProvider,
    LlmTaskKind,
    LlmUnavailableError,
    resolve_provider,
)


def test_reasoning_prefers_xai_when_key_set():
    s = Settings(xai_api_key="test-key", reasoning_llm_model="grok-4")
    resolved = resolve_provider(s, LlmTaskKind.REASONING)
    assert resolved.provider is LlmProvider.XAI
    assert resolved.model == "grok-4"


def test_reasoning_falls_back_to_ollama_without_xai_key():
    s = Settings(xai_api_key=None, llm_fallback_enabled=True, local_daily_model="qwen3:8b")
    resolved = resolve_provider(s, LlmTaskKind.REASONING)
    assert resolved.provider is LlmProvider.OLLAMA
    assert resolved.model == "qwen3:8b"


def test_reasoning_raises_when_no_provider():
    s = Settings(xai_api_key=None, llm_fallback_enabled=False)
    with pytest.raises(LlmUnavailableError):
        resolve_provider(s, LlmTaskKind.REASONING)


def test_admin_prefers_ollama():
    s = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    resolved = resolve_provider(s, LlmTaskKind.ADMIN)
    assert resolved.provider is LlmProvider.OLLAMA


def test_admin_falls_back_to_xai_when_ollama_disabled():
    s = Settings(
        local_admin_model_enabled=False,
        xai_api_key="test-key",
        reasoning_llm_model="grok-4",
    )
    resolved = resolve_provider(s, LlmTaskKind.ADMIN)
    assert resolved.provider is LlmProvider.XAI