"""Operator education lane — lessons catalog + completion state."""

from pathlib import Path

from thread.config import Settings
from thread.services.operator_learning import (
    build_education_page_context,
    is_lesson_completed,
    list_education_lessons,
    load_operator_learning,
    set_lesson_completed,
)


def _seed_education_vault(vault: Path) -> None:
    lessons = vault / "education" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "01-living-packet-not-folder.md").write_text(
        """---
title: "Lesson 01 — Living packet"
id: education-lesson-01
lesson_number: 1
estimated_minutes: 12
---

# Lesson 01

Body text.
""",
        encoding="utf-8",
    )
    record = vault / "education" / "learning-records"
    record.mkdir(parents=True)
    (record / "ben.md").write_text(
        """# Learning record

## Learning (in progress)

- [ ] **Living packet vs folder** — [[lessons/01-living-packet-not-folder|Lesson 01]] assigned 2026-06-20
""",
        encoding="utf-8",
    )
    (vault / "education" / "MISSION.md").write_text(
        """---
title: Operator Mission
id: education-mission
---

# Operator mission

Why Thread exists.
""",
        encoding="utf-8",
    )


def test_list_education_lessons(settings: Settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _seed_education_vault(vault)
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    lessons = list_education_lessons(settings)
    assert len(lessons) == 1
    assert lessons[0].id == "education-lesson-01"
    assert lessons[0].lesson_number == 1
    assert lessons[0].completed is False


def test_set_lesson_completed_persists_state_and_syncs_record(
    settings: Settings, tmp_path, monkeypatch
):
    vault = tmp_path / "vault"
    _seed_education_vault(vault)
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")

    result = set_lesson_completed(settings, "education-lesson-01", completed=True)
    assert result is not None
    assert result.completed is True
    assert is_lesson_completed(settings, "education-lesson-01")

    state = load_operator_learning(settings)
    assert "education-lesson-01" in state["completed_lessons"]
    assert "education-lesson-01" in state["completed_at"]

    record_text = (vault / "education" / "learning-records" / "ben.md").read_text(
        encoding="utf-8"
    )
    assert "- [x] **Living packet vs folder**" in record_text

    set_lesson_completed(settings, "education-lesson-01", completed=False)
    record_text = (vault / "education" / "learning-records" / "ben.md").read_text(
        encoding="utf-8"
    )
    assert "- [ ] **Living packet vs folder**" in record_text


def test_build_education_page_context_defaults_to_first_incomplete(
    settings: Settings, tmp_path, monkeypatch
):
    vault = tmp_path / "vault"
    _seed_education_vault(vault)
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")

    ctx = build_education_page_context(settings)
    assert ctx.active_key == "mission"
    assert ctx.panel.kind == "mission"

    lesson_ctx = build_education_page_context(settings, lesson="education-lesson-01")
    assert lesson_ctx.active_key == "education-lesson-01"
    assert lesson_ctx.panel.kind == "lesson"
    content = lesson_ctx.panel.content or ""
    assert "Body text." in content
    assert "id: education-lesson-01" not in content
    assert "lesson_number:" not in content

    mission_ctx = build_education_page_context(settings, lesson="mission")
    mission_content = mission_ctx.panel.content or ""
    assert "Why Thread exists" in mission_content
    assert "type: education" not in mission_content
    assert "tags:" not in mission_content


def test_lesson_display_title_and_body_from_ingest_promoted_file(settings: Settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    lessons = vault / "education" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "02-messy.md").write_text(
        """---
name: edu-02-lesson-02-watch-vs-track-deciding-pursuit-intens-2026-06-21
type: education
id: education-lesson-02
lesson_number: 2
estimated_minutes: 12
---

# edu-02-lesson-02-watch-vs-track-deciding-pursuit-intens-2026-06-21

## Added/Updated 2026-06-21

# Lesson 02 — Watch vs Track

> [!abstract] Body here.

**Review:** `abc`

### Related
- [[capture-llm-wiki]]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    lessons_list = list_education_lessons(settings)
    assert len(lessons_list) == 1
    assert lessons_list[0].title == "Lesson 02 — Watch vs Track"
    assert lessons_list[0].estimated_minutes == 12

    ctx = build_education_page_context(settings, lesson="education-lesson-02")
    content = ctx.panel.content or ""
    assert "Body here." in content
    assert "Added/Updated" not in content
    assert "edu-02-lesson" not in content
    assert "**Review:**" not in content