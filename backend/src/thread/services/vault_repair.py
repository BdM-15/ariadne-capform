"""Repair vault wikilinks and hub connectivity — fix targets, not delete."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings
from thread.services.vault_link_index import (
    CANONICAL_STEM_ALIASES,
    VaultLinkIndex,
    build_link_index,
    iter_wikilinks,
)
from thread.services.vault_lint import (
    INDEX_PAGES_MARKER,
    _infer_page_type,
    _iter_wiki_pages,
    _rel,
    _upgrade_frontmatter,
    lint_vault,
    rebuild_index_catalog,
)
from thread.services.vault_ofm import insert_related_links
from thread.services.vault_write import (
    _parse_frontmatter,
    _render_frontmatter,
    _slug,
    _vault_root,
    append_log,
)

_SKIP_REPAIR_PREFIXES = (".obsidian/",)

# Prose documenting syntax — do not rewrite wikilinks here.
_SKIP_REPAIR_FILES = frozenset(
    {
        "foundation/capture-llm-wiki.md",
        "foundation/reference/obsidian-desktop.md",
    }
)


@dataclass
class VaultRepairReport:
    dry_run: bool
    hubs_written: int = 0
    links_repaired: int = 0
    pages_touched: int = 0
    ids_assigned: int = 0
    aliases_added: int = 0
    repairs: list[str] = field(default_factory=list)
    semantic_links_added: int = 0
    semantic_pages_updated: int = 0
    lint_after: dict | None = None

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "hubs_written": self.hubs_written,
            "links_repaired": self.links_repaired,
            "pages_touched": self.pages_touched,
            "ids_assigned": self.ids_assigned,
            "aliases_added": self.aliases_added,
            "repairs": self.repairs[:150],
            "semantic_links_added": self.semantic_links_added,
            "semantic_pages_updated": self.semantic_pages_updated,
            "lint_after": self.lint_after,
        }


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_all_pages(vault: Path) -> list[Path]:
    pages: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        rel = _rel(vault, path)
        if rel in ("index.md", "log.md"):
            continue
        if any(rel.startswith(p) for p in _SKIP_REPAIR_PREFIXES):
            continue
        pages.append(path)
    return pages


def _capability_pages(vault: Path) -> list[Path]:
    root = vault / "global" / "domain_intel" / "capabilities"
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.md") if p.name.lower() != "readme.md")


def _entity_pages(vault: Path, sub: str) -> list[Path]:
    root = vault / "entities" / sub
    if not root.is_dir():
        return []
    return sorted(root.glob("*.md"))


def _lessons_pages(vault: Path) -> list[Path]:
    root = vault / "global" / "global_wiki" / "lessons_learned"
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.md") if "index" not in p.stem)


def _ensure_meta_id(rel: str, meta: dict[str, str], stem: str) -> bool:
    if meta.get("id"):
        return False
    page_type = _infer_page_type(rel, meta)
    if rel.startswith("entities/agencies/"):
        meta["id"] = f"entity-agency-{_slug(stem)}"
    elif rel.startswith("entities/competitors/"):
        meta["id"] = f"entity-competitor-{_slug(stem)}"
    elif "/capabilities/" in rel:
        meta["id"] = f"capability-{_slug(stem)}"
    elif "/lessons_learned/" in rel:
        meta["id"] = f"lesson-{_slug(stem)}"
    elif "/capture/concepts/" in rel:
        meta["id"] = f"concept-{_slug(stem)}"
    elif rel.startswith("global/"):
        meta["id"] = f"global-{_slug(stem)}"
    else:
        meta["id"] = f"{page_type}-{_slug(stem)}"
    return True


def _write_hub(vault: Path, rel: str, content: str, *, dry_run: bool) -> bool:
    path = vault / Path(rel)
    existed = path.is_file()
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True if not dry_run or not existed else True


def ensure_vault_hubs(settings: Settings, *, dry_run: bool = True) -> int:
    vault = _vault_root(settings)
    written = 0

    agencies = _entity_pages(vault, "agencies")
    competitors = _entity_pages(vault, "competitors")
    lines = [
        "---",
        'name: "Entities"',
        'type: "meta"',
        'id: "entities-hub"',
        'trust: "trusted"',
        f'added: "{_now_iso()}"',
        f'last_updated: "{_today()}"',
        'aliases: "entities, brain, brain/"',
        'tags: "hub, karpathy-wiki"',
        "---",
        "",
        "# Entities",
        "",
        "Agencies and competitors (`entities/` — formerly capture-insights `brain/`).",
        "",
        "## Agencies",
    ]
    for p in agencies:
        lines.append(f"- [[{p.stem}]]")
    lines.extend(["", "## Competitors"])
    for p in competitors:
        lines.append(f"- [[{p.stem}]]")
    lines.extend(["", "## Related", "- [[capture-llm-wiki]]", "- [[follow-the-money]]", ""])
    if _write_hub(vault, "entities/entities.md", "\n".join(lines), dry_run=dry_run):
        written += 1

    lessons = _lessons_pages(vault)
    if lessons:
        lines = [
            "---",
            'name: "Lessons Learned Index"',
            'type: "meta"',
            'id: "lessons-learned-index"',
            'trust: "trusted"',
            f'added: "{_now_iso()}"',
            f'last_updated: "{_today()}"',
            'aliases: "lessons-learned, lessons learned"',
            'tags: "hub, shipley, lessons"',
            "---",
            "",
            "# Lessons Learned",
            "",
            "Evergreen proposal and capture lessons (`global/global_wiki/lessons_learned/`).",
            "",
            "## Catalog",
        ]
        for p in lessons:
            lines.append(f"- [[{p.stem}]]")
        lines.extend(["", "## Related", "- [[capture-llm-wiki]]", "- [[milestone_1]]", ""])
        if _write_hub(
            vault,
            "global/global_wiki/lessons_learned/lessons-learned-index.md",
            "\n".join(lines),
            dry_run=dry_run,
        ):
            written += 1

    caps = _capability_pages(vault)
    if caps:
        lines = [
            "---",
            'name: "Capabilities Catalog"',
            'type: "meta"',
            'id: "capabilities-catalog"',
            'trust: "trusted"',
            f'added: "{_now_iso()}"',
            f'last_updated: "{_today()}"',
            'aliases: "capabilities, domain-intel-capabilities"',
            'tags: "hub, domain-intel, bid-fit"',
            "---",
            "",
            "# Domain Intel — Capabilities",
            "",
            "Bid/no-bid fit capability statements. Append synthesis; never erase trusted history.",
            "",
            "## Catalog",
        ]
        for p in caps:
            lines.append(f"- [[{p.stem}]]")
        lines.extend(
            [
                "",
                "## Related",
                "- [[capture-llm-wiki]]",
                "- [[thread-role]]",
                "",
            ]
        )
        if _write_hub(
            vault,
            "global/domain_intel/capabilities/capabilities-catalog.md",
            "\n".join(lines),
            dry_run=dry_run,
        ):
            written += 1

    # Domain intel root hub refresh
    di_readme = vault / "global" / "domain_intel" / "README.md"
    if di_readme.is_file() and caps:
        text = di_readme.read_text(encoding="utf-8")
        if "[[capabilities-catalog]]" not in text and "[[README]]" not in text:
            addition = (
                "\n## Vault hubs\n\n"
                "- [[capabilities-catalog]] — bid-fit capabilities\n"
                "- [[lessons-learned-index]] — proposal lessons\n"
                "- [[entities]] — agencies & competitors\n"
            )
            if not dry_run:
                di_readme.write_text(text.rstrip() + addition, encoding="utf-8")
            written += 1

    return written


def _add_aliases_to_page(path: Path, aliases: list[str], *, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    if not meta:
        return False
    existing = meta.get("aliases", "")
    tokens = {a.strip() for a in re.split(r"[,;]", existing.strip("[]")) if a.strip()}
    new_tokens = [a for a in aliases if _normalize_alias(a) not in {_normalize_alias(t) for t in tokens}]
    if not new_tokens:
        return False
    merged = ", ".join(sorted(tokens | set(new_tokens)))
    meta["aliases"] = merged
    if not dry_run:
        path.write_text(_render_frontmatter(meta) + body, encoding="utf-8")
    return True


def _normalize_alias(value: str) -> str:
    return value.strip().lower()


def _repair_wikilink_token(
    raw: str,
    index: VaultLinkIndex,
) -> tuple[str | None, str]:
    """Return (canonical_stem, reason)."""
    resolved = index.resolve(raw)
    if resolved:
        return resolved, "resolved"
    return None, "unresolved"


def _replace_wikilinks(text: str, index: VaultLinkIndex, report: VaultRepairReport) -> tuple[str, int]:
    changes = 0

    def replacer(match: re.Match) -> str:
        nonlocal changes
        full = match.group(0)
        target = match.group(1)
        heading = match.group(2) or ""
        display = match.group(3)

        stem, reason = _repair_wikilink_token(target, index)
        if stem is None:
            return full

        canonical = stem
        if _normalize_alias(target.rstrip("/")) == _normalize_alias(canonical):
            return full

        changes += 1
        report.repairs.append(f"[[{target}]] → [[{canonical}]] ({reason})")
        if display:
            return f"[[{canonical}{heading}|{display}]]"
        return f"[[{canonical}{heading}]]"

    from thread.services.vault_link_index import _WIKILINK_RE

    new_text = _WIKILINK_RE.sub(replacer, text)
    return new_text, changes


def _assign_missing_ids(vault: Path, *, dry_run: bool) -> int:
    count = 0
    for path in _iter_all_pages(vault):
        rel = _rel(vault, path)
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        if not meta:
            continue
        if _ensure_meta_id(rel, meta, path.stem):
            count += 1
            if not dry_run:
                path.write_text(_render_frontmatter(meta) + body, encoding="utf-8")
    return count


def repair_vault_links(settings: Settings, *, dry_run: bool = True) -> VaultRepairReport:
    vault = _vault_root(settings)
    report = VaultRepairReport(dry_run=dry_run)

    report.hubs_written = ensure_vault_hubs(settings, dry_run=dry_run)

    # Alias patches on canonical targets
    alias_patches: list[tuple[str, list[str]]] = [
        (
            "global/global_wiki/capture/competitive-intelligence-sources.md",
            ["SAM MCP", "sam-mcp"],
        ),
        (
            "global/global_wiki/regulations/naics-code-and-size-standard-strategy.md",
            ["NAICS", "561210", "NAICS 561210"],
        ),
        ("foundation/capture-llm-wiki.md", ["wikilinks"]),
    ]
    for rel, aliases in alias_patches:
        path = vault / Path(rel)
        if path.is_file() and _add_aliases_to_page(path, aliases, dry_run=dry_run):
            report.aliases_added += 1

    report.ids_assigned = _assign_missing_ids(vault, dry_run=dry_run)

    # Rebuild index after hubs + ids
    index = build_link_index(vault)

    for path in _iter_all_pages(vault):
        rel = _rel(vault, path)
        if rel in _SKIP_REPAIR_FILES:
            continue

        original = path.read_text(encoding="utf-8")
        upgraded, fm_fixed, _ = _upgrade_frontmatter(rel, original)
        new_text, n = _replace_wikilinks(upgraded, index, report)
        if n or (fm_fixed and new_text != original):
            report.pages_touched += 1
            report.links_repaired += n
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")

    if not dry_run:
        rebuild_index_catalog(settings)
        append_log(settings, "lint", "vault repair", f"links={report.links_repaired}")

    # Refresh index for lint pass
    index = build_link_index(vault)
    _ = index  # used by lint if we refactor; run lint separately

    if not dry_run:
        report.lint_after = lint_vault(settings).to_dict()

    return report


_HUB_RENAMES: tuple[tuple[str, str, str, str], ...] = (
    (
        "relationships/README.md",
        "relationships/relationships.md",
        "relationships-hub",
        "Relationships",
    ),
    (
        "global/domain_intel/README.md",
        "global/domain_intel/domain-intel.md",
        "domain-intel-hub",
        "Domain Intel",
    ),
    (
        "global/domain_intel/milestones/README.md",
        "global/domain_intel/milestones/milestones-overview.md",
        "milestones-overview",
        "Capture Milestones (MS1–MS4)",
    ),
    (
        "global/global_wiki/README.md",
        "global/global_wiki/global-wiki.md",
        "global-wiki-hub",
        "Global Wiki",
    ),
)


def _relocate_hub_page(
    vault: Path,
    src_rel: str,
    dest_rel: str,
    page_id: str,
    name: str,
    *,
    dry_run: bool,
) -> bool:
    src = vault / Path(src_rel)
    if not src.is_file():
        return False
    dest = vault / Path(dest_rel)
    text = src.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    if not meta:
        meta = {}
    meta["name"] = name
    meta["type"] = meta.get("type") or "meta"
    meta["id"] = page_id
    meta["trust"] = meta.get("trust") or "trusted"
    meta["last_updated"] = _today()
    if not meta.get("added"):
        meta["added"] = _now_iso()
    content = _render_frontmatter(meta) + body.lstrip()
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        src.unlink()
    return True


def _remove_junk_pages(vault: Path, *, dry_run: bool) -> int:
    removed = 0
    for rel in (
        "global/global_wiki/capture/vault_lint_report.md",
    ):
        path = vault / Path(rel)
        if path.is_file():
            if not dry_run:
                path.unlink()
            removed += 1
    return removed


def _patch_index_catalog_hubs(vault: Path, *, dry_run: bool) -> bool:
    index_path = vault / "index.md"
    if not index_path.is_file():
        return False
    text = index_path.read_text(encoding="utf-8")
    hub_block = (
        "\n\n## Vault hubs\n\n"
        "- [[entities]] — agencies & competitors\n"
        "- [[global-wiki]] — evergreen doctrine (Shipley, FAR, capture)\n"
        "- [[domain-intel]] — bid-fit overlays & MS gates\n"
        "- [[capabilities-catalog]] — capability statements\n"
        "- [[capture-insights-index]] — dashboard concept MOC\n"
        "- [[lessons-learned-index]] — proposal lessons\n"
        "- [[relationships]] — money-flow graph notes\n"
        "- [[milestones-overview]] — MS1–MS4 gate model\n"
    )
    if "## Vault hubs" in text:
        return False
    marker = "## Pages"
    if marker in text:
        text = text.replace(marker, hub_block.strip() + "\n\n" + marker, 1)
    else:
        text = text.rstrip() + hub_block
    if not dry_run:
        index_path.write_text(text, encoding="utf-8")
    return True


def _wire_hub_crosslinks(vault: Path, *, dry_run: bool) -> int:
    from thread.services.vault_link_index import build_link_index

    index = build_link_index(vault)
    patches: list[tuple[str, str]] = [
        (
            "entities/entities.md",
            "\n- [[relationships]]\n- [[domain-intel]]\n",
        ),
        (
            "global/domain_intel/capabilities/capabilities-catalog.md",
            "\n- [[domain-intel]]\n- [[milestones-overview]]\n",
        ),
        (
            "global/domain_intel/domain-intel.md",
            "\n- [[capabilities-catalog]]\n- [[milestones-overview]]\n- [[global-wiki]]\n",
        ),
    ]
    touched = 0
    for rel, addition in patches:
        path = vault / Path(rel)
        if not path.is_file():
            continue
        key_link = addition.strip().split("[[", 1)[-1].split("]]", 1)[0] if "[[" in addition else ""
        if key_link and index.resolve(key_link) is None:
            continue
        text = path.read_text(encoding="utf-8")
        if addition.strip() in text:
            continue
        if key_link and f"[[{key_link}]]" in text:
            continue
        stems = re.findall(r"\[\[([^\]|#]+)\]\]", addition)
        new_text, _ = insert_related_links(text, stems) if stems else (text, 0)
        if not stems and "## Related" not in text:
            new_text = text.rstrip() + "\n\n## Related" + addition
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")
        touched += 1
    return touched


def finalize_vault_connectivity(settings: Settings, *, dry_run: bool = True) -> int:
    vault = _vault_root(settings)
    changed = 0
    changed += _remove_junk_pages(vault, dry_run=dry_run)
    for src, dest, page_id, name in _HUB_RENAMES:
        if _relocate_hub_page(vault, src, dest, page_id, name, dry_run=dry_run):
            changed += 1
    if _patch_index_catalog_hubs(vault, dry_run=dry_run):
        changed += 1
    changed += _wire_hub_crosslinks(vault, dry_run=dry_run)
    return changed


def repair_vault_full(settings: Settings, *, dry_run: bool = True) -> VaultRepairReport:
    """Hubs → ids → wikilink repair → normalize → semantic cross-link → lint."""
    from thread.services.vault_lint import normalize_vault
    from thread.services.vault_semantic_graph import apply_semantic_crosslinks

    report = repair_vault_links(settings, dry_run=dry_run)
    if not dry_run:
        finalize_vault_connectivity(settings, dry_run=False)
        normalize_vault(settings, dry_run=False)
        rebuild_index_catalog(settings)
        semantic = apply_semantic_crosslinks(settings, dry_run=False)
        report.semantic_links_added = semantic.links_added
        report.semantic_pages_updated = semantic.pages_updated
        rebuild_index_catalog(settings)
        report.lint_after = lint_vault(settings).to_dict()
    return report