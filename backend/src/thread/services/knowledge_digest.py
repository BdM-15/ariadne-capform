"""Knowledge digest — domain_intel highlights for Pulse (12j)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thread.config import Settings

DIGEST_LIMIT = 6

DOMAIN_INTEL_ROOT = Path("global/domain_intel")
CAPABILITIES_DIR = DOMAIN_INTEL_ROOT / "capabilities"
UEI_DIR = DOMAIN_INTEL_ROOT / "uei"
THREAD_ROLE = DOMAIN_INTEL_ROOT / "thread-role.md"

KIND_LABELS = {
    "capability": "Capability",
    "uei": "UEI / PP",
    "meta": "Domain intel",
}


@dataclass(frozen=True)
class KnowledgeDigestItem:
    rel_path: str
    title: str
    excerpt: str
    kind: str
    kind_label: str


@dataclass(frozen=True)
class KnowledgeDigestWidget:
    vault_ready: bool
    items: tuple[KnowledgeDigestItem, ...]
    capability_count: int
    uei_count: int
    has_domain_intel: bool


def _vault_root(settings: Settings) -> Path:
    return settings.resolve(settings.knowledge_vault_path)


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _excerpt_from_markdown(text: str, *, limit: int = 180) -> str:
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            body = text[end + 4 :]
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("[[") or line.startswith("---"):
            continue
        if line.startswith("- ") and len(lines) > 0:
            break
        lines.append(line)
        if len(" ".join(lines)) >= limit:
            break
    clean = " ".join(lines)
    clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", clean)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _title_from_file(path: Path, text: str) -> str:
    meta = _parse_frontmatter(text)
    if meta.get("name"):
        return meta["name"]
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def _kind_for_path(rel: Path) -> str:
    parts = rel.parts
    if "capabilities" in parts:
        return "capability"
    if "uei" in parts:
        return "uei"
    return "meta"


def _collect_md_files(root: Path, subdir: Path) -> list[Path]:
    target = root / subdir
    if not target.is_dir():
        return []
    return sorted(
        (p for p in target.rglob("*.md") if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _item_from_path(vault: Path, path: Path) -> KnowledgeDigestItem | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rel = path.relative_to(vault).as_posix()
    kind = _kind_for_path(Path(rel))
    title = _title_from_file(path, text)
    excerpt = _excerpt_from_markdown(text)
    if not excerpt and kind == "meta":
        excerpt = "Bid/no-bid fit layer — capabilities and UEI awareness for qualification."
    return KnowledgeDigestItem(
        rel_path=rel,
        title=title,
        excerpt=excerpt or "(no preview)",
        kind=kind,
        kind_label=KIND_LABELS.get(kind, "Domain intel"),
    )


def build_knowledge_digest_widget(settings: Settings) -> KnowledgeDigestWidget:
    vault = _vault_root(settings)
    vault_ready = vault.is_dir()

    cap_files = _collect_md_files(vault, CAPABILITIES_DIR) if vault_ready else []
    uei_files = _collect_md_files(vault, UEI_DIR) if vault_ready else []

    candidates: list[Path] = []
    role_path = vault / THREAD_ROLE
    if role_path.is_file():
        candidates.append(role_path)
    candidates.extend(cap_files[:4])
    candidates.extend(uei_files[:3])

    seen: set[str] = set()
    items: list[KnowledgeDigestItem] = []
    for path in candidates:
        rel = path.relative_to(vault).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        item = _item_from_path(vault, path)
        if item:
            items.append(item)
        if len(items) >= DIGEST_LIMIT:
            break

    return KnowledgeDigestWidget(
        vault_ready=vault_ready,
        items=tuple(items),
        capability_count=len(cap_files),
        uei_count=len(uei_files),
        has_domain_intel=bool(items),
    )