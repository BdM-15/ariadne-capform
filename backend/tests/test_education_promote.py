"""Education lesson promote — clean curriculum format on approve."""

from pathlib import Path

from thread.config import Settings
from thread.db.models import ReviewRecord
from thread.domain.enums import ReviewState, TrustLevel
from thread.services.vault_write import _extract_education_lesson_body, promote_vault_candidate


def test_extract_education_lesson_body_strips_ingest_wrapper():
    body = """# edu-02-lesson-02-watch-2026-06-21

## Added/Updated 2026-06-21

# Lesson 02 — Watch vs Track

> [!abstract] Core idea.

**Review:** `id`

### Related
- [[capture-llm-wiki]]
"""
    cleaned = _extract_education_lesson_body(body)
    assert "Lesson 02 — Watch vs Track" in cleaned
    assert "Core idea." in cleaned
    assert "Added/Updated" not in cleaned
    assert "edu-02-lesson" not in cleaned
    assert "capture-llm-wiki" not in cleaned


def test_promote_education_lesson_writes_curriculum_frontmatter(
    settings: Settings, tmp_path, monkeypatch
):
    vault = tmp_path / "vault"
    candidate = vault / "generated-projections" / "edu-02-watch-2026-06-21.md"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
        """---
title: "Lesson 02 — Watch vs Track"
name: "Lesson 02 — Watch vs Track"
type: education
id: education-lesson-02
lesson_number: 2
estimated_minutes: 12
tags: [education, lesson, draft]
promote_target: education/lessons/02-watch-vs-track.md
---

# Lesson 02 — Watch vs Track

> [!abstract] Abstract text.

## Who this is for
Operators.
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)

    record = ReviewRecord(
        entity_type="vault_candidate",
        entity_id="generated-projections/edu-02-watch-2026-06-21.md",
        trust_level=TrustLevel.CANDIDATE.value,
        review_state=ReviewState.PENDING_REVIEW.value,
        provenance=[{"kind": "vault_candidate", "ref": candidate.as_posix(), "target": "education/lessons/02-watch-vs-track.md"}],
    )

    result = promote_vault_candidate(settings, record)
    assert result is not None
    promoted = vault / "education" / "lessons" / "02-watch-vs-track.md"
    assert promoted.is_file()
    text = promoted.read_text(encoding="utf-8")
    assert 'title: "Lesson 02 — Watch vs Track"' in text or "title: Lesson 02" in text
    assert "lesson_number: 2" in text
    assert "estimated_minutes: 12" in text
    assert "Added/Updated" not in text
    assert "Abstract text." in text
    assert not candidate.is_file()