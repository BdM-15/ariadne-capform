"""OFM + vault_maintainer audit — run after semantic passes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thread.config import Settings
from thread.services.vault_lint import lint_vault

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_HEADING_RE = re.compile(r"^## +(.+)$", re.M)


def _rel(vault: Path, path: Path) -> str:
    return str(path.relative_to(vault)).replace("\\", "/")


def audit_vault(vault: Path) -> dict:
    de_stems = (
        {p.stem.lower() for p in (vault / "data-elements").glob("*.md")}
        if (vault / "data-elements").is_dir()
        else set()
    )

    report: dict[str, list[str]] = {
        "related_stray_after_added": [],
        "inline_related_no_bullet": [],
        "tags_string_not_yaml": [],
        "missing_trust": [],
        "de_mesh_in_related": [],
        "related_missing": [],
        "semantic_eof_append": [],
        "aliases_string_not_yaml": [],
    }

    for path in sorted(vault.rglob("*.md")):
        rel = _rel(vault, path)
        if rel in ("index.md", "log.md") or rel.startswith((".obsidian/", "foundation/")):
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        meta_m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if meta_m:
            meta = meta_m.group(1)
            if re.search(r'^tags:\s*"\[', meta, re.M) or (
                re.search(r"^tags:\s*", meta, re.M)
                and not re.search(r"^tags:\s*\n\s+-", meta, re.M)
                and "tags:" in meta
                and "[" in meta.split("tags:", 1)[1].split("\n", 1)[0]
            ):
                report["tags_string_not_yaml"].append(rel)
            if re.search(r'^aliases:\s*"\[', meta, re.M) and "aliases:" in meta:
                # quoted bracket strings are legacy; YAML list preferred per Kepano PROPERTIES
                if not re.search(r"^aliases:\s*\n\s+-", meta, re.M):
                    report["aliases_string_not_yaml"].append(rel)
            if "trust:" not in meta and rel.startswith(
                ("entities/", "global/", "relationships/", "pursuits/")
            ):
                report["missing_trust"].append(rel)

        if "## Related" not in text and rel.startswith(("entities/", "global/", "relationships/")):
            report["related_missing"].append(rel)

        if "## Related" in text:
            after_related = text.split("## Related", 1)[1]
            related_block = re.split(r"\n## ", after_related, 1)[0]

            has_list_links = bool(re.search(r"^-\s*\[\[", related_block, re.M))
            has_inline = bool(re.search(r"(?:^|\s)\[\[[^\]]+\]\]", related_block, re.M))
            if has_inline and not has_list_links:
                report["inline_related_no_bullet"].append(rel)

            if "## Added/Updated" in text:
                added_idx = text.find("## Added/Updated")
                related_idx = text.find("## Related")
                if related_idx < added_idx:
                    tail = text[added_idx:]
                    if re.search(r"^-\s*\[\[", tail, re.M):
                        report["related_stray_after_added"].append(rel)

            # Semantic pass appends at EOF when ## Related exists — links after last ## section
            headings = list(_HEADING_RE.finditer(text))
            if headings:
                last_h = headings[-1]
                tail = text[last_h.end() :]
                last_title = last_h.group(1).strip()
                if last_title in ("Related", "Vault hubs"):
                    pass
                elif re.search(r"^-\s*\[\[[^\]]+\]\]", tail, re.M):
                    # Hub catalog lines with em-dash descriptions are intentional
                    if last_title == "Vault hubs" or re.search(
                        r"^-\s*\[\[[^\]]+\]\]\s+—", tail, re.M
                    ):
                        pass
                    else:
                        report["semantic_eof_append"].append(rel)

            if rel.startswith("data-elements/"):
                for m in _WIKILINK_RE.finditer(related_block):
                    target = m.group(1).strip().lower()
                    if target in de_stems and target != path.stem.lower():
                        report["de_mesh_in_related"].append(f"{rel} → {target}")
                        break

    return report


def main() -> None:
    settings = Settings()
    vault = settings.resolve(settings.knowledge_vault_path)
    lint = lint_vault(settings).to_dict()
    report = audit_vault(vault)

    print("=== PLATFORM LINT ===")
    print(f"pages_scanned: {lint['pages_scanned']}")
    print(f"issue_count: {lint['issue_count']}")
    by_code: dict[str, int] = {}
    for issue in lint["issues"]:
        by_code[issue["code"]] = by_code.get(issue["code"], 0) + 1
    for code, n in sorted(by_code.items()):
        print(f"  {code}: {n}")

    print("\n=== OFM / KEPANO / SCHEMA AUDIT ===")
    for key, items in report.items():
        print(f"{key}: {len(items)}")
        for item in items[:6]:
            print(f"  - {item}")
        if len(items) > 6:
            print(f"  ... +{len(items) - 6} more")


if __name__ == "__main__":
    main()