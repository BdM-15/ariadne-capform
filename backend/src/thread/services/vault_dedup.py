"""Deterministic vault dedup hints — link index + name/stem overlap before promote."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thread.config import Settings
from thread.services.vault_link_index import _normalize_key, build_link_index
from thread.services.vault_write import (
    PROTECTED_PREFIXES,
    VaultWriteError,
    _assert_write_zone,
    _infer_promote_target,
    _parse_frontmatter,
    _slug,
    _vault_root,
)

_GENERATED_PREFIX = "generated-projections/"
_MAX_HINTS = 5
_MIN_TOKEN_OVERLAP = 2


@dataclass(frozen=True)
class DedupHint:
    rel_path: str
    title: str
    page_type: str
    reason: str
    score: int


@dataclass(frozen=True)
class MergeTargetOption:
    rel_path: str
    label: str
    is_default: bool
    from_dedup: bool


def validate_promote_target(rel_path: str) -> str:
    """Normalize and guard a human-selected merge target."""
    normalized = rel_path.strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise VaultWriteError("Merge target is required")
    if not normalized.endswith(".md"):
        normalized = f"{normalized}.md"
    if normalized.startswith(_GENERATED_PREFIX):
        raise VaultWriteError("Cannot promote into generated-projections")
    _assert_write_zone(normalized)
    return normalized


def _is_trusted_rel(rel: str) -> bool:
    if rel in ("index.md", "log.md"):
        return False
    if rel.startswith(_GENERATED_PREFIX):
        return False
    return not any(rel.startswith(p) for p in PROTECTED_PREFIXES)


def _page_meta(vault: Path, rel: str) -> tuple[dict[str, str], str]:
    path = vault / rel
    if not path.is_file():
        return {}, ""
    return _parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))


def _add_hint(
    hints: dict[str, DedupHint],
    *,
    rel: str,
    title: str,
    page_type: str,
    reason: str,
    score: int,
) -> None:
    if not _is_trusted_rel(rel):
        return
    existing = hints.get(rel)
    if existing is None or score > existing.score:
        hints[rel] = DedupHint(
            rel_path=rel,
            title=title or Path(rel).stem,
            page_type=page_type or "synthesis",
            reason=reason,
            score=score,
        )


def _name_tokens(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", value.lower()) if len(t) >= 3}


def find_dedup_hints(
    settings: Settings,
    *,
    candidate_rel: str,
    meta: dict[str, str],
    body: str,
    default_target: str,
) -> tuple[DedupHint, ...]:
    vault = _vault_root(settings)
    if not vault.is_dir():
        return ()

    index = build_link_index(vault)
    hints: dict[str, DedupHint] = {}

    name = (meta.get("name") or Path(candidate_rel).stem).strip()
    page_type = meta.get("type") or "synthesis"
    name_key = _normalize_key(name)
    slug = _slug(name)

    normalized_default = default_target.replace("\\", "/")
    if (vault / normalized_default).is_file():
        dmeta, _ = _page_meta(vault, normalized_default)
        _add_hint(
            hints,
            rel=normalized_default,
            title=dmeta.get("name") or Path(normalized_default).stem,
            page_type=dmeta.get("type") or page_type,
            reason="default merge path already exists",
            score=100,
        )

    resolved_stem = index.resolve(name)
    if resolved_stem:
        rel = index.stem_to_rel.get(_normalize_key(resolved_stem)) or index.stem_to_rel.get(_slug(resolved_stem))
        if rel:
            dmeta, _ = _page_meta(vault, rel)
            _add_hint(
                hints,
                rel=rel,
                title=dmeta.get("name") or resolved_stem,
                page_type=dmeta.get("type") or page_type,
                reason="title matches existing wiki page",
                score=90,
            )

    if name_key in index.alias_to_stem:
        stem = index.alias_to_stem[name_key]
        rel = index.stem_to_rel.get(_normalize_key(stem)) or index.stem_to_rel.get(_slug(stem))
        if rel:
            dmeta, _ = _page_meta(vault, rel)
            _add_hint(
                hints,
                rel=rel,
                title=dmeta.get("name") or stem,
                page_type=dmeta.get("type") or page_type,
                reason="name alias matches vault index",
                score=85,
            )

    for rel in index.stem_to_rel.values():
        if not _is_trusted_rel(rel):
            continue
        stem = Path(rel).stem
        if _slug(stem) == slug or _normalize_key(stem) == name_key:
            dmeta, _ = _page_meta(vault, rel)
            _add_hint(
                hints,
                rel=rel,
                title=dmeta.get("name") or stem,
                page_type=dmeta.get("type") or page_type,
                reason="filename stem matches candidate",
                score=80,
            )

    candidate_tokens = _name_tokens(name)
    if len(candidate_tokens) >= _MIN_TOKEN_OVERLAP:
        for path in vault.rglob("*.md"):
            rel = str(path.relative_to(vault)).replace("\\", "/")
            if not _is_trusted_rel(rel):
                continue
            dmeta, _ = _page_meta(vault, rel)
            other_name = dmeta.get("name") or path.stem
            overlap = candidate_tokens & _name_tokens(other_name)
            if len(overlap) >= _MIN_TOKEN_OVERLAP:
                _add_hint(
                    hints,
                    rel=rel,
                    title=other_name,
                    page_type=dmeta.get("type") or "synthesis",
                    reason=f"token overlap ({', '.join(sorted(overlap)[:3])})",
                    score=55 + len(overlap) * 5,
                )

    ranked = sorted(hints.values(), key=lambda h: (-h.score, h.rel_path))
    return tuple(ranked[:_MAX_HINTS])


def resolve_auto_promote_target(
    default_target: str,
    dedup_hints: tuple[DedupHint, ...],
    merge_targets: tuple[MergeTargetOption, ...],
) -> tuple[str, str]:
    """Pick merge path + one-line summary for glance-and-approve."""
    if dedup_hints:
        hint = dedup_hints[0]
        return (
            hint.rel_path,
            f"Merge into {hint.title} — {hint.reason}",
        )
    for option in merge_targets:
        if option.is_default:
            return option.rel_path, f"New trusted page — {option.rel_path}"
    clean = default_target.replace("\\", "/")
    return clean, f"Promote — {clean}"


def build_merge_target_options(
    default_target: str,
    dedup_hints: tuple[DedupHint, ...],
    *,
    meta: dict[str, str] | None = None,
    candidate_rel: str | None = None,
) -> tuple[MergeTargetOption, ...]:
    """Picker options: default inferred path + dedup matches."""
    seen: set[str] = set()
    options: list[MergeTargetOption] = []

    default = default_target.replace("\\", "/")
    if default:
        options.append(
            MergeTargetOption(
                rel_path=default,
                label=f"Default — {default}",
                is_default=True,
                from_dedup=False,
            )
        )
        seen.add(default)

    for hint in dedup_hints:
        if hint.rel_path in seen:
            continue
        options.append(
            MergeTargetOption(
                rel_path=hint.rel_path,
                label=f"{hint.title} — {hint.reason}",
                is_default=False,
                from_dedup=True,
            )
        )
        seen.add(hint.rel_path)

    if meta and candidate_rel and len(options) <= 1:
        alt = _infer_promote_target(candidate_rel.replace("\\", "/"), meta)
        if alt not in seen:
            options.append(
                MergeTargetOption(
                    rel_path=alt,
                    label=f"Inferred — {alt}",
                    is_default=not default,
                    from_dedup=False,
                )
            )

    return tuple(options)


def patch_provenance_target(provenance: list | None, target_path: str) -> list[dict[str, str]]:
    """Set vault_candidate provenance target before promote."""
    normalized = validate_promote_target(target_path)
    updated: list[dict[str, str]] = []
    replaced = False
    for item in provenance or []:
        if isinstance(item, dict) and item.get("kind") == "vault_candidate":
            updated.append({**item, "target": normalized})
            replaced = True
        elif isinstance(item, dict):
            updated.append(dict(item))
    if not replaced:
        updated.insert(0, {"kind": "vault_candidate", "ref": "", "target": normalized})
    return updated