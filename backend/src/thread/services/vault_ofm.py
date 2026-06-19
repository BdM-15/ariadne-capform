"""Obsidian Flavored Markdown helpers — Kepano + capture-llm-wiki conventions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from thread.config import Settings
from thread.services.vault_write import _parse_frontmatter, _vault_root, append_log

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_WIKILINK_FULL_RE = re.compile(r"\[\[[^\]|#]+(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
_LINK_BULLET_RE = re.compile(r"^-\s*\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]\s*$")


def existing_wikilink_stems(text: str) -> frozenset[str]:
    return frozenset(m.group(1).strip().lower() for m in _WIKILINK_RE.finditer(text))


def insert_related_links(text: str, new_stems: list[str]) -> tuple[str, int]:
    """Append list-style wikilinks inside ## Related, before ## Added/Updated or next ##."""
    if not new_stems:
        return text, 0

    existing = existing_wikilink_stems(text)
    to_add = [s for s in new_stems if s.lower() not in existing]
    if not to_add:
        return text, 0

    block = "\n".join(f"- [[{stem}]]" for stem in to_add)
    marker = "## Related"
    if marker not in text:
        return text.rstrip() + f"\n\n{marker}\n{block}\n", len(to_add)

    before, after = text.split(marker, 1)
    section_break = re.search(r"\n## ", after)
    if section_break:
        related_body, rest = after[: section_break.start()], after[section_break.start() :]
    else:
        related_body, rest = after, ""

    new_related = related_body.rstrip() + "\n" + block + "\n"
    return before + marker + new_related + rest, len(to_add)


def _inline_only_wikilinks(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("- "):
        return None
    stems = _WIKILINK_RE.findall(stripped)
    if not stems:
        return None
    remainder = _WIKILINK_FULL_RE.sub("", stripped).strip()
    return stems if not remainder else None


def normalize_related_section(text: str) -> tuple[str, int]:
    """OFM normalize: Related uses list bullets; link-only bullets at EOF → Related."""
    changed = 0
    if "## Related" in text:
        before, after = text.split("## Related", 1)
        section_break = re.search(r"\n## ", after)
        if section_break:
            related_body, rest = after[: section_break.start()], after[section_break.start() :]
        else:
            related_body, rest = after, ""

        new_lines: list[str] = []
        for line in related_body.splitlines():
            stems = _inline_only_wikilinks(line)
            if stems:
                for stem in stems:
                    new_lines.append(f"- [[{stem}]]")
                changed += len(stems)
            else:
                new_lines.append(line)
        related_body = "\n" + "\n".join(new_lines) + ("\n" if new_lines else "")
        text = before + "## Related" + related_body + rest

    lines = text.splitlines()
    trailing_idxs: list[int] = []
    i = len(lines) - 1
    while i >= 0:
        if not lines[i].strip():
            i -= 1
            continue
        if _LINK_BULLET_RE.match(lines[i]):
            trailing_idxs.insert(0, i)
            i -= 1
            continue
        break

    if trailing_idxs:
        related_line = next((i for i, ln in enumerate(lines) if ln.strip() == "## Related"), None)
        after_related = False
        if related_line is not None:
            next_section = next(
                (i for i in range(related_line + 1, len(lines)) if lines[i].startswith("## ")),
                len(lines),
            )
            after_related = trailing_idxs[0] >= next_section

        if after_related or "## Added/Updated" in "\n".join(lines[: trailing_idxs[0]]):
            stems: list[str] = []
            for idx in trailing_idxs:
                m = _LINK_BULLET_RE.match(lines[idx])
                if m:
                    stems.append(m.group(1).strip())
            base = "\n".join(lines[: trailing_idxs[0]]).rstrip() + "\n"
            text, n = insert_related_links(base, stems)
            changed += n

    return text, changed


def parse_list_property(raw: str) -> list[str] | None:
    value = raw.strip().strip('"').strip("'")
    if not value.startswith("["):
        return None
    try:
        parsed = json.loads(value.replace("'", '"'))
    except json.JSONDecodeError:
        inner = value.strip("[]")
        if not inner:
            return []
        return [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return None


def render_frontmatter_ofm(meta: dict[str, str], *, list_keys: tuple[str, ...] = ("tags", "aliases")) -> str:
    """Render YAML frontmatter with Kepano-style list properties."""
    list_values: dict[str, list[str]] = {}
    scalar_meta = dict(meta)
    for key in list_keys:
        if key not in scalar_meta:
            continue
        parsed = parse_list_property(scalar_meta[key])
        if parsed is not None:
            list_values[key] = parsed
            del scalar_meta[key]

    lines = ["---"]
    for key in sorted(scalar_meta.keys()):
        value = scalar_meta[key]
        if " " in value or ":" in value:
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    for key in list_keys:
        if key not in list_values:
            continue
        lines.append(f"{key}:")
        for item in list_values[key]:
            lines.append(f"  - {item}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


@dataclass
class PacketFieldCleanReport:
    dry_run: bool
    pages_scanned: int = 0
    pages_updated: int = 0
    links_removed: int = 0
    removals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "pages_scanned": self.pages_scanned,
            "pages_updated": self.pages_updated,
            "links_removed": self.links_removed,
            "removals": self.removals[:100],
        }


def _packet_field_stems(vault: Path) -> frozenset[str]:
    root = vault / "data-elements"
    if not root.is_dir():
        return frozenset()
    return frozenset(p.stem.lower() for p in root.glob("*.md"))


def _split_related_body(body: str) -> tuple[str, str, str] | None:
    if "## Related" not in body:
        return None
    before, after = body.split("## Related", 1)
    section_break = re.search(r"\n## ", after)
    if section_break:
        related_body, rest = after[: section_break.start()], after[section_break.start() :]
    else:
        related_body, rest = after, ""
    return before, related_body, rest


def clean_packet_field_related_links(
    text: str,
    page_stem: str,
    packet_field_stems: frozenset[str],
) -> tuple[str, int, list[str]]:
    """Drop Related links that point at other briefing-packet field pages."""
    split = _split_related_body(text)
    if split is None:
        return text, 0, []

    before, related_body, rest = split
    own = page_stem.lower()
    removed: list[str] = []
    kept: list[str] = []

    for line in related_body.splitlines():
        m = _LINK_BULLET_RE.match(line)
        if m:
            target = m.group(1).strip()
            key = target.lower()
            if key in packet_field_stems and key != own:
                removed.append(target)
                continue
        kept.append(line)

    if not removed:
        return text, 0, []

    new_related = "\n".join(kept)
    if new_related and not new_related.endswith("\n"):
        new_related += "\n"
    new_body = before + "## Related" + new_related + rest
    return new_body, len(removed), removed


def clean_packet_field_links(settings: Settings, *, dry_run: bool = True) -> PacketFieldCleanReport:
    vault = _vault_root(settings)
    report = PacketFieldCleanReport(dry_run=dry_run)
    field_stems = _packet_field_stems(vault)
    root = vault / "data-elements"
    if not root.is_dir():
        return report

    for path in sorted(root.glob("*.md")):
        report.pages_scanned += 1
        original = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(original)
        new_body, n, removed = clean_packet_field_related_links(body, path.stem, field_stems)
        if n == 0:
            continue
        report.pages_updated += 1
        report.links_removed += n
        for stem in removed:
            report.removals.append(f"{path.stem} ✕ {stem}")
        if not dry_run:
            path.write_text(_render_page(meta, new_body), encoding="utf-8")

    if not dry_run and report.pages_updated:
        append_log(
            settings,
            "lint",
            "packet-field link clean",
            f"removed={report.links_removed} pages={report.pages_updated}",
        )

    return report


def _render_page(meta: dict[str, str], body: str) -> str:
    from thread.services.vault_lint import _render_frontmatter

    use_ofm = any(parse_list_property(meta[k]) is not None for k in ("tags", "aliases") if k in meta)
    fm = render_frontmatter_ofm(meta) if use_ofm else _render_frontmatter(meta)
    return fm + body.lstrip("\n")