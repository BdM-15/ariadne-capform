"""Operator education lane — curriculum browser + completion state (Phase 22c)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings
from thread.services.knowledge import KnowledgeVaultError, read_vault_page
from thread.services.knowledge_digest import _parse_frontmatter

EDUCATION_ROOT = Path("education")
LESSONS_DIR = EDUCATION_ROOT / "lessons"
MISSION_REL = "education/MISSION.md"
DEFAULT_LEARNING_RECORD_REL = "education/learning-records/ben.md"
DEFAULT_OPERATOR = "ben"
MISSION_LESSON_KEY = "mission"


@dataclass(frozen=True)
class EducationLesson:
    id: str
    lesson_number: int
    rel_path: str
    title: str
    estimated_minutes: int | None
    completed: bool
    completed_at: str | None
    has_content: bool = True


@dataclass(frozen=True)
class EducationPanel:
    kind: str
    lesson_id: str | None
    title: str | None
    rel_path: str | None
    content: str | None
    completed: bool
    completed_at: str | None
    estimated_minutes: int | None
    error: str | None = None


@dataclass(frozen=True)
class EducationPageContext:
    vault_ready: bool
    operator: str
    lessons: tuple[EducationLesson, ...]
    active_key: str
    panel: EducationPanel
    completed_count: int
    total_count: int


def _vault_root(settings: Settings) -> Path:
    return settings.resolve(settings.knowledge_vault_path)


def _operator_learning_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "operator_learning.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _lesson_number(meta: dict[str, str], path: Path) -> int:
    raw = meta.get("lesson_number", "").strip()
    if raw.isdigit():
        return int(raw)
    prefix = path.name.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else 999


def _estimated_minutes(meta: dict[str, str]) -> int | None:
    raw = meta.get("estimated_minutes", "").strip()
    return int(raw) if raw.isdigit() else None


def _strip_frontmatter(text: str) -> str:
    """Return markdown body only — hide vault YAML from operator-facing render."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    return text[end + 4 :].lstrip("\n")


def _looks_like_ingest_slug(value: str) -> bool:
    clean = value.strip().lower()
    return clean.startswith("edu-") or (
        bool(re.search(r"-\d{4}-\d{2}-\d{2}$", clean)) and "lesson" in clean
    )


def _lesson_display_title(meta: dict[str, str], text: str, path: Path) -> str:
    title = (meta.get("title") or "").strip().strip('"')
    if title:
        return title
    name = (meta.get("name") or "").strip()
    if name and not _looks_like_ingest_slug(name):
        return name
    body = _strip_frontmatter(text)
    for line in body.splitlines():
        if not line.startswith("# "):
            continue
        h1 = line[2:].strip()
        if h1 and not _looks_like_ingest_slug(h1):
            return h1
    return path.stem.replace("-", " ").title()


def _sanitize_lesson_body(text: str, *, display_title: str) -> str:
    """Hide vault-ingest wrappers from operator-facing lesson render."""
    body = _strip_frontmatter(text)
    lines = body.splitlines()
    out: list[str] = []
    skipping_ingest = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Added/Updated"):
            skipping_ingest = True
            continue
        if skipping_ingest:
            if stripped.startswith("# ") and not _looks_like_ingest_slug(stripped[2:]):
                skipping_ingest = False
            else:
                continue
        if stripped.startswith("# ") and _looks_like_ingest_slug(stripped[2:]):
            continue
        if stripped.startswith("**Review:**"):
            continue
        if stripped == "### Related":
            break
        out.append(line)
    cleaned = "\n".join(out).strip()
    if cleaned.startswith(f"# {display_title}"):
        cleaned = cleaned[len(f"# {display_title}") :].lstrip("\n")
    return cleaned


def _lesson_id(meta: dict[str, str], path: Path) -> str:
    explicit = meta.get("id", "").strip()
    if explicit:
        return explicit
    return f"education-lesson-{path.stem}"


def load_operator_learning(settings: Settings) -> dict:
    path = _operator_learning_path(settings)
    if not path.is_file():
        return {"operator": DEFAULT_OPERATOR, "completed_lessons": [], "completed_at": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"operator": DEFAULT_OPERATOR, "completed_lessons": [], "completed_at": {}}
    if not isinstance(data, dict):
        return {"operator": DEFAULT_OPERATOR, "completed_lessons": [], "completed_at": {}}
    completed = data.get("completed_lessons")
    completed_at = data.get("completed_at")
    return {
        "operator": str(data.get("operator") or DEFAULT_OPERATOR),
        "completed_lessons": list(completed) if isinstance(completed, list) else [],
        "completed_at": dict(completed_at) if isinstance(completed_at, dict) else {},
    }


def _save_operator_learning(settings: Settings, payload: dict) -> None:
    path = _operator_learning_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_lesson_completed(settings: Settings, lesson_id: str) -> bool:
    state = load_operator_learning(settings)
    return lesson_id in state["completed_lessons"]


def list_education_lessons(settings: Settings) -> tuple[EducationLesson, ...]:
    vault = _vault_root(settings)
    lessons_dir = vault / LESSONS_DIR
    if not lessons_dir.is_dir():
        return ()

    state = load_operator_learning(settings)
    completed_ids = set(state["completed_lessons"])
    completed_at = state["completed_at"]

    lessons: list[EducationLesson] = []
    for path in sorted(lessons_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        rel = f"{LESSONS_DIR.as_posix()}/{path.name}"
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = _parse_frontmatter(text)
        lesson_id = _lesson_id(meta, path)
        lessons.append(
            EducationLesson(
                id=lesson_id,
                lesson_number=_lesson_number(meta, path),
                rel_path=rel,
                title=_lesson_display_title(meta, text, path),
                estimated_minutes=_estimated_minutes(meta),
                completed=lesson_id in completed_ids,
                completed_at=completed_at.get(lesson_id),
            )
        )
    return tuple(sorted(lessons, key=lambda item: (item.lesson_number, item.title)))


def _read_education_markdown(settings: Settings, rel: str) -> tuple[str, str]:
    vault = _vault_root(settings)
    page = read_vault_page(vault, rel)
    raw = page["content"]
    meta = _parse_frontmatter(raw)
    title = _lesson_display_title(meta, raw, vault / rel)
    return title, _sanitize_lesson_body(raw, display_title=title)


def _default_active_key(lessons: tuple[EducationLesson, ...]) -> str:
    for lesson in lessons:
        if not lesson.completed:
            return lesson.id
    if lessons:
        return lessons[0].id
    return MISSION_LESSON_KEY


def _normalize_active_key(raw: str | None, lessons: tuple[EducationLesson, ...]) -> str:
    clean = (raw or "").strip()
    if not clean or clean == MISSION_LESSON_KEY:
        return MISSION_LESSON_KEY
    if any(lesson.id == clean for lesson in lessons):
        return clean
    return _default_active_key(lessons)


def build_education_panel(
    settings: Settings,
    *,
    active_key: str,
    lessons: tuple[EducationLesson, ...] | None = None,
) -> EducationPanel:
    catalog = lessons if lessons is not None else list_education_lessons(settings)
    state = load_operator_learning(settings)
    completed_at = state["completed_at"]

    if active_key == MISSION_LESSON_KEY:
        vault = _vault_root(settings)
        mission_path = vault / MISSION_REL
        if not mission_path.is_file():
            return EducationPanel(
                kind="mission",
                lesson_id=None,
                title="Operator mission",
                rel_path=MISSION_REL,
                content=None,
                completed=False,
                completed_at=None,
                estimated_minutes=None,
                error="Mission file missing — seed education/MISSION.md in vault.",
            )
        title, content = _read_education_markdown(settings, MISSION_REL)
        return EducationPanel(
            kind="mission",
            lesson_id=None,
            title=title,
            rel_path=MISSION_REL,
            content=content,
            completed=False,
            completed_at=None,
            estimated_minutes=None,
        )

    lesson = next((item for item in catalog if item.id == active_key), None)
    if lesson is None:
        return EducationPanel(
            kind="empty",
            lesson_id=None,
            title=None,
            rel_path=None,
            content=None,
            completed=False,
            completed_at=None,
            estimated_minutes=None,
            error="Lesson not found.",
        )

    try:
        title, content = _read_education_markdown(settings, lesson.rel_path)
    except KnowledgeVaultError as exc:
        return EducationPanel(
            kind="lesson",
            lesson_id=lesson.id,
            title=lesson.title,
            rel_path=lesson.rel_path,
            content=None,
            completed=lesson.completed,
            completed_at=lesson.completed_at,
            estimated_minutes=lesson.estimated_minutes,
            error=str(exc),
        )

    return EducationPanel(
        kind="lesson",
        lesson_id=lesson.id,
        title=title,
        rel_path=lesson.rel_path,
        content=content,
        completed=lesson.completed,
        completed_at=lesson.completed_at,
        estimated_minutes=lesson.estimated_minutes,
    )


def build_education_page_context(
    settings: Settings,
    *,
    lesson: str = "",
) -> EducationPageContext:
    vault = _vault_root(settings)
    lessons = list_education_lessons(settings)
    active_key = _normalize_active_key(lesson, lessons)
    panel = build_education_panel(settings, active_key=active_key, lessons=lessons)
    completed_count = sum(1 for item in lessons if item.completed)
    state = load_operator_learning(settings)
    return EducationPageContext(
        vault_ready=vault.is_dir(),
        operator=state["operator"],
        lessons=lessons,
        active_key=active_key,
        panel=panel,
        completed_count=completed_count,
        total_count=len(lessons),
    )


def _lesson_slug_from_rel(rel_path: str) -> str:
    return Path(rel_path).stem


def _sync_learning_record_checkbox(
    settings: Settings,
    *,
    lesson_rel_path: str,
    completed: bool,
    operator: str = DEFAULT_OPERATOR,
) -> None:
    record_rel = DEFAULT_LEARNING_RECORD_REL
    vault = _vault_root(settings)
    record_path = vault / record_rel
    if not record_path.is_file():
        return

    slug = _lesson_slug_from_rel(lesson_rel_path)
    text = record_path.read_text(encoding="utf-8")
    checked = "[x]" if completed else "[ ]"
    unchecked = "[ ]" if completed else "[x]"

    patterns = [
        re.compile(
            rf"^(- ){re.escape(unchecked)}(\s+\*\*[^*]+\*\*.*{re.escape(slug)}.*)$",
            re.MULTILINE,
        ),
        re.compile(
            rf"^(- ){re.escape(unchecked)}(\s+.*{re.escape(slug)}.*)$",
            re.MULTILINE,
        ),
    ]
    updated = text
    for pattern in patterns:
        new_text, count = pattern.subn(rf"\1{checked}\2", updated, count=1)
        if count:
            updated = new_text
            break

    if updated != text:
        record_path.write_text(updated, encoding="utf-8")


def set_lesson_completed(
    settings: Settings,
    lesson_id: str,
    *,
    completed: bool | None = None,
) -> EducationLesson | None:
    lessons = list_education_lessons(settings)
    lesson = next((item for item in lessons if item.id == lesson_id), None)
    if lesson is None:
        return None

    state = load_operator_learning(settings)
    completed_ids = set(state["completed_lessons"])
    completed_at = dict(state["completed_at"])
    target = not lesson.completed if completed is None else completed

    if target:
        completed_ids.add(lesson_id)
        completed_at[lesson_id] = _utc_now_iso()
    else:
        completed_ids.discard(lesson_id)
        completed_at.pop(lesson_id, None)

    state["completed_lessons"] = sorted(completed_ids)
    state["completed_at"] = completed_at
    _save_operator_learning(settings, state)
    _sync_learning_record_checkbox(
        settings,
        lesson_rel_path=lesson.rel_path,
        completed=target,
        operator=state["operator"],
    )

    return EducationLesson(
        id=lesson.id,
        lesson_number=lesson.lesson_number,
        rel_path=lesson.rel_path,
        title=lesson.title,
        estimated_minutes=lesson.estimated_minutes,
        completed=target,
        completed_at=completed_at.get(lesson_id),
    )


def education_href(*, lesson: str = "") -> str:
    clean = lesson.strip()
    if not clean or clean == MISSION_LESSON_KEY:
        return "/education"
    return f"/education?lesson={clean}"