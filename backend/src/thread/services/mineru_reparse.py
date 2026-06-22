"""Re-run MinerU on staged inbox files — no re-upload."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from thread.config import Settings
from thread.services.mineru_client import parse_staged_document
from thread.services.mineru_markdown import format_mineru_vault_document, summarize_mineru_body
from thread.services.mineru_stub import probe_mineru_health
from thread.services.incubator_capture import format_incubator_body, is_incubator_path
from thread.services.mineru_stub import DocumentExtract
from thread.services.vault_write import VaultWriteError, load_candidate_note, save_candidate_note

_INGEST_ID_RE = re.compile(r"ingest:([a-f0-9]{12})")
_INGEST_PATH_RE = re.compile(r"ingest_path:([^\s;]+)")


class MineruReparseError(Exception):
    pass


@dataclass(frozen=True)
class MineruReparseResult:
    candidate_path: str
    ingest_id: str
    filename: str
    glance_summary: str
    mineru_ready: bool
    error: str = ""


def ingest_id_from_citations(citations: str) -> str:
    match = _INGEST_ID_RE.search(citations or "")
    return match.group(1) if match else ""


def mineru_parse_failed_in_body(body: str) -> bool:
    text = body or ""
    return (
        "mineru_error" in text
        or ("Parse error" in text and "MinerU HTTP" in text)
        or "Parse failed — staged source preserved" in text
    )


def mineru_parsed_in_body(body: str) -> bool:
    return "[!abstract] Extracted" in (body or "") or "mineru_parsed" in (body or "")


def operator_notes_after_document(body: str) -> str:
    """Brain dump and context footer kept below the document ingest block."""
    text = (body or "").replace("\r\n", "\n")
    if "## Document —" not in text:
        return ""

    cut = 0
    for pattern in (
        re.compile(r"_ingest:_\s*`[^`]+`"),
        re.compile(r"^- \*\*ingest_id:\*\*[^\n]+$", re.M),
        re.compile(r"^_Source:_.*$", re.M),
    ):
        for match in pattern.finditer(text):
            cut = max(cut, match.end())

    if "### Parse error" in text:
        err_tail = text.split("### Parse error", 1)[1]
        tick = re.search(r"`[^`]+`", err_tail)
        if tick:
            base = text.index("### Parse error") + len("### Parse error") + tick.end()
            cut = max(cut, base)

    if cut <= 0:
        return ""

    tail = text[cut:].strip()
    tail = re.sub(r"^---\s*\n", "", tail)
    return tail.strip()


def staged_file_for_ingest(settings: Settings, ingest_id: str) -> tuple[Path, str] | None:
    if not ingest_id:
        return None
    inbox_dir = settings.resolve(settings.thread_state_dir) / "ingest" / "inbox" / ingest_id
    if not inbox_dir.is_dir():
        return None
    files = sorted(path for path in inbox_dir.iterdir() if path.is_file())
    if not files:
        return None
    staged = files[0]
    return staged, staged.name


def reparse_candidate_document(settings: Settings, candidate_rel: str) -> MineruReparseResult:
    """Parse staged source again and refresh the document section on a vault candidate."""
    if not settings.mineru_enabled:
        raise MineruReparseError("MinerU is disabled — set MINERU_ENABLED=true")
    if not probe_mineru_health(settings):
        raise MineruReparseError(
            "MinerU API not reachable — wait for parser at "
            f"{settings.mineru_local_endpoint} or restart python app.py"
        )

    try:
        loaded = load_candidate_note(settings, candidate_rel)
    except VaultWriteError as exc:
        raise MineruReparseError(str(exc)) from exc

    citations = str(loaded.get("citations") or "")
    ingest_id = ingest_id_from_citations(citations)
    if not ingest_id:
        raise MineruReparseError("No staged ingest id on this candidate — re-upload the file")

    staged = staged_file_for_ingest(settings, ingest_id)
    if staged is None:
        raise MineruReparseError(f"Staged file missing for ingest `{ingest_id}` — re-upload the document")

    staged_path, filename = staged
    operator_tail = operator_notes_after_document(str(loaded.get("body") or ""))

    try:
        parsed = parse_staged_document(
            settings,
            ingest_id=ingest_id,
            staged_path=staged_path,
            filename=filename,
        )
    except (OSError, RuntimeError, httpx.HTTPError) as exc:
        return MineruReparseResult(
            candidate_path=candidate_rel,
            ingest_id=ingest_id,
            filename=filename,
            glance_summary="",
            mineru_ready=False,
            error=str(exc),
        )

    ingest_rel = _INGEST_PATH_RE.search(citations)
    rel_path = ingest_rel.group(1) if ingest_rel else f"ingest/inbox/{ingest_id}/{filename}"
    summary = summarize_mineru_body(parsed.markdown, filename=filename)

    if is_incubator_path(candidate_rel):
        intent = str(loaded.get("intent") or loaded.get("name") or "")
        if "## Intent" in str(loaded.get("body") or ""):
            intent_block = str(loaded.get("body") or "").split("## Intent", 1)[1]
            intent_block = intent_block.split("##", 1)[0].strip()
            if intent_block:
                intent = intent_block
        document = DocumentExtract(
            filename=filename,
            ingest_id=ingest_id,
            ingest_rel=rel_path,
            markdown=parsed.markdown,
            source_kind="mineru",
            mineru_ready=True,
            glance_summary=summary,
        )
        new_body = format_incubator_body(intent=intent, document=document)
    else:
        doc_block = format_mineru_vault_document(
            filename=filename,
            ingest_id=ingest_id,
            ingest_rel=rel_path,
            parsed_rel=parsed.parsed_rel,
            raw_body=parsed.markdown,
        )
        new_body = doc_block.rstrip()
        if operator_tail:
            new_body = f"{new_body}\n\n{operator_tail}\n"

    save_candidate_note(
        settings,
        candidate_rel,
        name=str(loaded.get("name") or ""),
        body=new_body,
        page_type=str(loaded.get("page_type") or "synthesis"),
        related=list(loaded.get("related") or ()),
    )

    if not summary:
        summary = summarize_mineru_body(parsed.markdown, filename=filename)
    return MineruReparseResult(
        candidate_path=candidate_rel,
        ingest_id=ingest_id,
        filename=filename,
        glance_summary=summary,
        mineru_ready=True,
    )