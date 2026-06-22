"""Layer 1 ingest parse — read-only preview for incubator seed editing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thread.config import Settings
from thread.services.mineru_markdown import normalize_mineru_body


@dataclass(frozen=True)
class IngestParsePreview:
    ingest_id: str
    rel_path: str
    filename: str
    markdown: str
    char_count: int
    source: str  # parsed | staged


def _thread_root(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir)


def load_ingest_parse_preview(settings: Settings, ingest_id: str) -> IngestParsePreview | None:
    """Load full parse from disk for read-only display while editing a seed."""
    clean_id = (ingest_id or "").strip()
    if not clean_id:
        return None

    root = _thread_root(settings)
    parsed_path = root / "ingest" / "parsed" / clean_id / "output.md"
    if parsed_path.is_file():
        raw = parsed_path.read_text(encoding="utf-8")
        display = normalize_mineru_body(raw)
        return IngestParsePreview(
            ingest_id=clean_id,
            rel_path=parsed_path.relative_to(root).as_posix(),
            filename="output.md",
            markdown=display,
            char_count=len(raw),
            source="parsed",
        )

    inbox_dir = root / "ingest" / "inbox" / clean_id
    if inbox_dir.is_dir():
        files = sorted(path for path in inbox_dir.iterdir() if path.is_file())
        if files:
            staged = files[0]
            try:
                text = staged.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return None
            return IngestParsePreview(
                ingest_id=clean_id,
                rel_path=staged.relative_to(root).as_posix(),
                filename=staged.name,
                markdown=text.strip(),
                char_count=len(text),
                source="staged",
            )
    return None