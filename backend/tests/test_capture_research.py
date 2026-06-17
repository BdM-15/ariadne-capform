import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from thread.config import Settings
from thread.domain.enums import ResearchLens
from thread.research.capture_research import load_run, run_capture_research
from thread.research.types import ResearchRunStatus


@pytest.mark.asyncio
async def test_capture_research_fake_adapter_creates_candidate_reviews(tmp_path, monkeypatch):
    review_id = uuid.uuid4()

    async def _fake_review(session, **kwargs):
        record = MagicMock()
        record.id = review_id
        return record

    monkeypatch.setattr("thread.research.capture_research.create_review_record", _fake_review)

    settings = Settings(
        thread_state_dir=tmp_path / ".thread",
        xai_api_key=None,
    )
    session = MagicMock()
    result = await run_capture_research(
        settings,
        session,
        lens=ResearchLens.CUSTOMER_RESEARCH,
        query="DHS cyber recompete",
        max_sources=2,
        use_fake=True,
    )

    assert result.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
    assert result.findings
    assert result.review_ids
    saved = load_run(settings, result.run_id)
    assert saved is not None
    assert saved["query"] == "DHS cyber recompete"


@pytest.mark.asyncio
async def test_provider_registry_includes_free_providers():
    from thread.research.providers import build_provider_registry

    settings = Settings()
    registry = await build_provider_registry(settings)
    ids = {p.id for p in registry}
    assert "searxng" in ids
    assert "crawl4ai" in ids
    assert "fake" in ids