"""Incubator capture — slim seeds, hold path, publish gate."""

from pathlib import Path

import pytest

from thread.config import Settings
from thread.services.capture_fab import build_capture_context, ingest_quick_capture, prepare_quick_capture
from thread.services.incubator_capture import (
    format_incubator_body,
    infer_capture_kind,
    is_incubator_path,
)
from thread.services.mineru_stub import DocumentExtract, extract_document_for_capture
from thread.services.vault_write import VaultWriteError, load_candidate_note, promote_vault_candidate, write_incubator_note
from thread.db.models import ReviewRecord


def test_is_incubator_path():
    assert is_incubator_path("generated-projections/incubator/foo-2026-06-22.md")
    assert is_incubator_path("generated-projections/sandbox/incubator/foo-2026-06-22.md")
    assert not is_incubator_path("generated-projections/foo-2026-06-22.md")


def test_format_incubator_body_slim_no_full_parse():
    doc = DocumentExtract(
        filename="receipt.pdf",
        ingest_id="abc123def456",
        ingest_rel="ingest/inbox/abc123def456/receipt.pdf",
        markdown="# Huge\n\n" + ("x" * 20_000),
        source_kind="mineru",
        mineru_ready=True,
        glance_summary="**Guest Folio** · MARTIN, BENJAMIN",
    )
    body = format_incubator_body(intent="Expense receipt for training", document=doc)
    assert "## Intent" in body
    assert "## Extract" in body
    assert "Guest Folio" in body
    assert "abc123def456" in body
    assert "x" * 1000 not in body


def test_prepare_quick_capture_incubator_excludes_full_mineru_md(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    ctx = build_capture_context()
    doc = extract_document_for_capture(settings, "note.pdf", b"%PDF-1.4")
    draft = prepare_quick_capture("my intent line", context=ctx, document=doc)
    assert "## Intent" in draft.body
    assert "my intent line" in draft.body
    assert "## Document —" not in draft.body


def test_infer_capture_kind():
    doc = DocumentExtract(
        filename="a.pdf",
        ingest_id="x",
        ingest_rel="y",
        markdown="",
        source_kind="mineru",
        mineru_ready=True,
    )
    assert infer_capture_kind(document=doc) == "document"
    assert infer_capture_kind(document=None, award_key="AWD-1") == "signal"
    assert infer_capture_kind(document=None) == "idea"


def test_write_incubator_note_frontmatter(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    settings = Settings(knowledge_vault_path=vault)
    result = write_incubator_note(
        settings,
        name="Edge Compute Lead",
        body="## Intent\n\nJason Gray mentioned edge capability.",
        capture_kind="idea",
        intent="Jason Gray mentioned edge capability.",
        citations="source:fabric",
    )
    assert "incubator/" in result.path
    text = (vault / result.path).read_text(encoding="utf-8")
    assert "maturity: seed" in text
    assert "capture_kind: idea" in text
    assert "> Seed — held in Incubator" in text


@pytest.mark.asyncio
async def test_ingest_quick_capture_writes_incubator(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox" / "incubator").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)

    result = await ingest_quick_capture(
        settings,
        db_session,
        raw_dump="Edge computing lead from Jason Gray",
        context=build_capture_context(),
    )
    assert "incubator/" in result.write.path
    assert result.polish_provider == "rules-incubator"
    loaded = load_candidate_note(settings, result.write.path)
    assert loaded.get("maturity") == "seed"
    assert loaded.get("capture_kind") == "idea"


def test_promote_blocks_incubator_seed(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    settings = Settings(knowledge_vault_path=vault)
    created = write_incubator_note(
        settings,
        name="Blocked Seed",
        body="## Intent\n\nHold only.",
        capture_kind="idea",
        intent="Hold only.",
        citations="source:fabric",
        source="test",
    )
    record = ReviewRecord(
        entity_type="vault_candidate",
        entity_id=created.path,
        trust_level="trusted",
        review_state="accepted",
    )
    with pytest.raises(VaultWriteError, match="Incubator seed cannot publish"):
        promote_vault_candidate(settings, record)