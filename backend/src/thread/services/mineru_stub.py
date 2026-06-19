"""MinerU document parse — Phase 19 hook for quick capture + vault ingest."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from thread.config import Settings
from thread.services.mineru_client import (
    mineru_base_url,
    parse_staged_document,
    probe_mineru_health,
)

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
    """MinerU 3.3 FastAPI status for Insights/Clew panels."""
    enabled = bool(settings.mineru_enabled)
    reachable = probe_mineru_health(settings) if enabled else False
    if not enabled:
        status = "stub"
    elif reachable:
        status = "ready"
    else:
        status = "unreachable"
    base = mineru_base_url(settings)
    return {
        "product": "MinerU",
        "version": "3.3",
        "enabled": enabled,
        "reachable": reachable,
        "endpoint": base,
        "docs_url": f"{base}/docs",
        "status": status,
        "role": "Background parse API — Thread calls it from capture; no operator web UI.",
        "operator_path": "Use the floating capture FAB in Thread to upload documents.",
        "browser_note": "Opening the API root in a browser returns 404 — expected. /docs is dev API playground only.",
        "capture_extensions": sorted(ALL_CAPTURE_EXTENSIONS),
        "not_used": "Legacy third-party pdfparser forks — Thread uses MinerU only.",
        "start_hint": (
            "Autostarts with python app.py when MINERU_ENABLED=true; "
            "manual fallback: python -m mineru.cli.fast_api --host 127.0.0.1 --port 8888"
        ),
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


def _mineru_meta_block(staged: StagedDocument, *, status: str, lead: str, parsed_rel: str = "") -> str:
    lines = [
        f"## Document — {staged.filename}",
        "",
        f"> [!note] MinerU ingest · `{status}`",
        f"> {lead}",
        "",
        f"- **ingest_id:** `{staged.ingest_id}`",
        f"- **path:** `{staged.rel_path}`",
        f"- **size:** {staged.size_bytes:,} bytes",
        f"- **type:** `{staged.suffix}`",
    ]
    if parsed_rel:
        lines.append(f"- **parsed:** `{parsed_rel}`")
    return "\n".join(lines) + "\n"


def _mineru_placeholder_markdown(staged: StagedDocument, *, settings: Settings) -> str:
    if settings.mineru_enabled:
        lead = (
            f"MinerU enabled at {mineru_base_url(settings)} but parse did not complete. "
            "Staged source preserved — start MinerU FastAPI and re-capture or enrich later."
        )
        status = "mineru_error"
    else:
        lead = (
            "Document staged for MinerU 3.3. Set `MINERU_ENABLED=true` and run MinerU FastAPI "
            "to auto-extract structure and prose on capture."
        )
        status = "mineru_stub"
    return _mineru_meta_block(staged, status=status, lead=lead)


def _mineru_parsed_markdown(staged: StagedDocument, *, parsed_rel: str, body: str) -> str:
    lead = "Parsed via MinerU 3.3 FastAPI — full output also on disk."
    header = _mineru_meta_block(staged, status="mineru_parsed", lead=lead, parsed_rel=parsed_rel)
    return f"{header}\n### Extracted content\n\n{body.strip()}\n"


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

    source_kind = "mineru_stub"
    mineru_ready = False
    markdown = _mineru_placeholder_markdown(staged, settings=settings)

    if settings.mineru_enabled:
        parsed_kind, parsed_md, ready = _run_mineru_parse(settings, staged)
        markdown = parsed_md
        source_kind = parsed_kind
        mineru_ready = ready

    return DocumentExtract(
        filename=staged.filename,
        ingest_id=staged.ingest_id,
        ingest_rel=staged.rel_path,
        markdown=markdown,
        source_kind=source_kind,
        mineru_ready=mineru_ready,
    )


def _run_mineru_parse(
    settings: Settings,
    staged: StagedDocument,
) -> tuple[str, str, bool]:
    """Returns (source_kind, markdown, mineru_ready)."""
    fallback = _mineru_placeholder_markdown(staged, settings=settings)
    try:
        result = parse_staged_document(
            settings,
            ingest_id=staged.ingest_id,
            staged_path=staged.abs_path,
            filename=staged.filename,
        )
        return (
            "mineru",
            _mineru_parsed_markdown(staged, parsed_rel=result.parsed_rel, body=result.markdown),
            True,
        )
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        error_note = f"\n\n### Parse error\n\n`{exc}`\n"
        return ("mineru_error", fallback + error_note, False)


def mineru_parse_document(settings: Settings, staged_path: Path) -> str:
    """Invoke MinerU 3.3 on a staged file; return markdown for vault enrichment."""
    if not settings.mineru_enabled:
        raise MineruIngestError("MinerU is disabled — set MINERU_ENABLED=true")
    if not staged_path.is_file():
        raise MineruIngestError(f"Staged document missing: {staged_path}")

    ingest_id = staged_path.parent.name
    filename = staged_path.name
    try:
        result = parse_staged_document(
            settings,
            ingest_id=ingest_id,
            staged_path=staged_path,
            filename=filename,
        )
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        raise MineruIngestError(f"MinerU parse failed: {exc}") from exc
    return result.markdown