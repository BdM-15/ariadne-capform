"""Capture title inference — glanceable labels."""

from unittest.mock import AsyncMock, patch

import pytest

from thread.config import Settings
from thread.services.capture_title import (
    infer_capture_title,
    rules_infer_capture_title,
    rules_is_confident,
)


def test_rules_infer_proposal_review_repository():
    dump = (
        "I want to create a knowledge repository from reviewer feedback "
        "and anonymize it for proposal reviews"
    )
    result = rules_infer_capture_title(dump)
    assert result.title == "Proposal Review Comments Repository"
    assert result.match_kind == "keyword"


def test_rules_do_not_confuse_boss_grill_dump_with_proposal_review():
    dump = (
        "i want to consolidate all the comments or questions my boss asks during meetings "
        "so i can create a grill me boss skill that will review my artifacts before i present them "
        "so i can get ahead of any common concerns and pr"
    )
    result = rules_infer_capture_title(dump)
    assert result.title != "Proposal Review Comments Repository"
    assert "Grill" in result.title or result.match_kind == "first_line"


def test_rules_infer_boss_grill_skill_keyword():
    dump = "create a grill me boss skill to review artifacts before I present"
    result = rules_infer_capture_title(dump)
    assert result.title == "Boss Grill Prep Skill"
    assert result.page_type == "concept"
    assert result.match_kind == "keyword"


@pytest.mark.asyncio
async def test_infer_capture_title_falls_back_to_rules_without_ollama():
    settings = Settings(local_admin_model_enabled=False)
    dump = "I want to create a knowledge repository from reviewer feedback"
    result = await infer_capture_title(settings, dump)
    assert result.provider == "rules"
    assert "Review" in result.title or "Repository" in result.title


def test_rules_confident_only_for_keywords():
    generic = rules_infer_capture_title("hm")
    assert rules_is_confident(generic) is False
    keyword = rules_infer_capture_title("reviewer feedback on proposals")
    assert rules_is_confident(keyword) is True
    first_line = rules_infer_capture_title("Maybe we should track sub award spend by NAICS for DISA")
    assert first_line.match_kind == "first_line"
    assert rules_is_confident(first_line) is False


@pytest.mark.asyncio
async def test_infer_capture_title_skips_ollama_when_keyword_match():
    settings = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    dump = "reviewer feedback on proposal comments repository"
    with patch("thread.services.capture_title.complete", new_callable=AsyncMock) as mocked:
        result = await infer_capture_title(settings, dump, quick=False)
        mocked.assert_not_called()
    assert result.provider == "rules"
    assert result.match_kind == "keyword"


@pytest.mark.asyncio
async def test_infer_capture_title_uses_ollama_for_random_thought():
    settings = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    dump = "Maybe we should track sub award spend by NAICS for army CIO office recompete signals"
    with patch("thread.services.capture_title.complete", new_callable=AsyncMock) as mocked:
        from thread.llm.router import CompletionResult, LlmProvider

        mocked.return_value = CompletionResult(
            text='{"title": "Army CIO Sub Award Spend", "page_type": "agency"}',
            provider=LlmProvider.OLLAMA,
            model="qwen3:8b",
        )
        result = await infer_capture_title(settings, dump)
    mocked.assert_called_once()
    assert result.provider == "ollama"
    assert result.title == "Army CIO Sub Award Spend"
    assert result.page_type == "agency"


@pytest.mark.asyncio
async def test_infer_capture_title_quick_never_calls_ollama():
    settings = Settings(local_admin_model_enabled=True)
    with patch("thread.services.capture_title.complete", new_callable=AsyncMock) as mocked:
        await infer_capture_title(settings, "random thought about clouds", quick=True)
        mocked.assert_not_called()


@pytest.mark.asyncio
async def test_infer_capture_title_falls_back_when_ollama_times_out():
    import httpx

    settings = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    dump = (
        "i heard about a new potential edge computing capability during ameetting "
        "from a person named Jason Gray. need more information to add to company capability konweldge"
    )
    with patch("thread.services.capture_title.complete", side_effect=httpx.ReadTimeout("")):
        result = await infer_capture_title(settings, dump)
    assert result.provider == "rules"
    assert result.title
    assert result.title != "Quick Capture Note"


@pytest.mark.asyncio
async def test_infer_capture_title_uses_ollama_on_generic_dump():
    settings = Settings(local_admin_model_enabled=True, local_daily_model="qwen3:8b")
    dump = "hm"
    with patch("thread.services.capture_title.complete", new_callable=AsyncMock) as mocked:
        from thread.llm.router import CompletionResult, LlmProvider

        mocked.return_value = CompletionResult(
            text='{"title": "Cyber Spend Trend Note", "page_type": "synthesis"}',
            provider=LlmProvider.OLLAMA,
            model="qwen3:8b",
        )
        result = await infer_capture_title(settings, dump)
    assert result.provider == "ollama"
    assert result.title == "Cyber Spend Trend Note"