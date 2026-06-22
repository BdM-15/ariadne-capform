"""Layer 1 parse preview for incubator seed editing."""

from pathlib import Path

from thread.config import Settings
from thread.services.ingest_parse_view import load_ingest_parse_preview


def test_load_ingest_parse_preview_from_parsed(tmp_path: Path):
    root = tmp_path / ".thread"
    ingest_id = "545054fb5fce"
    parsed = root / "ingest" / "parsed" / ingest_id / "output.md"
    parsed.parent.mkdir(parents=True)
    parsed.write_text("# Folio\n\n**Tab Responsibility: Capture Manager**\n", encoding="utf-8")
    settings = Settings(thread_state_dir=root)
    preview = load_ingest_parse_preview(settings, ingest_id)
    assert preview is not None
    assert preview.source == "parsed"
    assert "Capture Manager" in preview.markdown
    assert preview.char_count > 0


def test_load_ingest_parse_preview_falls_back_to_staged(tmp_path: Path):
    root = tmp_path / ".thread"
    ingest_id = "abc123def456"
    staged = root / "ingest" / "inbox" / ingest_id / "note.md"
    staged.parent.mkdir(parents=True)
    staged.write_text("# Hello\n\nInline body.\n", encoding="utf-8")
    settings = Settings(thread_state_dir=root)
    preview = load_ingest_parse_preview(settings, ingest_id)
    assert preview is not None
    assert preview.source == "staged"
    assert "Hello" in preview.markdown