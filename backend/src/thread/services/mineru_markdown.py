"""Normalize MinerU markdown for vault candidates — readable at a glance."""

from __future__ import annotations

import re
from html import unescape


def html_tables_to_markdown(text: str) -> str:
    """MinerU often emits raw HTML tables; Obsidian needs pipe tables."""

    def _table_to_md(match: re.Match[str]) -> str:
        rows = re.findall(r"<tr>(.*?)</tr>", match.group(0), flags=re.I | re.S)
        md_rows: list[str] = []
        for index, row in enumerate(rows):
            cells = re.findall(r"<t[dh]>(.*?)</t[dh]>", row, flags=re.I | re.S)
            cleaned = [_clean_cell(cell) for cell in cells]
            if not cleaned or not any(cleaned):
                continue
            md_rows.append("| " + " | ".join(cleaned) + " |")
            if index == 0:
                md_rows.append("| " + " | ".join("---" for _ in cleaned) + " |")
        if not md_rows:
            return ""
        return "\n".join(md_rows) + "\n\n"

    return re.sub(r"<table>.*?</table>", _table_to_md, text, flags=re.I | re.S)


def _clean_cell(raw: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", text).strip()


def _strip_embedded_images(text: str) -> str:
    return re.sub(
        r"!\[[^\]]*\]\(images/[^)]+\)",
        "_\\[logo/image omitted — not bundled in vault candidate\\]_",
        text,
    )


def _demote_heading_spam(text: str) -> str:
    """Keep one H1; demote MinerU's label-everything-as-H1 pattern."""
    lines = text.splitlines()
    out: list[str] = []
    seen_h1 = False
    for line in lines:
        if re.match(r"^#\s+", line):
            if not seen_h1:
                out.append(line)
                seen_h1 = True
            else:
                title = line.lstrip("#").strip()
                out.append(f"### {title}")
            continue
        out.append(line)
    return "\n".join(out)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def summarize_mineru_body(body: str, *, filename: str) -> str:
    """One-line glance summary for callouts and FAB success flash."""
    text = body.strip()
    bits: list[str] = []

    title = re.search(r"^#\s+(.+)$", text, re.M)
    if title:
        bits.append(f"**{title.group(1).strip()}**")

    guest = re.search(r"\b([A-Z][A-Z' -]+,\s*[A-Z][A-Z' -]+)\b", text)
    if guest:
        bits.append(guest.group(1).strip())

    conf = re.search(r"Confirmation(?:\s+Number)?\s*[-#:]?\s*(\d{6,})", text, re.I)
    if conf:
        bits.append(f"conf {conf.group(1)}")

    dates = re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b",
        text,
    )
    if len(dates) >= 2:
        bits.append(f"{dates[0]} → {dates[1]}")
    elif len(dates) == 1:
        bits.append(dates[0])

    total = re.search(
        r"(?:Folio Balance|Total|Amount Due)[^\$]*(\$[\d,]+\.\d{2})",
        text,
        re.I | re.S,
    )
    if total:
        bits.append(f"balance {total.group(1)}")

    payment = re.search(r"Payments[^\$]*(\$[\d,]+\.\d{2})", text, re.I | re.S)
    if payment and not total:
        bits.append(f"paid {payment.group(1)}")

    if not bits:
        words = len(re.findall(r"\w+", text))
        stem = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        bits.append(f"**{stem}** — {words:,} words extracted")

    return " · ".join(bits)


def normalize_mineru_body(raw: str) -> str:
    """Vault-friendly markdown from MinerU GPU output."""
    text = raw.strip()
    text = html_tables_to_markdown(text)
    text = _strip_embedded_images(text)
    text = _demote_heading_spam(text)
    return _collapse_blank_lines(text)


def format_mineru_vault_document(
    *,
    filename: str,
    ingest_id: str,
    ingest_rel: str,
    parsed_rel: str,
    raw_body: str,
) -> str:
    """Document section for vault candidate — summary first, readable body, source footer."""
    normalized = normalize_mineru_body(raw_body)
    summary = summarize_mineru_body(normalized, filename=filename)
    return "\n".join(
        [
            f"## Document — {filename}",
            "",
            "> [!abstract] Extracted",
            f"> {summary}",
            "",
            normalized,
            "",
            "---",
            (
                f"_Source:_ `{ingest_rel}` · _Parse on disk:_ `{parsed_rel}` · "
                f"_ingest:_ `{ingest_id}`"
            ),
            "",
        ]
    )