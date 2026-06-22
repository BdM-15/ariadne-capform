"""Plain-language labels for Vault Inbox review cards."""

from __future__ import annotations

import re

_PAGE_TYPE_LABELS: dict[str, str] = {
    "synthesis": "Knowledge note",
    "concept": "Framework / concept",
    "framework": "Framework",
    "process": "Process note",
    "agency": "Agency profile",
    "competitor": "Competitor profile",
    "opportunity": "Pursuit intel",
    "competition": "Competitive intel",
}

_STRIP_LINE_PATTERNS = (
    re.compile(r"^>\s*Candidate\b.*$", re.IGNORECASE),
    re.compile(r"^>\s*\[!note\].*$", re.IGNORECASE),
    re.compile(r"^>\s*Context\b.*$", re.IGNORECASE),
    re.compile(r"^#+\s+"),
)

_SLUG_TITLE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}-\d{4}-\d{2}-\d{2}$")


def page_type_label(page_type: str) -> str:
    key = (page_type or "synthesis").strip().lower()
    return _PAGE_TYPE_LABELS.get(key, key.replace("_", " ").title() or "Vault note")


_CAPTURE_KIND_LABELS: dict[str, str] = {
    "idea": "Idea",
    "document": "Document",
    "signal": "Signal",
}

_MATURITY_LABELS: dict[str, str] = {
    "seed": "Held",
    "developing": "Developing",
    "ready": "Ready to publish",
}


def capture_kind_label(capture_kind: str) -> str:
    key = (capture_kind or "idea").strip().lower()
    return _CAPTURE_KIND_LABELS.get(key, key.replace("_", " ").title() or "Capture")


def maturity_label(maturity: str) -> str:
    key = (maturity or "").strip().lower()
    return _MATURITY_LABELS.get(key, key.replace("_", " ").title() or "")


def build_incubator_intent_line(
    *,
    capture_kind: str,
    intent: str,
    title: str,
) -> str:
    kind = capture_kind_label(capture_kind)
    clean_intent = (intent or title or "Untitled").strip()
    if len(clean_intent) > 96:
        clean_intent = clean_intent[:95].rstrip() + "…"
    return f"{kind} seed — {clean_intent}"


def build_intent_line(*, page_type: str, title: str, promote_summary: str) -> str:
    label = page_type_label(page_type)
    clean_title = (title or "Untitled").strip()
    summary = (promote_summary or "New trusted page").strip()
    if summary.lower().startswith("new trusted"):
        return f"{label} — {summary}"
    return f"{label} — «{clean_title[:72]}»"


def _looks_like_slug(value: str) -> bool:
    text = (value or "").strip()
    if not text or " " in text:
        return False
    return bool(_SLUG_TITLE_RE.match(text)) or text.count("-") >= 4


def display_title(name: str, *, candidate_path: str = "") -> str:
    """Prefer frontmatter name; recover from slug-like stems when needed."""
    clean = (name or "").strip()
    if clean and not _looks_like_slug(clean):
        return clean
    stem = clean or candidate_path.replace("\\", "/").split("/")[-1].removesuffix(".md")
    if _SLUG_TITLE_RE.match(stem):
        stem = stem.rsplit("-", 3)[0]
    phrase = stem.replace("-", " ")
    return " ".join(word.capitalize() for word in phrase.split() if word)[:72] or "Untitled"


def extract_dump_snippet(body: str, *, limit: int = 220) -> str:
    """Pull operator-facing text from a candidate body — strip boilerplate."""
    text = (body or "").replace("\r\n", "\n")
    if "## Related" in text:
        text = text.split("## Related", 1)[0]
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith(">") and "[!note]" in line.lower():
            continue
        skip = False
        for pattern in _STRIP_LINE_PATTERNS:
            if pattern.search(line):
                skip = True
                break
        if skip:
            continue
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        if line:
            lines.append(line)
    snippet = " ".join(lines).strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1].rstrip() + "…"


def promote_destination_label(target_path: str) -> str:
    """Short folder hint without full vault path."""
    rel = (target_path or "").replace("\\", "/").strip("/")
    if not rel:
        return "Vault (path TBD)"
    parts = rel.split("/")
    if len(parts) >= 2:
        return f"{parts[0]} / {parts[1]}"
    return parts[0]