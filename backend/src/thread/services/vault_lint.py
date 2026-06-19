"""Vault lint + batch normalize — Karpathy health checks without hand-editing every page."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings
from thread.services.vault_link_index import build_link_index
from thread.services.vault_ofm import normalize_related_section, parse_list_property, render_frontmatter_ofm
from thread.services.vault_sandbox import is_sandbox_path, is_test_marked
from thread.services.vault_write import (
    INDEX_PAGES_MARKER,
    PROTECTED_PREFIXES,
    _parse_frontmatter,
    _render_frontmatter,
    _slug,
    _vault_root,
    append_log,
)

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
_REQUIRED_KEYS = ("name", "type", "id")

_SKIP_LINT_PREFIXES = (
    "foundation/",
    "data-elements/",
    "milestones/",
    "training/",
    "education/",
    ".obsidian/",
)

_LEGACY_ZONES = (
    "entities/agencies/",
    "entities/competitors/",
    "global/",
    "relationships/",
    "pursuits/",
)


@dataclass
class VaultLintIssue:
    code: str
    path: str
    message: str


@dataclass
class VaultLintReport:
    pages_scanned: int = 0
    issues: list[VaultLintIssue] = field(default_factory=list)
    fixable: int = 0

    def to_dict(self) -> dict:
        return {
            "pages_scanned": self.pages_scanned,
            "issue_count": len(self.issues),
            "fixable": self.fixable,
            "issues": [
                {"code": i.code, "path": i.path, "message": i.message}
                for i in self.issues[:200]
            ],
        }


@dataclass
class VaultNormalizeReport:
    dry_run: bool
    pages_scanned: int = 0
    frontmatter_fixed: int = 0
    related_added: int = 0
    index_rebuilt: bool = False
    paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "pages_scanned": self.pages_scanned,
            "frontmatter_fixed": self.frontmatter_fixed,
            "related_added": self.related_added,
            "index_rebuilt": self.index_rebuilt,
            "paths": self.paths[:100],
        }


def _rel(vault: Path, path: Path) -> str:
    return str(path.relative_to(vault)).replace("\\", "/")


def _iter_ofm_normalize_pages(vault: Path) -> list[Path]:
    """Wiki pages + data-elements for OFM Related/tags normalize."""
    pages: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        rel = _rel(vault, path)
        if rel in ("index.md", "log.md"):
            continue
        if rel.startswith((".obsidian/", "foundation/")):
            continue
        pages.append(path)
    return pages


def _iter_wiki_pages(vault: Path) -> list[Path]:
    pages: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        rel = _rel(vault, path)
        if rel in ("index.md", "log.md"):
            continue
        if any(rel.startswith(p) for p in _SKIP_LINT_PREFIXES):
            continue
        pages.append(path)
    return pages


def _stem_index(vault: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in vault.rglob("*.md"):
        rel = _rel(vault, path)
        if any(rel.startswith(p) for p in PROTECTED_PREFIXES):
            continue
        out[path.stem.lower()] = rel
        out[_slug(path.stem)] = rel
    return out


def _collect_inbound_links(vault: Path) -> dict[str, int]:
    inbound: dict[str, int] = {}
    sources: list[Path] = list(_iter_wiki_pages(vault))
    for extra in ("index.md", "foundation/capture-llm-wiki.md"):
        p = vault / extra
        if p.is_file():
            sources.append(p)
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _WIKILINK_RE.finditer(text):
            target = match.group(1).strip()
            for key in (target.lower(), _slug(target), Path(target).stem.lower()):
                inbound[key] = inbound.get(key, 0) + 1
    return inbound


def lint_vault(settings: Settings) -> VaultLintReport:
    vault = _vault_root(settings)
    report = VaultLintReport()
    if not vault.is_dir():
        report.issues.append(VaultLintIssue("vault_missing", "", "knowledge/thread not found"))
        return report

    link_index = build_link_index(vault)
    inbound = _collect_inbound_links(vault)

    for path in _iter_wiki_pages(vault):
        rel = _rel(vault, path)
        report.pages_scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)

        if not meta:
            report.issues.append(VaultLintIssue("missing_frontmatter", rel, "No YAML frontmatter"))
            report.fixable += 1
            continue

        for key in _REQUIRED_KEYS:
            if not meta.get(key):
                report.issues.append(VaultLintIssue("missing_field", rel, f"Frontmatter missing `{key}`"))
                report.fixable += 1

        trust = meta.get("trust", "")
        if rel.startswith("generated-projections/") and trust != "candidate":
            report.issues.append(VaultLintIssue("trust_zone", rel, "generated-projections should be trust: candidate"))
            report.fixable += 1
        if rel.startswith("entities/") and trust == "candidate":
            report.issues.append(
                VaultLintIssue("candidate_in_entity", rel, "Candidate note in entities/ — promote or move")
            )

        if meta.get("id", "").startswith("brain-"):
            report.issues.append(VaultLintIssue("legacy_id", rel, "Legacy brain-* id — normalize will upgrade"))
            report.fixable += 1

        if trust == "trusted" and (
            is_test_marked(meta=meta, rel_path=rel, citations=meta.get("citations", ""))
            or is_sandbox_path(rel)
        ):
            report.issues.append(
                VaultLintIssue(
                    "test_in_trusted_zone",
                    rel,
                    "Test/sandbox content in trusted zone — archive or set trust: candidate",
                )
            )

        if "## Related" not in text and rel.startswith(_LEGACY_ZONES):
            report.issues.append(VaultLintIssue("missing_related", rel, "No ## Related section"))
            report.fixable += 1

        stem = path.stem.lower()
        if inbound.get(stem, 0) == 0 and rel.startswith(
            ("entities/agencies/", "entities/competitors/", "global/domain_intel/capabilities/", "relationships/")
        ):
            report.issues.append(VaultLintIssue("orphan", rel, "No inbound wikilinks (true orphan)"))

        for match in _WIKILINK_RE.finditer(text):
            target = match.group(1).strip()
            if target.startswith("http"):
                continue
            if link_index.resolve(target) is None:
                report.issues.append(
                    VaultLintIssue("broken_link", rel, f"Wikilink target not found: [[{target}]]")
                )

    return report


def _infer_page_type(rel: str, meta: dict[str, str]) -> str:
    if meta.get("type"):
        return meta["type"]
    if "agencies" in rel:
        return "agency"
    if "competitors" in rel:
        return "competitor"
    if "pursuits/" in rel:
        return "opportunity"
    return "concept"


def _upgrade_frontmatter(rel: str, text: str) -> tuple[str, bool, bool]:
    meta, body = _parse_frontmatter(text)
    if not meta:
        return text, False, False

    changed = False
    stem = Path(rel).stem
    page_type = _infer_page_type(rel, meta)

    if not meta.get("trust"):
        if rel.startswith("generated-projections/"):
            meta["trust"] = "candidate"
        elif rel.startswith(_LEGACY_ZONES):
            meta["trust"] = "trusted"
        changed = True

    if meta.get("id", "").startswith("brain-"):
        meta["id"] = f"entity-{page_type}-{_slug(meta.get('name') or stem)}"
        changed = True

    if not meta.get("last_updated") and meta.get("added"):
        meta["last_updated"] = meta["added"][:10]
        changed = True
    elif not meta.get("last_updated"):
        meta["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        changed = True

    if not meta.get("name"):
        meta["name"] = stem.replace("-", " ").title()
        changed = True

    if not meta.get("id"):
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
        changed = True

    if not meta.get("type"):
        meta["type"] = page_type
        changed = True

    related_added = False
    if "## Related" not in text and rel.startswith(_LEGACY_ZONES):
        body = body.rstrip() + "\n\n## Related\n- [[capture-llm-wiki]]\n"
        related_added = True
        changed = True

    body, rel_fixed = normalize_related_section(body)
    if rel_fixed:
        related_added = True
        changed = True

    use_ofm_render = any(parse_list_property(meta[k]) is not None for k in ("tags", "aliases") if k in meta)
    if use_ofm_render:
        changed = True

    if not changed:
        return text, False, related_added

    fm = render_frontmatter_ofm(meta) if use_ofm_render else _render_frontmatter(meta)
    return fm + body, True, related_added


def rebuild_index_catalog(settings: Settings) -> bool:
    vault = _vault_root(settings)
    index_path = vault / "index.md"
    if not index_path.is_file():
        return False

    base = index_path.read_text(encoding="utf-8")
    if INDEX_PAGES_MARKER in base:
        base = base.split(INDEX_PAGES_MARKER, 1)[0].rstrip()

    lines = [INDEX_PAGES_MARKER.rstrip()]
    for path in _iter_wiki_pages(vault):
        rel = _rel(vault, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, _ = _parse_frontmatter(text)
        name = meta.get("name") or path.stem
        trust = meta.get("trust", "legacy")
        lines.append(f"- [[{path.stem}]] — `{rel}` — {name} — trust:{trust}")

    index_path.write_text(base + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return True


def normalize_vault(settings: Settings, *, dry_run: bool = True) -> VaultNormalizeReport:
    vault = _vault_root(settings)
    report = VaultNormalizeReport(dry_run=dry_run)

    for path in _iter_ofm_normalize_pages(vault):
        rel = _rel(vault, path)
        report.pages_scanned += 1
        original = path.read_text(encoding="utf-8", errors="replace")
        upgraded, fm_fixed, related_added = _upgrade_frontmatter(rel, original)
        if upgraded != original:
            report.paths.append(rel)
            if fm_fixed:
                report.frontmatter_fixed += 1
            if related_added:
                report.related_added += 1
            if not dry_run:
                path.write_text(upgraded, encoding="utf-8")

    if not dry_run:
        report.index_rebuilt = rebuild_index_catalog(settings)
        append_log(settings, "lint", "vault normalize", f"fixed={report.frontmatter_fixed}")

    return report