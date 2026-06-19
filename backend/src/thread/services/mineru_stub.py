"""MinerU document parse — Phase 19 hook for quick capture + vault ingest."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings

# MinerU 3.3 / Theseus-supported ingest types (expand when Phase 19 wires docker).
MINERU_CAPTURE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".html",
        ".htm",
        ".epub",
        ".mobi",
    }
)

INLINE_TEXT_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".markdown"})

ALL_CAPTURE_EXTENSIONS: frozenset[str] = MINERU_CAPTURE_EXTENSIONS | INLINE_TEXT_EXTENSIONS

_DEFAULT_MAX_BYTES = 25 * 1024 * 1024


class MineruIngestError(Exception):
    pass


@dataclass(frozen=True)
class StagedDocument:
    ingest_id: str
    filename: str
    rel_path: str
    abs_path: Path
    size_bytes: int
    suffix: str


@dataclass(frozen=True)
class DocumentExtract:
    filename: str
    ingest_id: str
    ingest_rel: str
    markdown: str
    source_kind: str
    mineru_ready: bool


def mineru_ingest_status(settings: Settings) -> dict[str, Any]:
    """Theseus uses MinerU 3.3; Thread wires ingest when MINERU_ENABLED=true."""
    enabled = bool(settings.mineru_enabled)
    return {
        "product": "MinerU",
        "version": "3.3",
        "enabled": enabled,
        "status": "ready" if enabled else "stub",
        "role": "Any document → structured markdown → vault candidate (Phase 19).",
        "capture_extensions": sorted(ALL_CAPTURE_EXTENSIONS),
        "not_used": "Legacy third-party pdfparser forks — Thread uses MinerU only.",
        "theseus_note": "MinerU 3.3 already runs on Theseus; enable here when docker pipeline lands.",
    }


def is_inline_text_document(filename: str) -> bool:
    return Path(filename).suffix.lower() in INLINE_TEXT_EXTENSIONS


def is_mineru_document(filename: str) -> bool:
    return Path(filename).suffix.lower() in MINERU_CAPTURE_EXTENSIONS


def is_capture_document(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALL_CAPTURE_EXTENSIONS


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\- ]+", "_", base).strip("._ ")
    return cleaned or "document"


def _ingest_inbox_root(settings: Settings) -> Path:
    root = settings.resolve(settings.thread_state_dir) / "ingest" / "inbox"
    root.mkdir(parents=True, exist_ok=True)
    return root


def stage_capture_document(
    settings: Settings,
    filename: str,
    data: bytes,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> StagedDocument:
    if not filename or not data:
        raise MineruIngestError("Document upload is empty")
    if len(data) > max_bytes:
        raise MineruIngestError(f"Document too large (max {max_bytes // (1024 * 1024)}MB)")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALL_CAPTURE_EXTENSIONS:
        supported = ", ".join(sorted(ALL_CAPTURE_EXTENSIONS))
        raise MineruIngestError(f"Unsupported type {suffix or '(none)'} — MinerU accepts: {supported}")

    ingest_id = uuid.uuid4().hex[:12]
    safe = _safe_filename(filename)
    dest_dir = _ingest_inbox_root(settings) / ingest_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)
    rel = dest.relative_to(settings.resolve(settings.thread_state_dir)).as_posix()
    return StagedDocument(
        ingest_id=ingest_id,
        filename=safe,
        rel_path=rel,
        abs_path=dest,
        size_bytes=len(data),
        suffix=suffix,
    )


def _mineru_placeholder_markdown(staged: StagedDocument, *, settings: Settings) -> str:
    enabled = bool(settings.mineru_enabled)
    if enabled:
        lead = (
            "MinerU is enabled — parse job will run server-side (Phase 19 docker wire). "
            "Candidate queued with staged source; re-run enrich after parse completes."
        )
        status = "mineru_queued"
    else:
        lead = (
            "Document staged for MinerU 3.3. Enable `MINERU_ENABLED` in Settings when the "
            "docker pipeline lands (Phase 19) — platform will extract structure and prose automatically."
        )
        status = "mineru_stub"

    return (
        f"## Document — {staged.filename}\n\n"
        f"> [!note] MinerU ingest · `{status}`\n"
        f"> {lead}\n\n"
        f"- **ingest_id:** `{staged.ingest_id}`\n"
        f"- **path:** `{staged.rel_path}`\n"
        f"- **size:** {staged.size_bytes:,} bytes\n"
        f"- **type:** `{staged.suffix}`\n"
    )


def extract_document_for_capture(
    settings: Settings,
    filename: str,
    data: bytes,
) -> DocumentExtract:
    """Stage upload and return markdown for vault candidate body."""
    staged = stage_capture_document(settings, filename, data)

    if is_inline_text_document(filename):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MineruIngestError("Text attachment must be UTF-8 (.txt or .md)") from exc
        return DocumentExtract(
            filename=staged.filename,
            ingest_id=staged.ingest_id,
            ingest_rel=staged.rel_path,
            markdown=f"## Source file — {staged.filename}\n\n{text.strip()}\n",
            source_kind="inline_text",
            mineru_ready=True,
        )

    markdown = _mineru_placeholder_markdown(staged, settings=settings)
    if settings.mineru_enabled:
        # Phase 19: replace body with mineru_parse_document(staged.abs_path) output.
        markdown = _run_mineru_parse_stub(settings, staged, markdown)

    return DocumentExtract(
        filename=staged.filename,
        ingest_id=staged.ingest_id,
        ingest_rel=staged.rel_path,
        markdown=markdown,
        source_kind="mineru" if settings.mineru_enabled else "mineru_stub",
        mineru_ready=bool(settings.mineru_enabled),
    )


def _run_mineru_parse_stub(settings: Settings, staged: StagedDocument, fallback: str) -> str:
    """Placeholder until Phase 19 docker MinerU invocation ships."""
    del settings
    return (
        fallback
        + "\n\n### Parse output (pending)\n\n"
        "_MinerU docker hook not wired yet — staged file preserved for batch parse._\n"
    )


def mineru_parse_document(settings: Settings, staged_path: Path) -> str:
    """Phase 19 entry — invoke MinerU 3.3 on a staged file, return markdown."""
    if not settings.mineru_enabled:
        raise MineruIngestError("MinerU is disabled — set MINERU_ENABLED=true")
    if not staged_path.is_file():
        raise MineruIngestError(f"Staged document missing: {staged_path}")
    # Real implementation: subprocess/docker Theseus MinerU API.
    raise NotImplementedError("MinerU docker parse — Phase 19")