"""Incubator capture — fast hold layer before develop → publish."""

from __future__ import annotations

from thread.services.mineru_stub import DocumentExtract
from thread.services.vault_inbox_display import extract_dump_snippet

INCUBATOR_PREFIX = "generated-projections/incubator/"
SANDBOX_INCUBATOR_PREFIX = "generated-projections/sandbox/incubator/"


def is_incubator_path(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/")
    return rel.startswith(INCUBATOR_PREFIX) or rel.startswith(SANDBOX_INCUBATOR_PREFIX)


def infer_capture_kind(
    *,
    document: DocumentExtract | None,
    award_key: str = "",
) -> str:
    if document:
        return "document"
    if (award_key or "").strip():
        return "signal"
    return "idea"


def build_incubator_intent(raw_dump: str, *, document: DocumentExtract | None) -> str:
    dump = (raw_dump or "").strip()
    if dump:
        snippet = extract_dump_snippet(dump, limit=200)
        return snippet or dump[:200]
    if document:
        return f"Document capture — {document.filename}"
    return "Quick capture"


def intent_from_incubator_body(body: str) -> str:
    """Extract ## Intent section for frontmatter sync on save."""
    text = (body or "").replace("\r\n", "\n")
    if "## Intent" not in text:
        return ""
    block = text.split("## Intent", 1)[1]
    if "##" in block:
        block = block.split("##", 1)[0]
    return block.strip()[:240]


def format_incubator_body(
    *,
    intent: str,
    document: DocumentExtract | None,
    context_footer: str = "",
) -> str:
    parts = ["## Intent", "", intent.strip()]

    if document:
        parts.extend(["", "## Extract", ""])
        summary = (document.glance_summary or "").strip()
        if summary:
            parts.append(summary)
        elif document.source_kind == "inline_text":
            parts.append(extract_dump_snippet(document.markdown) or "(inline text file)")
        elif document.source_kind == "mineru_error":
            parts.append("> Parse failed — staged source preserved. Re-parse in Advanced when MinerU is up.")
        else:
            parts.append("> Full parse on disk — not embedded in this seed note.")

        parts.extend(["", "## Source", ""])
        parts.append(f"- **ingest:** `{document.ingest_id}`")
        parts.append(f"- **path:** `{document.ingest_rel}`")
        if document.mineru_ready and document.source_kind == "mineru":
            parts.append(f"- **parsed:** `.thread/ingest/parsed/{document.ingest_id}/`")

    body = "\n".join(parts)
    footer = (context_footer or "").strip()
    if footer:
        body = f"{body.rstrip()}\n\n{footer}\n"
    return body