"""Education Studio — Grok explain + lesson draft queue (Phase 22e-1)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.llm.router import CompletionResult, LlmProvider
from thread.main import create_app
from thread.services.education_studio import (
    EducationStudioWidget,
    education_vault_review_href,
    explain_education_topic,
    load_education_studio_widget,
    queue_education_lesson_draft,
    save_education_studio_snapshot,
)
from thread.services.vault_write import _assert_write_zone, _infer_promote_target


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_education_studio_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def _seed_education_vault(vault, tmp_path):
    lessons = vault / "education" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "01-existing.md").write_text(
        """---
title: Existing
id: education-lesson-01
lesson_number: 1
---
# Existing
""",
        encoding="utf-8",
    )
    record = vault / "education" / "learning-records"
    record.mkdir(parents=True)
    (record / "ben.md").write_text("# Learning record\n\n## Learning\n- [ ] Topic\n", encoding="utf-8")
    (vault / "education" / "MISSION.md").write_text("# Mission\n", encoding="utf-8")
    plan = tmp_path / "docs"
    plan.mkdir(parents=True)
    (plan / "PLAN.md").write_text("### Phase 22\nEducation lane\n", encoding="utf-8")


def test_education_draft_links_to_knowledge_vault_inbox():
    rid = uuid.uuid4()
    assert education_vault_review_href(rid) == (
        f"/knowledge?inbox={rid}#knowledge-vault-inbox"
    )


def test_studio_snapshot_survives_reload(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    studio = EducationStudioWidget(
        grok_configured=True,
        reasoning_model="grok-4.3",
        suggestion="Watch vs Track",
        response="# Draft\n\nBody",
        response_kind="draft",
        review_id="abc-123",
        draft_target="education/lessons/02-watch.md",
    )
    save_education_studio_snapshot(settings, studio)
    restored = load_education_studio_widget(settings)
    assert restored.suggestion == "Watch vs Track"
    assert "Draft" in (restored.response or "")
    assert restored.review_href == "/knowledge?inbox=abc-123#knowledge-vault-inbox"


def test_education_lesson_path_allowed_in_write_zone():
    _assert_write_zone("education/lessons/02-watch-vs-track.md")


def test_infer_promote_target_for_education_candidate():
    meta = {
        "type": "education",
        "promote_target": "education/lessons/02-watch-vs-track.md",
        "lesson_number": "2",
    }
    assert _infer_promote_target("generated-projections/edu-02-watch-2026-06-21.md", meta) == (
        "education/lessons/02-watch-vs-track.md"
    )


@pytest.mark.asyncio
async def test_explain_education_topic(settings: Settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _seed_education_vault(vault, tmp_path)
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "xai_api_key", "test-key")

    mock_result = CompletionResult(
        text="## Answer\n\nWatch is explicit potential.\n\n## What you can steer\n- Pulse copy",
        provider=LlmProvider.XAI,
        model="grok-4.3",
    )
    with patch(
        "thread.services.education_studio.complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await explain_education_topic(settings, suggestion="Watch vs Track?")

    assert "Watch is explicit" in result.text
    assert result.model == "grok-4.3"


@pytest.mark.asyncio
async def test_queue_education_lesson_draft(settings: Settings, tmp_path, monkeypatch, db_session):
    vault = tmp_path / "vault"
    _seed_education_vault(vault, tmp_path)
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    monkeypatch.setattr(settings, "xai_api_key", "test-key")
    monkeypatch.chdir(tmp_path)

    mock_result = CompletionResult(
        text="# Lesson 02 — Watch vs Track\n\n## Who this is for\nBuilder.\n\n## What you can steer\n- IA",
        provider=LlmProvider.XAI,
        model="grok-4.3",
    )
    with patch(
        "thread.services.education_studio.complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await queue_education_lesson_draft(
            settings,
            db_session,
            suggestion="Explain Watch vs Track",
        )

    assert result.lesson_number == 2
    assert result.target_rel.startswith("education/lessons/02-")
    candidate = vault / result.candidate_path
    assert candidate.is_file()
    text = candidate.read_text(encoding="utf-8")
    assert "type: education" in text
    assert "Lesson 02" in text


def test_education_page_includes_studio():
    client = TestClient(create_app())
    res = client.get("/education")
    assert res.status_code == 200
    assert "education-studio" in res.text
    assert "Ask Grok" in res.text
    assert "Vault Inbox" in res.text
    assert "not auto-approved" in res.text


def test_education_studio_ask_partial(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _seed_education_vault(vault, tmp_path)
    monkeypatch.setenv("KNOWLEDGE_VAULT_PATH", str(vault))
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    from thread.config import get_settings

    get_settings.cache_clear()

    mock_result = CompletionResult(
        text="Thread-native explanation.",
        provider=LlmProvider.XAI,
        model="grok-4.3",
    )
    with patch(
        "thread.services.education_studio.complete",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        client = TestClient(create_app())
        res = client.post(
            "/partials/education/studio/ask",
            data={"suggestion": "Why living packet?"},
        )

    assert res.status_code == 200
    assert "Thread-native explanation" in res.text
    get_settings.cache_clear()