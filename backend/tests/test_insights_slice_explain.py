"""Phase 2e-a — on-demand slice explain + provider choice."""

from unittest.mock import AsyncMock, patch

import pytest

from thread.config import Settings
from thread.intel.facet_query import query_from_dict
from thread.llm.router import LlmProvider, LlmUnavailableError, resolve_provider_choice
from thread.services.insights_slice_explain import (
    SLICE_EXPLAIN_SYSTEM_PROMPT,
    SliceExplainError,
    build_slice_explain_bundle,
    explain_slice,
    _build_explain_messages,
)


def test_resolve_provider_choice_cloud():
    s = Settings(xai_api_key="key", reasoning_llm_model="grok-4.3")
    resolved = resolve_provider_choice(s, "cloud")
    assert resolved.provider is LlmProvider.XAI


def test_resolve_provider_choice_local():
    s = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    resolved = resolve_provider_choice(s, "local")
    assert resolved.provider is LlmProvider.OLLAMA


def test_resolve_provider_choice_cloud_requires_key():
    s = Settings(xai_api_key=None)
    with pytest.raises(LlmUnavailableError):
        resolve_provider_choice(s, "cloud")


def test_slice_explain_system_prompt_demands_synthesis_not_readout():
    assert "Do NOT" in SLICE_EXPLAIN_SYSTEM_PROMPT
    assert "analyst-grade synthesis" in SLICE_EXPLAIN_SYSTEM_PROMPT
    assert "Pursuit lanes" in SLICE_EXPLAIN_SYSTEM_PROMPT
    messages = _build_explain_messages({"facet_query": "NAICS 561210"})
    assert messages[0]["role"] == "system"
    assert "Synthesize" in messages[1]["content"]


def test_build_slice_explain_bundle_includes_shipley_and_motion():
    query = query_from_dict({"id": "t", "name": "t", "naics_codes": "561210"})
    verdict = {
        "cards": [{"id": "tam", "label": "TAM", "value": "$10.0M", "hint": "100 actions"}],
        "shipley": [{"id": "prime_lane", "gate": "pursue", "headline": "Open lane", "bullets": []}],
        "motion": {"headline": "40% direct-prime", "bullets": ["Q4 skew"]},
    }
    overview = {
        "expiring_timeline": {"insight": "Peak Mar 2026"},
        "kpis": {"millions": 100.0},
        "set_aside": [{"bucket": "NO SET ASIDE", "millions": 60.0}],
        "top_recipients": [{"recipient": "ACME", "millions": 20.0, "actions": 5}],
        "agency_intensity": {"hot_agencies": ["Department of Defense"]},
        "motion": {"channels": [{"channel": "open_competed", "pct": 62.0, "millions": 62.0}]},
    }
    bundle = build_slice_explain_bundle(
        query=query,
        overview_verdict=verdict,
        overview=overview,
        expiring_rows=({"recipient": "ACME", "months_to_end": 3, "shape_gate": "shape_now"},),
    )
    assert "561210" in bundle["facet_query"]
    assert bundle["shipley_gates"][0]["gate"] == "pursue"
    assert bundle["motion"]["headline"] == "40% direct-prime"
    assert bundle["hot_expiring_sample"][0]["recipient"] == "ACME"
    assert bundle["market_access"]["set_aside_mix"]
    assert bundle["concentration"]["hot_agencies"] == ["Department of Defense"]
    assert bundle["motion"]["entry_lanes"][0]["pct"] == 62.0


@pytest.mark.asyncio
async def test_explain_slice_returns_text(settings: Settings, monkeypatch):
    settings = settings.model_copy(update={"xai_api_key": "test-key"})

    async def _fake_complete(*_args, **_kwargs):
        from thread.llm.router import CompletionResult, LlmProvider

        return CompletionResult(text="## Slice story\n\nPursue teaming.", provider=LlmProvider.XAI, model="grok-4.3")

    monkeypatch.setattr("thread.services.insights_slice_explain.complete", _fake_complete)
    result = await explain_slice(
        settings,
        bundle={"facet_query": "NAICS 561210"},
        provider_choice="cloud",
    )
    assert "Slice story" in result.text
    assert result.provider == "xai"


@pytest.mark.asyncio
async def test_explain_slice_maps_unavailable(settings: Settings, monkeypatch):
    async def _fail(*_args, **_kwargs):
        raise LlmUnavailableError("no key")

    monkeypatch.setattr("thread.services.insights_slice_explain.complete", _fail)
    with pytest.raises(SliceExplainError, match="no key"):
        await explain_slice(settings, bundle={}, provider_choice="cloud")