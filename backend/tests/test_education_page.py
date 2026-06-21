"""Education page — HTMX curriculum browser (Phase 22c)."""

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_education_page_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_education_page_loads():
    client = TestClient(create_app())
    res = client.get("/education")
    assert res.status_code == 200
    assert "education-body" in res.text
    assert "education-lesson-list" in res.text
    assert "education-lesson-panel" in res.text
    assert "graduation-cap" in res.text or "Education" in res.text
    assert "marked.min.js" in res.text
    assert "vault_markdown.js" in res.text


def test_education_page_shows_lesson_one(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    lessons = vault / "education" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "01-living-packet-not-folder.md").write_text(
        """---
title: "Lesson 01 — Living packet"
id: education-lesson-01
lesson_number: 1
---

# Lesson 01

Packet beats folder.
""",
        encoding="utf-8",
    )
    (vault / "education" / "MISSION.md").write_text("# Mission\n", encoding="utf-8")

    monkeypatch.setenv("KNOWLEDGE_VAULT_PATH", str(vault))
    from thread.config import get_settings

    get_settings.cache_clear()
    client = TestClient(create_app())
    res = client.get("/education?lesson=education-lesson-01")
    assert res.status_code == 200
    assert "Packet beats folder." in res.text
    assert "Mark complete" in res.text
    get_settings.cache_clear()


def test_education_mark_complete_updates_progress(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    lessons = vault / "education" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "01-test-lesson.md").write_text(
        """---
title: Test lesson
id: education-lesson-test
lesson_number: 1
---

# Test

Done reading.
""",
        encoding="utf-8",
    )
    (vault / "education" / "MISSION.md").write_text("# Mission\n", encoding="utf-8")

    state_dir = tmp_path / ".thread"
    monkeypatch.setenv("KNOWLEDGE_VAULT_PATH", str(vault))
    monkeypatch.setenv("THREAD_STATE_DIR", str(state_dir))
    from thread.config import get_settings

    get_settings.cache_clear()
    client = TestClient(create_app())
    res = client.post(
        "/partials/education/lesson/education-lesson-test/complete",
        data={"completed": "true"},
    )
    assert res.status_code == 200
    assert "Complete" in res.text
    assert "1/1 done" in res.text
    assert (state_dir / "operator_learning.json").is_file()
    get_settings.cache_clear()