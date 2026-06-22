"""Incubator Advanced path — edit, polish, rejected list."""

from pathlib import Path

import pytest

from thread.config import Settings
from thread.services.incubator_capture import intent_from_incubator_body
from thread.services.incubator_rejected import list_rejected_seeds
from thread.services.vault_review_queue import load_candidate_edit_form
from thread.services.vault_write import load_candidate_note, save_candidate_note, write_incubator_note
from thread.db.models import ReviewRecord
from thread.services.review_gate import create_review_record


def test_intent_from_incubator_body():
    body = "## Intent\n\nNew process for capture.\n\n## Extract\n\nSummary."
    assert intent_from_incubator_body(body) == "New process for capture."


def test_save_candidate_note_syncs_incubator_intent(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    settings = Settings(knowledge_vault_path=vault)
    created = write_incubator_note(
        settings,
        name="Process Note",
        body="## Intent\n\nOriginal intent.\n\n## Source\n\n- **ingest:** `abc`",
        capture_kind="idea",
        intent="Original intent.",
        citations="source:fabric",
        source="test",
    )
    save_candidate_note(
        settings,
        created.path,
        name="Process Note",
        body="## Intent\n\nUpdated capture process intent.\n\n## Source\n\n- **ingest:** `abc`",
    )
    loaded = load_candidate_note(settings, created.path)
    assert loaded["intent"] == "Updated capture process intent."


def test_list_rejected_seeds(tmp_path: Path):
    vault = tmp_path / "vault"
    rejected = vault / "generated-projections" / "rejected"
    rejected.mkdir(parents=True)
    (rejected / "old-seed.md").write_text(
        "---\nname: Old Seed\ncapture_kind: document\nmaturity: seed\n---\n# Old\n",
        encoding="utf-8",
    )
    settings = Settings(knowledge_vault_path=vault)
    items = list_rejected_seeds(settings)
    assert len(items) == 1
    assert items[0].name == "Old Seed"
    assert items[0].capture_kind == "document"


@pytest.mark.asyncio
async def test_load_candidate_edit_form_incubator(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "generated-projections" / "sandbox" / "incubator").mkdir(parents=True)
    path = vault / "generated-projections" / "sandbox" / "incubator" / "test-seed-2026-06-22.md"
    path.write_text(
        "---\n"
        "name: Test Seed\n"
        "type: synthesis\n"
        "maturity: seed\n"
        "capture_kind: document\n"
        "intent: Doc intent\n"
        "ingest: abc123def456\n"
        "trust: candidate\n"
        "citations: source:fabric;ingest:abc123def456\n"
        "---\n"
        "# Test Seed\n\n"
        "> Seed — held in Incubator.\n\n"
        "## Intent\n\nDoc intent\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    record = await create_review_record(
        db_session,
        entity_type="vault_candidate",
        entity_id="generated-projections/sandbox/incubator/test-seed-2026-06-22.md",
    )
    form = load_candidate_edit_form(settings, record)
    assert form is not None
    assert form.is_incubator is True
    assert form.capture_kind == "document"
    assert form.ingest_id == "abc123def456"
    assert form.merge_targets == ()