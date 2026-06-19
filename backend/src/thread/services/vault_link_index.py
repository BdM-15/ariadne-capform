"""Vault wikilink index — resolve [[targets]] to real pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from thread.services.vault_write import PROTECTED_PREFIXES, _parse_frontmatter, _slug

_WIKILINK_RE = re.compile(
    r"\[\[([^\]|#]+)(#[^\]|]+)?(?:\|([^\]]+))?\]\]",
)

# Legacy / shorthand → canonical page stem (Obsidian resolves by stem).
CANONICAL_STEM_ALIASES: dict[str, str] = {
    "brain/": "entities",
    "brain": "entities",
    "lessons-learned": "lessons-learned-index",
    "lessons learned": "lessons-learned-index",
    "sam mcp": "competitive-intelligence-sources",
    "naics": "naics-code-and-size-standard-strategy",
    "561210": "naics-code-and-size-standard-strategy",
    "naics 561210": "naics-code-and-size-standard-strategy",
    "wikilinks": "capture-llm-wiki",
    "domain-intel": "domain-intel",
    "global-wiki": "global-wiki",
    "relationships": "relationships",
    "milestones-overview": "milestones-overview",
    "capabilities-catalog": "capabilities-catalog",
    "capture-llm-wiki": "capture-llm-wiki",
    "thread-wiki-schema": "thread-wiki-schema",
    "usaspending-plain-english": "usaspending-plain-english",
}


@dataclass(frozen=True)
class VaultStemOption:
    stem: str
    rel: str
    folder: str
    label: str


_PRIORITY_STEMS: tuple[str, ...] = (
    "capture-llm-wiki",
    "domain-intel",
    "global-wiki",
    "thread-wiki-schema",
    "relationships",
    "capabilities-catalog",
    "milestones-overview",
)


@dataclass
class VaultLinkIndex:
    stem_to_rel: dict[str, str] = field(default_factory=dict)
    alias_to_stem: dict[str, str] = field(default_factory=dict)

    def has_stem(self, stem: str) -> bool:
        return _normalize_key(stem) in self.stem_to_rel

    def resolve(self, raw_target: str) -> str | None:
        target = raw_target.strip().rstrip("/")
        if not target or target.startswith("http"):
            return None

        key = _normalize_key(target)
        if key in CANONICAL_STEM_ALIASES:
            target = CANONICAL_STEM_ALIASES[key]
            key = _normalize_key(target)

        if key in self.stem_to_rel:
            return Path(self.stem_to_rel[key]).stem

        if key in self.alias_to_stem:
            return self.alias_to_stem[key]

        slug = _slug(target)
        if slug in self.stem_to_rel:
            return Path(self.stem_to_rel[slug]).stem

        # Path-style: entities/agencies/foo → foo
        if "/" in target:
            leaf = Path(target).stem
            leaf_key = _normalize_key(leaf)
            if leaf_key in self.stem_to_rel:
                return Path(self.stem_to_rel[leaf_key]).stem

        # Fuzzy: name in frontmatter
        return self.alias_to_stem.get(key)


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _register(index: VaultLinkIndex, rel: str, stem: str, meta: dict[str, str]) -> None:
    index.stem_to_rel[_normalize_key(stem)] = rel
    index.stem_to_rel[_slug(stem)] = rel

    page_id = meta.get("id", "").strip()
    if page_id:
        id_slug = _slug(page_id.replace("global-", "").replace("entity-", ""))
        if id_slug and id_slug not in index.stem_to_rel:
            index.stem_to_rel[_normalize_key(id_slug)] = rel
        index.alias_to_stem[_normalize_key(page_id)] = id_slug or stem

    name = meta.get("name", "").strip()
    if name:
        index.alias_to_stem[_normalize_key(name)] = stem
        index.alias_to_stem[_slug(name)] = stem

    aliases_raw = meta.get("aliases", "")
    if aliases_raw:
        cleaned = aliases_raw.strip("[]")
        for part in re.split(r"[,;]", cleaned):
            token = part.strip().strip('"')
            if token:
                index.alias_to_stem[_normalize_key(token)] = stem


def build_link_index(vault: Path, *, include_protected: bool = True) -> VaultLinkIndex:
    index = VaultLinkIndex()
    for path in sorted(vault.rglob("*.md")):
        rel = str(path.relative_to(vault)).replace("\\", "/")
        if rel in ("index.md", "log.md"):
            continue
        if not include_protected and any(rel.startswith(p) for p in PROTECTED_PREFIXES):
            continue
        meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        stem = path.stem
        _register(index, rel, stem, meta)

    for alias, stem in CANONICAL_STEM_ALIASES.items():
        if index.has_stem(stem):
            index.alias_to_stem[_normalize_key(alias)] = stem
        elif _normalize_key(alias) in index.alias_to_stem:
            continue
        elif _normalize_key(stem) in index.stem_to_rel:
            index.alias_to_stem[_normalize_key(alias)] = Path(index.stem_to_rel[_normalize_key(stem)]).stem

    return index


def iter_wikilinks(text: str):
    for match in _WIKILINK_RE.finditer(text):
        yield match.group(0), match.group(1), match.group(2), match.group(3)


def build_vault_stem_options(vault: Path) -> tuple[VaultStemOption, ...]:
    """Trusted vault pages as wikilink stem picks for candidate editor."""
    index = build_link_index(vault)
    seen_rels: set[str] = set()
    options: list[VaultStemOption] = []
    for rel in sorted(set(index.stem_to_rel.values())):
        if rel in seen_rels:
            continue
        seen_rels.add(rel)
        stem = Path(rel).stem
        folder = Path(rel).parent.as_posix() or "root"
        options.append(
            VaultStemOption(
                stem=stem,
                rel=rel,
                folder=folder,
                label=f"{stem} — {folder}/",
            )
        )

    def _sort_key(option: VaultStemOption) -> tuple:
        if option.stem == "capture-llm-wiki":
            return (0, "")
        if option.stem in _PRIORITY_STEMS:
            return (1, option.stem)
        return (2, option.folder, option.stem)

    return tuple(sorted(options, key=_sort_key))