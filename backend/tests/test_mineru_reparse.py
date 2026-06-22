"""MinerU re-parse from staged inbox — no re-upload."""

from pathlib import Path
from unittest.mock import patch

import pytest

from thread.config import Settings
from thread.services.mineru_client import MineruParseResult
from thread.services.mineru_reparse import (
    MineruReparseError,
    ingest_id_from_citations,
    mineru_parse_failed_in_body,
    operator_notes_after_document,
    reparse_candidate_document,
    staged_file_for_ingest,
)
from thread.services.vault_write import write_candidate_note


def test_ingest_id_from_citations():
    cites = "source:fabric;ingest:dc1a11067e93;ingest_path:ingest/inbox/dc1a/file.pdf"
    assert ingest_id_from_citations(cites) == "dc1a11067e93"


def test_operator_notes_after_document_footer():
    body = (
        "## Document — trip.pdf\n\n"
        "> [!abstract] Extracted\n> summary\n\n"
        "# Folio\n\n"
        "---\n"
        "_Source:_ `ingest/inbox/x/trip.pdf` · _Parse on disk:_ `out.md` · _ingest:_ `x`\n\n"
        "Here is a hotel receipt example for expense automation"
    )
    assert operator_notes_after_document(body) == "Here is a hotel receipt example for expense automation"


def test_staged_file_for_ingest(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    ingest_id = "abc123def456"
    inbox = settings.resolve(settings.thread_state_dir) / "ingest" / "inbox" / ingest_id
    inbox.mkdir(parents=True)
    (inbox / "receipt.pdf").write_bytes(b"%PDF")
    found = staged_file_for_ingest(settings, ingest_id)
    assert found is not None
    assert found[1] == "receipt.pdf"


def test_reparse_candidate_document_success(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")

    settings = Settings(
        knowledge_vault_path=vault,
        thread_state_dir=tmp_path / ".thread",
        mineru_enabled=True,
    )
    ingest_id = "abc123def456"
    inbox = settings.resolve(settings.thread_state_dir) / "ingest" / "inbox" / ingest_id
    inbox.mkdir(parents=True)
    (inbox / "folio.pdf").write_bytes(b"%PDF")

    cites = f"source:fabric;ingest:{ingest_id};ingest_path:ingest/inbox/{ingest_id}/folio.pdf"
    write_result = write_candidate_note(
        settings,
        name="Hotel Folio",
        body=(
            "## Document — folio.pdf\n\n"
            "> [!note] MinerU ingest · `mineru_error`\n\n"
            "### Parse error\n\n`connection refused`\n\n"
            "expense automation notes"
        ),
        page_type="synthesis",
        citations=cites,
    )

    with (
        patch("thread.services.mineru_reparse.probe_mineru_health", return_value=True),
        patch(
            "thread.services.mineru_reparse.parse_staged_document",
            return_value=MineruParseResult(
                markdown="# Guest Folio\n\nMARTIN, BENJAMIN\n\n"
                "<table><tr><td>Total</td><td>$10.00</td></tr></table>",
                parsed_rel=f"ingest/parsed/{ingest_id}/output.md",
            ),
        ),
    ):
        result = reparse_candidate_document(settings, write_result.path)

    assert result.mineru_ready is True
    assert "Guest Folio" in result.glance_summary
    text = (vault / write_result.path).read_text(encoding="utf-8")
    assert "[!abstract] Extracted" in text
    assert "expense automation notes" in text
    assert "mineru_error" not in text


def test_reparse_requires_ingest_id(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    settings = Settings(knowledge_vault_path=vault, thread_state_dir=tmp_path / ".thread")
    write_result = write_candidate_note(
        settings,
        name="Note",
        body="plain text",
        page_type="synthesis",
        citations="source:fabric",
    )
    with patch("thread.services.mineru_reparse.probe_mineru_health", return_value=True):
        with pytest.raises(MineruReparseError, match="No staged ingest"):
            reparse_candidate_document(settings, write_result.path)


def test_mineru_parse_failed_in_body():
    assert mineru_parse_failed_in_body("> `mineru_error`") is True