"""Trusted vault writes — Karpathy ingest with review gate + schema enforcement."""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import CapabilityRun, ReviewRecord
from thread.research.capture_research import load_run
from thread.services.knowledge import _safe_path
from thread.services.review_gate import create_review_record
from thread.services.vault_review_context import ReviewVaultContext, resolve_review_vault_context
from thread.domain.enums import TrustLevel
from thread.services.vault_sandbox import (
    VaultSandboxError,
    apply_test_markers,
    assert_promote_allowed,
    assert_trusted_write_allowed,
    is_test_marked,
    sandbox_candidate_rel,
    sandbox_enabled,
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

WRITE_ZONES: tuple[str, ...] = (
    "entities/agencies/",
    "entities/competitors/",
    "global/domain_intel/",
    "pursuits/",
    "generated-projections/",
    "relationships/",
)

PROTECTED_PREFIXES: tuple[str, ...] = (
    "foundation/",
    "data-elements/",
    "milestones/",
    "training/",
    "education/",
    ".obsidian/",
)

INDEX_PAGES_MARKER = "## Pages\n"


class VaultWriteError(Exception):
    pass


def _guard_vault_sandbox(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except VaultSandboxError as exc:
        raise VaultWriteError(str(exc)) from exc


@dataclass(frozen=True)
class VaultWriteResult:
    path: str
    created: bool
    appended: bool
    index_updated: bool
    log_appended: bool
    skipped_dedup: bool = False


@dataclass
class VaultIngestResult:
    review_id: str
    writes: list[VaultWriteResult] = field(default_factory=list)
    semantic: dict | None = None

    @property
    def paths(self) -> list[str]:
        return [w.path for w in self.writes if not w.skipped_dedup]


def _vault_root(settings: Settings) -> Path:
    return settings.resolve(settings.knowledge_vault_path)


def _slug(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower()).strip("-") or "unknown"
    return base[:72]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    body = text[match.end() :]
    return meta, body


def _render_frontmatter(meta: dict[str, str]) -> str:
    lines = ["---"]
    for key in sorted(meta.keys()):
        value = meta[key]
        if " " in value or ":" in value:
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _is_education_lesson_path(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").lstrip("/")
    return normalized.startswith("education/lessons/") and normalized.endswith(".md")


def _assert_write_zone(rel_path: str) -> None:
    normalized = rel_path.replace("\\", "/").lstrip("/")
    if normalized.endswith("index.md") or normalized.endswith("log.md"):
        raise VaultWriteError("index.md and log.md are updated via helpers only")
    if _is_education_lesson_path(normalized):
        return
    if any(normalized.startswith(p) for p in PROTECTED_PREFIXES):
        raise VaultWriteError(f"Protected vault path: {normalized}")
    if not any(normalized.startswith(z) for z in WRITE_ZONES):
        raise VaultWriteError(f"Path not in allowed write zones: {normalized}")


def _page_contains_identity(text: str, *, review_id: str | None, award_key: str | None) -> bool:
    if review_id and review_id in text:
        return True
    if award_key and award_key in text:
        return True
    return False


def append_log(settings: Settings, kind: str, title: str, detail: str = "") -> bool:
    vault = _vault_root(settings)
    log_path = vault / "log.md"
    if not log_path.is_file():
        return False
    stamp = _today()
    entry = f"\n## [{stamp}] {kind} | {title}"
    if detail:
        entry += f" | {detail}"
    entry += "\n"
    log_path.write_text(log_path.read_text(encoding="utf-8") + entry, encoding="utf-8")
    return True


def update_index_entry(settings: Settings, rel_path: str, name: str, summary: str) -> bool:
    vault = _vault_root(settings)
    index_path = vault / "index.md"
    if not index_path.is_file():
        return False
    normalized = rel_path.replace("\\", "/").lstrip("/")
    text = index_path.read_text(encoding="utf-8")
    if normalized in text:
        return False
    stem = Path(normalized).stem
    line = f"- [[{stem}]] — `{normalized}` — {name} — {summary}\n"
    if INDEX_PAGES_MARKER not in text:
        text = text.rstrip() + f"\n\n{INDEX_PAGES_MARKER}\n{line}"
    else:
        parts = text.split(INDEX_PAGES_MARKER, 1)
        text = parts[0] + INDEX_PAGES_MARKER + parts[1].rstrip() + "\n" + line
    index_path.write_text(text, encoding="utf-8")
    return True


def _format_related(links: list[str]) -> str:
    unique = []
    for link in links:
        token = link.strip()
        if token and token not in unique:
            unique.append(token)
    if not unique:
        return "- (none)"
    return "\n".join(f"- [[{item}]]" for item in unique)


def append_trusted_page(
    settings: Settings,
    rel_path: str,
    *,
    name: str,
    page_type: str,
    page_id: str,
    review_id: str,
    citations: str,
    section_body: str,
    related: list[str] | None = None,
    award_key: str | None = None,
    tags: list[str] | None = None,
) -> VaultWriteResult:
    _assert_write_zone(rel_path)
    _guard_vault_sandbox(assert_trusted_write_allowed, settings, rel_path)
    _guard_vault_sandbox(
        assert_promote_allowed,
        settings,
        meta={"id": page_id},
        rel_path=rel_path,
        citations=citations,
    )
    vault = _vault_root(settings)
    target = _safe_path(vault, rel_path)
    if target.suffix.lower() != ".md":
        raise VaultWriteError("Vault writes must be .md pages")

    related_block = _format_related(related or [])
    today = _today()
    section = (
        f"\n## Added/Updated {today}\n\n"
        f"{section_body.rstrip()}\n\n"
        f"**Review:** `{review_id}`\n\n"
        f"### Related\n{related_block}\n"
    )

    created = False
    appended = False
    skipped = False

    if target.is_file():
        existing = target.read_text(encoding="utf-8")
        if _page_contains_identity(existing, review_id=review_id, award_key=award_key):
            return VaultWriteResult(
                path=rel_path.replace("\\", "/"),
                created=False,
                appended=False,
                index_updated=False,
                log_appended=False,
                skipped_dedup=True,
            )
        meta, body = _parse_frontmatter(existing)
        meta["trust"] = "trusted"
        meta["last_updated"] = today
        if review_id:
            meta["review_id"] = review_id
        if citations:
            prior = meta.get("citations", "")
            meta["citations"] = f"{prior} • {citations}".strip(" •") if prior else citations
        target.write_text(_render_frontmatter(meta) + body + section, encoding="utf-8")
        appended = True
    else:
        tag_list = tags or ["vault-ingest"]
        meta = {
            "name": name,
            "type": page_type,
            "id": page_id,
            "trust": "trusted",
            "review_id": review_id,
            "added": _now_iso(),
            "last_updated": today,
            "citations": citations,
            "tags": ", ".join(tag_list),
        }
        header = f"# {name}\n\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_frontmatter(meta) + header + section.lstrip(), encoding="utf-8")
        created = True
        appended = True

    summary = section_body.split("\n", 1)[0][:120] if section_body else name
    index_updated = update_index_entry(settings, rel_path, name, summary)
    log_appended = append_log(settings, "ingest", name, f"review:{review_id}")

    return VaultWriteResult(
        path=rel_path.replace("\\", "/"),
        created=created,
        appended=appended,
        index_updated=index_updated,
        log_appended=log_appended,
    )


_RELATED_HEADING_RE = re.compile(r"^##\s+Related\s*$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _extract_candidate_parts(body: str) -> tuple[str, list[str]]:
    """Split candidate markdown into editable body and Related wikilinks."""
    related_links: list[str] = []
    main = body
    match = _RELATED_HEADING_RE.search(body)
    if match:
        main = body[: match.start()]
        related_section = body[match.end() :]
        for line in related_section.splitlines():
            for token in _WIKILINK_RE.findall(line):
                if token not in related_links:
                    related_links.append(token)

    lines: list[str] = []
    skipped_title = False
    for line in main.splitlines():
        if line.startswith("> Candidate"):
            continue
        if not skipped_title and line.startswith("# "):
            skipped_title = True
            continue
        lines.append(line)
    editable = "\n".join(lines).strip()
    return editable, related_links


def load_candidate_note(settings: Settings, candidate_rel: str) -> dict[str, Any]:
    """Load a generated-projections candidate for Capture Studio edit."""
    rel = candidate_rel.replace("\\", "/")
    if not rel.startswith("generated-projections/"):
        raise VaultWriteError("Only generated-projections candidates are editable")
    vault = _vault_root(settings)
    target = _safe_path(vault, rel)
    if not target.is_file():
        raise VaultWriteError(f"Candidate not found: {rel}")
    text = target.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    if meta.get("trust", "candidate") != "candidate":
        raise VaultWriteError("Only candidate trust notes are editable in Studio")
    editable_body, related = _extract_candidate_parts(body)
    return {
        "candidate_path": rel,
        "name": meta.get("name") or Path(rel).stem,
        "page_type": meta.get("type") or "synthesis",
        "body": editable_body,
        "related": related,
        "citations": meta.get("citations", ""),
        "source": meta.get("source", ""),
    }


def save_candidate_note(
    settings: Settings,
    candidate_rel: str,
    *,
    name: str,
    body: str,
    page_type: str | None = None,
    related: list[str] | None = None,
) -> VaultWriteResult:
    """Update an existing candidate note — stays under generated-projections/."""
    rel = candidate_rel.replace("\\", "/")
    if not rel.startswith("generated-projections/"):
        raise VaultWriteError("Only generated-projections candidates are editable")
    _assert_write_zone(rel)
    vault = _vault_root(settings)
    target = _safe_path(vault, rel)
    if not target.is_file():
        raise VaultWriteError(f"Candidate not found: {rel}")

    text = target.read_text(encoding="utf-8")
    meta, existing_body = _parse_frontmatter(text)
    if meta.get("trust", "candidate") != "candidate":
        raise VaultWriteError("Only candidate trust notes are editable in Studio")

    clean_name = name.strip()
    if not clean_name:
        raise VaultWriteError("Candidate name is required")

    _, existing_related = _extract_candidate_parts(existing_body)
    related_links = related if related is not None else existing_related

    meta["name"] = clean_name
    meta["last_updated"] = _today()
    if page_type:
        meta["type"] = page_type.strip() or meta.get("type", "synthesis")

    related_block = _format_related(related_links)
    content = (
        _render_frontmatter(meta)
        + f"# {clean_name}\n\n"
        + "> Candidate — approve in Knowledge → Vault Inbox before trusted merge.\n\n"
        + body.strip()
        + f"\n\n## Related\n{related_block}\n"
    )
    target.write_text(content, encoding="utf-8")
    index_updated = update_index_entry(settings, rel, clean_name, "candidate draft (edited)")
    log_appended = append_log(settings, "edit", clean_name, rel)
    return VaultWriteResult(
        path=rel,
        created=False,
        appended=False,
        index_updated=index_updated,
        log_appended=log_appended,
    )


def write_candidate_note(
    settings: Settings,
    *,
    name: str,
    body: str,
    page_type: str = "synthesis",
    citations: str = "",
    related: list[str] | None = None,
    source: str = "api",
) -> VaultWriteResult:
    slug = _slug(name)
    today = _today()
    use_sandbox = sandbox_enabled(settings) or source == "test" or is_test_marked(
        citations=citations, page_id=f"candidate-{slug}"
    )
    rel = sandbox_candidate_rel(slug, today) if use_sandbox else f"generated-projections/{slug}-{today}.md"
    vault = _vault_root(settings)
    target = _safe_path(vault, rel)
    meta = {
        "name": name,
        "type": page_type,
        "id": f"candidate-{_slug(name)}",
        "trust": "candidate",
        "added": _now_iso(),
        "last_updated": _today(),
        "citations": citations,
        "source": source,
    }
    if use_sandbox:
        meta = apply_test_markers(meta, source=source if source != "api" else "test")
    related_block = _format_related(related or [])
    content = (
        _render_frontmatter(meta)
        + f"# {name}\n\n"
        + "> Candidate — approve in Knowledge → Vault review before trusted merge.\n\n"
        + body.rstrip()
        + f"\n\n## Related\n{related_block}\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    index_updated = update_index_entry(settings, rel, name, "candidate draft")
    log_kind = "test" if use_sandbox else "candidate"
    log_appended = append_log(settings, log_kind, name, source if not use_sandbox else f"source:test • {source}")
    return VaultWriteResult(
        path=rel,
        created=True,
        appended=False,
        index_updated=index_updated,
        log_appended=log_appended,
    )


def _provenance_target(provenance: list | None) -> str | None:
    if not provenance:
        return None
    for item in provenance:
        if isinstance(item, dict) and item.get("target"):
            return str(item["target"]).replace("\\", "/")
    return None


def ensure_pursuit_scaffold(settings: Settings, pursuit_slug: str, opportunity_name: str) -> list[str]:
    vault = _vault_root(settings)
    created: list[str] = []
    for sub in ("", "01_capture", "02_intel"):
        (vault / "pursuits" / pursuit_slug / sub).mkdir(parents=True, exist_ok=True)
    readme = vault / "pursuits" / pursuit_slug / "README.md"
    if not readme.is_file():
        readme.write_text(
            _render_frontmatter(
                {
                    "name": opportunity_name,
                    "type": "opportunity",
                    "id": f"pursuit-{pursuit_slug}",
                    "trust": "trusted",
                    "added": _now_iso(),
                    "last_updated": _today(),
                    "tags": "pursuit",
                }
            )
            + f"# {opportunity_name}\n\n"
            + "Living pursuit wiki — trusted intel under `02_intel/`.\n\n"
            + "## Related\n- [[capture-llm-wiki]]\n- [[milestone_1]]\n",
            encoding="utf-8",
        )
        created.append(f"pursuits/{pursuit_slug}/README.md")
    return created


def _append_pursuit_intel(
    settings: Settings,
    ctx: ReviewVaultContext,
    *,
    review_id: str,
    kind: str,
    title: str,
    body: str,
    citations: str,
    related: list[str],
) -> VaultWriteResult | None:
    if not ctx.pursuit_slug:
        return None
    ensure_pursuit_scaffold(settings, ctx.pursuit_slug, ctx.opportunity_name or ctx.pursuit_slug)
    rel = f"pursuits/{ctx.pursuit_slug}/02_intel/{kind}-{_today()}.md"
    pursuit_related = [f"pursuits/{ctx.pursuit_slug}/README", *related]
    return append_trusted_page(
        settings,
        rel,
        name=title,
        page_type="opportunity",
        page_id=f"pursuit-intel-{kind}-{_slug(ctx.pursuit_slug)}",
        review_id=review_id,
        citations=citations,
        section_body=body,
        related=pursuit_related,
        tags=["pursuit", kind],
    )


async def queue_vault_candidate_review(
    session: AsyncSession,
    *,
    candidate_path: str,
    target_path: str | None = None,
    opportunity_id: uuid.UUID | None = None,
) -> ReviewRecord:
    provenance: list[dict[str, str]] = [
        {"kind": "vault_candidate", "ref": candidate_path, "target": target_path or ""},
    ]
    if opportunity_id:
        provenance.append({"kind": "opportunity", "ref": str(opportunity_id)})
    return await create_review_record(
        session,
        entity_type="vault_candidate",
        entity_id=candidate_path.replace("\\", "/"),
        trust_level=TrustLevel.CANDIDATE,
        provenance=provenance,
    )


def _infer_promote_target(candidate_rel: str, meta: dict[str, str]) -> str:
    page_type = meta.get("type", "synthesis")
    promote_target = (meta.get("promote_target") or "").strip().replace("\\", "/")
    if promote_target and _is_education_lesson_path(promote_target):
        return promote_target
    if page_type == "education":
        lesson_raw = (meta.get("lesson_number") or "").strip()
        stem = Path(candidate_rel).stem.removeprefix("edu-")
        if lesson_raw.isdigit():
            return f"education/lessons/{int(lesson_raw):02d}-{stem.split('-', 1)[-1] if '-' in stem else stem}.md"
        return f"education/lessons/{stem}.md"
    stem = Path(candidate_rel).stem
    if page_type == "agency":
        return f"entities/agencies/{stem}.md"
    if page_type == "competitor":
        return f"entities/competitors/{stem}.md"
    if page_type == "opportunity":
        return f"global/domain_intel/synthesis/{stem}.md"
    return f"global/domain_intel/synthesis/{stem}.md"


def _looks_like_education_ingest_slug(value: str) -> bool:
    clean = value.strip().lower()
    return clean.startswith("edu-") or (
        bool(re.search(r"-\d{4}-\d{2}-\d{2}$", clean)) and "lesson" in clean
    )


def _extract_education_lesson_body(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("> Candidate"):
            continue
        if stripped.startswith("## Added/Updated"):
            skipping = True
            continue
        if skipping:
            if stripped.startswith("# ") and not _looks_like_education_ingest_slug(stripped[2:]):
                skipping = False
            else:
                continue
        if stripped.startswith("# ") and _looks_like_education_ingest_slug(stripped[2:]):
            continue
        if stripped.startswith("**Review:**"):
            continue
        if stripped == "### Related":
            break
        out.append(line)
    return "\n".join(out).strip()


def _education_lesson_title(meta: dict[str, str], body: str, *, fallback: str) -> str:
    title = (meta.get("title") or "").strip().strip('"')
    if title:
        return title
    name = (meta.get("name") or "").strip()
    if name and not _looks_like_education_ingest_slug(name):
        return name
    for line in body.splitlines():
        if not line.startswith("# "):
            continue
        h1 = line[2:].strip()
        if h1 and not _looks_like_education_ingest_slug(h1):
            return h1
    return fallback


def _promote_education_lesson(
    settings: Settings,
    record: ReviewRecord,
    *,
    candidate_rel: str,
    meta: dict[str, str],
    body: str,
    target_rel: str,
) -> VaultIngestResult:
    vault = _vault_root(settings)
    target = _safe_path(vault, target_rel)
    lesson_body = _extract_education_lesson_body(body)
    title = _education_lesson_title(
        meta,
        lesson_body,
        fallback=Path(target_rel).stem.replace("-", " ").title(),
    )
    lesson_number = (meta.get("lesson_number") or "").strip() or "1"
    lesson_id = (meta.get("id") or "").strip() or f"education-lesson-{lesson_number.zfill(2)}"
    tags = (meta.get("tags") or "[education, lesson]").strip()
    if tags.startswith("["):
        tags = tags
    else:
        tags = "[education, lesson]"
    prerequisites = (meta.get("prerequisites") or "[]").strip() or "[]"
    estimated = (meta.get("estimated_minutes") or "12").strip() or "12"
    fm = {
        "title": title,
        "type": "education",
        "id": lesson_id,
        "tags": tags.replace(", draft]", "]") if ", draft]" in tags else tags,
        "lesson_number": lesson_number,
        "prerequisites": prerequisites,
        "estimated_minutes": estimated,
    }
    if lesson_body.startswith(f"# {title}"):
        lesson_body = lesson_body[len(f"# {title}") :].lstrip("\n")
    content = _render_frontmatter(fm) + lesson_body.rstrip() + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    created = not target.is_file()
    target.write_text(content, encoding="utf-8")
    index_updated = update_index_entry(settings, target_rel, title, "education lesson")
    log_appended = append_log(settings, "promote", title, f"education:{target_rel}")

    archive_dir = vault / "generated-projections" / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = _safe_path(vault, candidate_rel)
    if candidate_path.is_file():
        archive_path = archive_dir / Path(candidate_rel).name
        if archive_path.exists():
            archive_path = archive_dir / f"{Path(candidate_rel).stem}-{_today()}{Path(candidate_rel).suffix}"
        shutil.move(str(candidate_path), str(archive_path))

    write = VaultWriteResult(
        path=target_rel.replace("\\", "/"),
        created=created,
        appended=not created,
        index_updated=index_updated,
        log_appended=log_appended,
    )
    return VaultIngestResult(review_id=str(record.id), writes=[write])


def promote_vault_candidate(settings: Settings, record: ReviewRecord) -> VaultIngestResult | None:
    candidate_rel = record.entity_id.replace("\\", "/")
    if not candidate_rel.startswith("generated-projections/"):
        return None

    vault = _vault_root(settings)
    candidate_path = _safe_path(vault, candidate_rel)
    if not candidate_path.is_file():
        return None

    text = candidate_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    _guard_vault_sandbox(
        assert_promote_allowed,
        settings,
        meta=meta,
        rel_path=candidate_rel,
        citations=meta.get("citations", ""),
    )
    target_rel = _provenance_target(record.provenance) or _infer_promote_target(candidate_rel, meta)
    _guard_vault_sandbox(assert_trusted_write_allowed, settings, target_rel)
    _guard_vault_sandbox(
        assert_promote_allowed,
        settings,
        meta=meta,
        rel_path=target_rel,
        citations=meta.get("citations", ""),
    )
    review_id = str(record.id)

    page_type = (meta.get("type") or "").strip()
    if page_type == "education" or _is_education_lesson_path(target_rel):
        return _promote_education_lesson(
            settings,
            record,
            candidate_rel=candidate_rel,
            meta=meta,
            body=body,
            target_rel=target_rel,
        )

    body_lines = []
    for line in body.splitlines():
        if line.startswith("> Candidate"):
            continue
        body_lines.append(line)
    section_body = "\n".join(body_lines).strip()

    write = append_trusted_page(
        settings,
        target_rel,
        name=meta.get("name") or Path(candidate_rel).stem,
        page_type=meta.get("type") or "synthesis",
        page_id=meta.get("id") or f"promoted-{_slug(candidate_rel)}",
        review_id=review_id,
        citations=meta.get("citations") or f"source:vault_candidate • path:{candidate_rel}",
        section_body=section_body or "(empty candidate body)",
        related=["capture-llm-wiki", candidate_rel],
    )

    archive_dir = vault / "generated-projections" / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / Path(candidate_rel).name
    if archive_path.exists():
        archive_path = archive_dir / f"{Path(candidate_rel).stem}-{_today()}{Path(candidate_rel).suffix}"
    shutil.move(str(candidate_path), str(archive_path))
    append_log(settings, "promote", meta.get("name") or candidate_rel, f"archived:{archive_path.name}")

    return VaultIngestResult(review_id=review_id, writes=[write])


def _clew_synthesis(skill_id: str, output: dict[str, Any], inp: dict[str, Any]) -> tuple[str, str, list[str]]:
    mode = str(output.get("mode") or inp.get("mode") or "analysis")
    facet = str(output.get("facet_summary") or "")
    summary = str(output.get("summary") or output.get("method") or "")
    lines = [f"**Clew {skill_id}** — mode `{mode}`", ""]
    if facet:
        lines.append(f"**Facet:** {facet}")
    if summary:
        lines.append(f"**Summary:** {summary}")
    lines.append("")

    related: list[str] = []
    agency = (inp.get("agency") or "").strip()
    recipient = (inp.get("recipient") or "").strip()
    if agency:
        related.append(_slug(agency))
    if recipient:
        related.append(_slug(recipient))

    if mode == "money_flow":
        for row in (output.get("flows") or [])[:5]:
            lines.append(
                f"- {row.get('recipient')} → {row.get('agency')}: "
                f"${row.get('millions')}M ({row.get('actions')} actions)"
            )
            if row.get("agency"):
                related.append(_slug(str(row["agency"])))
            if row.get("recipient"):
                related.append(_slug(str(row["recipient"])))
    elif mode == "teaming":
        for row in (output.get("edges") or [])[:5]:
            lines.append(
                f"- {row.get('prime')} → {row.get('sub')}: "
                f"${row.get('millions')}M ({row.get('links')} links)"
            )
    elif mode == "spend_trend":
        for bar in (output.get("bars") or [])[:6]:
            lines.append(f"- FY{bar.get('year')}: ${bar.get('millions')}M")
    elif mode == "recipient_landscape":
        for row in (output.get("recipients") or [])[:5]:
            lines.append(f"- {row.get('recipient')}: ${row.get('millions')}M")
    else:
        lines.append(f"- {_clip(str(output), 800)}")

    citations = f"source:clew_intel • mode:{mode}"
    if agency:
        citations += f" • agency:{agency}"
    if recipient:
        citations += f" • recipient:{recipient}"
    return "\n".join(lines), citations, related[:8]


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def _ingest_clew_skill_run(
    settings: Settings,
    record: ReviewRecord,
    cap_run: CapabilityRun,
    ctx: ReviewVaultContext | None = None,
) -> VaultIngestResult:
    transcript = cap_run.transcript or {}
    output = transcript.get("output") if isinstance(transcript, dict) else {}
    inp = transcript.get("input") if isinstance(transcript, dict) else {}
    if not isinstance(output, dict):
        output = {}
    if not isinstance(inp, dict):
        inp = {}

    body, citations, related = _clew_synthesis(cap_run.skill_id, output, inp)
    review_id = str(record.id)
    mode = str(output.get("mode") or inp.get("mode") or "clew")
    facet_slug = _slug(str(output.get("facet_summary") or inp.get("agency") or "facet"))

    mode_slug = _slug(mode.replace("_", "-"))
    hub_path = f"relationships/clew-{mode_slug}-{_slug(facet_slug)}.md"
    hub = append_trusted_page(
        settings,
        hub_path,
        name=f"Clew {mode} — {facet_slug}",
        page_type="synthesis",
        page_id=f"clew-{mode}-{_slug(facet_slug)}",
        review_id=review_id,
        citations=citations + f" • review:{review_id}",
        section_body=body,
        related=related,
        tags=["clew", mode],
    )
    writes = [hub]

    agency = (inp.get("agency") or "").strip()
    if agency:
        writes.append(
            append_trusted_page(
                settings,
                f"entities/agencies/{_slug(agency)}.md",
                name=agency,
                page_type="agency",
                page_id=f"entity-agency-{_slug(agency)}",
                review_id=review_id,
                citations=citations,
                section_body=f"Clew `{mode}` slice referenced this agency.\n\n{body}",
                related=[hub_path, *related],
                tags=["agency", "clew"],
            )
        )

    recipient = (inp.get("recipient") or "").strip()
    if not recipient and output.get("flows"):
        top = output["flows"][0]
        recipient = str(top.get("recipient") or "").strip()
    if recipient:
        writes.append(
            append_trusted_page(
                settings,
                f"entities/competitors/{_slug(recipient)}.md",
                name=recipient,
                page_type="competitor",
                page_id=f"entity-competitor-{_slug(recipient)}",
                review_id=review_id,
                citations=citations,
                section_body=f"Clew `{mode}` slice referenced this recipient.\n\n{body}",
                related=[hub_path, *related],
                tags=["competitor", "clew"],
            )
        )

    if ctx and ctx.pursuit_slug:
        pursuit_write = _append_pursuit_intel(
            settings,
            ctx,
            review_id=review_id,
            kind=f"clew-{mode_slug}",
            title=f"Clew {mode} — {ctx.opportunity_name or ctx.pursuit_slug}",
            body=body,
            citations=citations,
            related=[hub_path],
        )
        if pursuit_write:
            writes.append(pursuit_write)

    return VaultIngestResult(review_id=review_id, writes=writes)


def _ingest_research_finding(
    settings: Settings,
    record: ReviewRecord,
    ctx: ReviewVaultContext | None = None,
) -> VaultIngestResult | None:
    parts = record.entity_id.split(":")
    if len(parts) < 3:
        return None
    run_id, _, idx_str = parts[0], parts[1], parts[2]
    try:
        idx = int(idx_str)
    except ValueError:
        return None
    run = load_run(settings, run_id)
    if not run:
        return None
    findings = run.get("findings") or []
    if idx >= len(findings):
        return None
    finding = findings[idx]
    title = str(finding.get("title") or f"Finding {idx}")
    summary = str(finding.get("summary") or "")
    review_id = str(record.id)
    rel = f"global/domain_intel/findings/{_slug(title)}.md"
    write = append_trusted_page(
        settings,
        rel,
        name=title,
        page_type="synthesis",
        page_id=f"finding-{_slug(title)}",
        review_id=review_id,
        citations=f"source:web_research • run:{run_id}",
        section_body=summary,
        related=["capture-llm-wiki"],
        tags=["research", "finding"],
    )
    writes = [write]
    if ctx and ctx.pursuit_slug:
        pursuit_write = _append_pursuit_intel(
            settings,
            ctx,
            review_id=review_id,
            kind="research-finding",
            title=title,
            body=summary,
            citations=f"source:web_research • run:{run_id}",
            related=[rel],
        )
        if pursuit_write:
            writes.append(pursuit_write)
    return VaultIngestResult(review_id=review_id, writes=writes)


def _ingest_research_interpretation(
    settings: Settings,
    record: ReviewRecord,
    ctx: ReviewVaultContext | None = None,
) -> VaultIngestResult | None:
    run_id = record.entity_id.split(":", 1)[0]
    run = load_run(settings, run_id)
    if not run:
        return None
    interpretation = str(run.get("interpretation") or "")
    if not interpretation:
        return None
    query = str(run.get("query") or "research")
    review_id = str(record.id)
    rel = f"global/domain_intel/synthesis/{_slug(query)[:48]}.md"
    write = append_trusted_page(
        settings,
        rel,
        name=f"Research — {query[:60]}",
        page_type="synthesis",
        page_id=f"research-{_slug(query)}",
        review_id=review_id,
        citations=f"source:web_research • run:{run_id} • lens:{run.get('lens')}",
        section_body=interpretation,
        related=["capture-llm-wiki"],
        tags=["research", "interpretation"],
    )
    writes = [write]
    if ctx and ctx.pursuit_slug:
        pursuit_write = _append_pursuit_intel(
            settings,
            ctx,
            review_id=review_id,
            kind="research-interpretation",
            title=f"Research — {query[:60]}",
            body=interpretation,
            citations=f"source:web_research • run:{run_id}",
            related=[rel],
        )
        if pursuit_write:
            writes.append(pursuit_write)
    return VaultIngestResult(review_id=review_id, writes=writes)


def _compound_semantic_after_writes(settings: Settings, result: VaultIngestResult | None) -> VaultIngestResult | None:
    if not result or not result.paths:
        return result
    from thread.services.vault_semantic_graph import compound_semantic_graph

    result.semantic = compound_semantic_graph(settings).to_dict()
    return result


async def ingest_approved_review(
    session: AsyncSession,
    settings: Settings,
    record: ReviewRecord,
) -> VaultIngestResult | None:
    if record.review_state != "accepted" or record.trust_level not in ("trusted", "TRUSTED"):
        return None

    ctx = await resolve_review_vault_context(session, settings, record)

    if record.entity_type == "vault_candidate":
        return _compound_semantic_after_writes(settings, promote_vault_candidate(settings, record))

    if record.entity_type == "skill_run":
        run_key, _, skill_id = record.entity_id.partition(":")
        try:
            cap_run = await session.get(CapabilityRun, uuid.UUID(run_key))
        except ValueError:
            cap_run = None
        if not cap_run:
            return None
        skill_id = cap_run.skill_id or skill_id
        if skill_id == "clew_intel":
            return _compound_semantic_after_writes(
                settings, _ingest_clew_skill_run(settings, record, cap_run, ctx)
            )
        return None

    if record.entity_type == "research_finding":
        return _compound_semantic_after_writes(settings, _ingest_research_finding(settings, record, ctx))

    if record.entity_type == "research_interpretation":
        return _compound_semantic_after_writes(
            settings, _ingest_research_interpretation(settings, record, ctx)
        )

    return None