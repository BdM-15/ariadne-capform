"""Phase 19 prep — MinerU document staging for quick capture FAB."""

from pathlib import Path
from unittest.mock import patch

import pytest

from thread.config import Settings
from thread.services.capture_fab import CaptureFabError, build_capture_context, ingest_quick_capture, prepare_quick_capture
from thread.services.mineru_stub import (
    ALL_CAPTURE_EXTENSIONS,
    MineruIngestError,
    extract_document_for_capture,
    is_capture_document,
    is_mineru_document,
    stage_capture_document,
)


def test_mineru_extension_catalog_includes_pdf_and_office():
    assert ".pdf" in ALL_CAPTURE_EXTENSIONS
    assert ".docx" in ALL_CAPTURE_EXTENSIONS
    assert is_mineru_document("solicitation.PDF")
    assert is_capture_document("notes.md")


def test_stage_capture_document_writes_inbox(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    staged = stage_capture_document(settings, "rfp.pdf", b"%PDF-1.4 fake")
    assert staged.ingest_id
    assert staged.abs_path.is_file()
    assert "ingest/inbox" in staged.rel_path


def test_extract_pdf_stages_mineru_stub_markdown(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread", mineru_enabled=False)
    extracted = extract_document_for_capture(settings, "deck.pdf", b"%PDF stub")
    assert extracted.source_kind == "mineru_stub"
    assert "MinerU" in extracted.markdown
    assert extracted.ingest_id in extracted.markdown


def test_extract_pdf_when_mineru_enabled_parses(tmp_path: Path):
    from thread.services.mineru_client import MineruParseResult

    settings = Settings(thread_state_dir=tmp_path / ".thread", mineru_enabled=True)
    with patch(
        "thread.services.mineru_stub.parse_staged_document",
        return_value=MineruParseResult(
            markdown="# Deck Title\n\nParsed content with enough words here.",
            parsed_rel="ingest/parsed/abc/output.md",
        ),
    ):
        extracted = extract_document_for_capture(settings, "deck.pdf", b"%PDF stub")
    assert extracted.source_kind == "mineru"
    assert extracted.mineru_ready is True
    assert "Parsed content" in extracted.markdown
    assert "[!abstract] Extracted" in extracted.markdown
    assert extracted.glance_summary


def test_extract_pdf_when_mineru_unreachable_falls_back(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread", mineru_enabled=True)
    with patch(
        "thread.services.mineru_stub.parse_staged_document",
        side_effect=RuntimeError("connection refused"),
    ):
        extracted = extract_document_for_capture(settings, "deck.pdf", b"%PDF stub")
    assert extracted.source_kind == "mineru_error"
    assert extracted.mineru_ready is False
    assert "Parse error" in extracted.markdown


def test_prepare_quick_capture_document_only(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    ctx = build_capture_context()
    extracted = extract_document_for_capture(settings, "brief.pdf", b"%PDF")
    draft = prepare_quick_capture("", context=ctx, document=extracted)
    assert "Brief" in draft.name or "brief" in draft.name.lower()
    assert "MinerU" in draft.body


def test_unsupported_extension_rejected(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    with pytest.raises(MineruIngestError, match="Unsupported"):
        stage_capture_document(settings, "archive.zip", b"PK")


@pytest.mark.asyncio
async def test_ingest_quick_capture_pdf_only(db_session, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    settings = Settings(
        knowledge_vault_path=vault,
        thread_state_dir=tmp_path / ".thread",
        local_admin_model_enabled=False,
        mineru_enabled=False,
    )

    ctx = build_capture_context()
    result = await ingest_quick_capture(
        settings,
        db_session,
        raw_dump="",
        context=ctx,
        attachment_name="solicitation.pdf",
        attachment_bytes=b"%PDF-1.4",
    )
    assert result.document_name == "solicitation.pdf"
    assert result.mineru_status == "mineru_stub"
    text = (vault / result.write.path).read_text(encoding="utf-8")
    assert "ingest:" in text
    assert "MinerU" in text
    assert (tmp_path / ".thread" / "ingest" / "inbox").exists()


@pytest.mark.asyncio
async def test_ingest_requires_dump_or_document(db_session, settings):
    with pytest.raises(CaptureFabError, match="No text or file received"):
        await ingest_quick_capture(settings, db_session, raw_dump="", context=build_capture_context())