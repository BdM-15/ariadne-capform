"""Education Studio — suggest topic, Grok explain, queue lesson draft (Phase 22e-1)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.llm.router import CompletionResult, LlmRouterError, LlmTaskKind, complete
from thread.services.operator_learning import (
    DEFAULT_LEARNING_RECORD_REL,
    list_education_lessons,
    load_operator_learning,
)
from thread.services.vault_write import (
    VaultWriteError,
    VaultWriteResult,
    _render_frontmatter,
    _slug,
    _today,
    append_log,
    queue_vault_candidate_review,
    sandbox_candidate_rel,
    sandbox_enabled,
    update_index_entry,
)
from thread.services.knowledge import _safe_path


class EducationStudioError(Exception):
    pass


def education_vault_review_href(review_id: uuid.UUID | str) -> str:
    """Vault candidates (including lesson drafts) approve on Knowledge → Vault Inbox."""
    return f"/knowledge?inbox={review_id}#knowledge-vault-inbox"


def _studio_snapshot_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "education_studio_last.json"


def save_education_studio_snapshot(settings: Settings, studio: EducationStudioWidget) -> None:
    if not studio.response and not studio.suggestion:
        return
    path = _studio_snapshot_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suggestion": studio.suggestion,
        "response": studio.response,
        "response_kind": studio.response_kind,
        "model_used": studio.model_used,
        "provider": studio.provider,
        "draft_title": studio.draft_title,
        "draft_target": studio.draft_target,
        "review_id": studio.review_id,
        "flash": studio.flash,
        "flash_ok": studio.flash_ok,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_education_studio_widget(settings: Settings) -> EducationStudioWidget:
    """Restore last Studio session so draft previews survive navigation."""
    base = EducationStudioWidget(
        grok_configured=bool(settings.xai_api_key),
        reasoning_model=settings.reasoning_llm_model,
    )
    path = _studio_snapshot_path(settings)
    if not path.is_file():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(data, dict):
        return base
    response = data.get("response")
    if not isinstance(response, str) or not response.strip():
        return base
    review_id = str(data.get("review_id") or "").strip() or None
    return EducationStudioWidget(
        grok_configured=base.grok_configured,
        reasoning_model=base.reasoning_model,
        suggestion=str(data.get("suggestion") or ""),
        response=response,
        response_kind=str(data.get("response_kind") or "") or None,
        model_used=str(data.get("model_used") or "") or None,
        provider=str(data.get("provider") or "") or None,
        draft_title=str(data.get("draft_title") or "") or None,
        draft_target=str(data.get("draft_target") or "") or None,
        review_id=review_id,
        review_href=education_vault_review_href(review_id) if review_id else None,
        flash=str(data.get("flash") or "") or None,
        flash_ok=bool(data.get("flash_ok", True)),
    )


@dataclass(frozen=True)
class EducationStudioWidget:
    grok_configured: bool
    reasoning_model: str
    suggestion: str = ""
    response: str | None = None
    response_kind: str | None = None
    error: str | None = None
    flash: str | None = None
    flash_ok: bool = True
    provider: str | None = None
    model_used: str | None = None
    review_id: str | None = None
    review_href: str | None = None
    draft_title: str | None = None
    draft_target: str | None = None

    @staticmethod
    def idle(settings: Settings) -> EducationStudioWidget:
        return load_education_studio_widget(settings)


@dataclass(frozen=True)
class EducationExplainResult:
    text: str
    provider: str
    model: str


@dataclass(frozen=True)
class EducationDraftResult:
    title: str
    body: str
    lesson_number: int
    lesson_id: str
    target_rel: str
    candidate_path: str
    review_id: uuid.UUID
    provider: str
    model: str


def _vault_root(settings: Settings) -> Path:
    return settings.resolve(settings.knowledge_vault_path)


def _plan_excerpt(settings: Settings, *, limit: int = 5500) -> str:
    plan_path = settings.resolve(Path("docs/PLAN.md"))
    if not plan_path.is_file():
        return ""
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    markers = ("### Phase 22", "### Phase 20", "## Identification", "Living Briefing Packet")
    start = 0
    for marker in markers:
        idx = text.find(marker)
        if idx >= 0:
            start = idx
            break
    return text[start : start + limit].strip()


def _learning_record_excerpt(settings: Settings, *, limit: int = 3500) -> str:
    path = _vault_root(settings) / DEFAULT_LEARNING_RECORD_REL
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            text = text[end + 4 :]
    return text.strip()[:limit]


def build_education_context_bundle(settings: Settings, *, suggestion: str = "") -> dict:
    lessons = list_education_lessons(settings)
    state = load_operator_learning(settings)
    return {
        "operator": state["operator"],
        "completed_lessons": state["completed_lessons"],
        "curriculum": [
            {
                "number": lesson.lesson_number,
                "title": lesson.title,
                "id": lesson.id,
                "completed": lesson.completed,
            }
            for lesson in lessons
        ],
        "learning_record_excerpt": _learning_record_excerpt(settings),
        "plan_excerpt": _plan_excerpt(settings),
        "suggestion": suggestion.strip(),
    }


def _build_explain_messages(bundle: dict) -> list[dict[str, str]]:
    context_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "You are the Thread operator education coach for Ariadne's Thread — "
                "a solo-operator federal capture platform (Shipley milestones, living briefing packet, "
                "Insights→Watch→Track→Capture funnel). "
                "The reader is the product owner/builder, not a capture expert. "
                "Explain Thread-native concepts only — use vault/PLAN context provided. "
                "End with a short **What you can steer** section (product levers). "
                "Do not invent features not in context. Markdown OK. No YAML frontmatter."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Operator question / thought:\n{bundle.get('suggestion') or '(none)'}\n\n"
                f"Context JSON:\n{context_json[:14000]}"
            ),
        },
    ]


def _build_draft_messages(bundle: dict) -> list[dict[str, str]]:
    next_num = _next_lesson_number(bundle.get("curriculum") or [])
    context_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "You draft a Thread operator education lesson (markdown body only, NO YAML frontmatter). "
                f"This will become lesson number {next_num:02d}. "
                "Match tone of existing curriculum: one concept, Shipley/capture tied to Thread UI. "
                "Required sections: opening abstract callout (> [!abstract]), "
                "## Who this is for, core teaching sections with tables where helpful, "
                "## What you can steer (product levers), "
                "> [!question] Reflection (2 min) with 2 bullets, "
                "## Related reading (wikilinks OK). "
                "Start with a single # H1 title. Thread-native only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic from operator:\n{bundle.get('suggestion') or '(none)'}\n\n"
                f"Context JSON:\n{context_json[:14000]}"
            ),
        },
    ]


def _next_lesson_number(curriculum: list[dict]) -> int:
    numbers = [int(item["number"]) for item in curriculum if str(item.get("number", "")).isdigit()]
    return (max(numbers) if numbers else 0) + 1


def _title_from_draft_body(body: str, *, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback[:120] or "Education lesson draft"


def _lesson_slug(title: str, lesson_number: int) -> str:
    short_title = re.sub(r"^lesson\s+\d+\s*[—\-:]\s*", "", title, flags=re.IGNORECASE).strip()
    short = _slug(short_title)[:40].strip("-") or "lesson"
    return f"{lesson_number:02d}-{short}"


async def explain_education_topic(settings: Settings, *, suggestion: str) -> EducationExplainResult:
    clean = (suggestion or "").strip()
    if not clean:
        raise EducationStudioError("Enter a question or topic first.")
    if not settings.xai_api_key:
        raise EducationStudioError("Grok not configured — set XAI_API_KEY in .env.")

    bundle = build_education_context_bundle(settings, suggestion=clean)
    try:
        result: CompletionResult = await complete(
            settings,
            task_kind=LlmTaskKind.REASONING,
            messages=_build_explain_messages(bundle),
            max_tokens=min(settings.llm_max_output_tokens, 4096),
        )
    except LlmRouterError as exc:
        raise EducationStudioError(str(exc)) from exc

    text = (result.text or "").strip()
    if not text:
        raise EducationStudioError("Grok returned an empty response.")
    return EducationExplainResult(
        text=text,
        provider=result.provider.value,
        model=result.model,
    )


def write_education_lesson_candidate(
    settings: Settings,
    *,
    title: str,
    body: str,
    lesson_number: int,
    lesson_id: str,
    suggestion: str,
) -> VaultWriteResult:
    slug = _lesson_slug(title, lesson_number)
    today = _today()
    use_sandbox = sandbox_enabled(settings)
    rel = (
        sandbox_candidate_rel(f"edu-{slug}", today)
        if use_sandbox
        else f"generated-projections/edu-{slug}-{today}.md"
    )
    vault = _vault_root(settings)
    target = _safe_path(vault, rel)
    target_rel = f"education/lessons/{slug}.md"
    meta = {
        "title": title,
        "name": title,
        "type": "education",
        "id": lesson_id,
        "tags": "[education, lesson, draft]",
        "lesson_number": str(lesson_number),
        "prerequisites": "[]",
        "estimated_minutes": "12",
        "trust": "candidate",
        "added": today,
        "last_updated": today,
        "citations": f"source:education_studio,topic:{_slug(suggestion)[:40]}",
        "source": "education_studio",
        "promote_target": target_rel,
    }
    content = (
        _render_frontmatter(meta)
        + body.strip()
        + "\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    index_updated = update_index_entry(settings, rel, title, "education lesson draft")
    log_appended = append_log(settings, "candidate", title, f"education_studio → {target_rel}")
    return VaultWriteResult(
        path=rel,
        created=True,
        appended=False,
        index_updated=index_updated,
        log_appended=log_appended,
    )


async def queue_education_lesson_draft(
    settings: Settings,
    session: AsyncSession,
    *,
    suggestion: str,
) -> EducationDraftResult:
    clean = (suggestion or "").strip()
    if not clean:
        raise EducationStudioError("Enter a topic before drafting a lesson.")
    if not settings.xai_api_key:
        raise EducationStudioError("Grok not configured — set XAI_API_KEY in .env.")

    bundle = build_education_context_bundle(settings, suggestion=clean)
    lesson_number = _next_lesson_number(bundle["curriculum"])
    lesson_id = f"education-lesson-{lesson_number:02d}"

    try:
        result: CompletionResult = await complete(
            settings,
            task_kind=LlmTaskKind.REASONING,
            messages=_build_draft_messages(bundle),
            max_tokens=min(settings.llm_max_output_tokens, 8192),
        )
    except LlmRouterError as exc:
        raise EducationStudioError(str(exc)) from exc

    body = (result.text or "").strip()
    if not body:
        raise EducationStudioError("Grok returned an empty lesson draft.")

    title = _title_from_draft_body(body, fallback=clean)
    slug = _lesson_slug(title, lesson_number)
    target_rel = f"education/lessons/{slug}.md"

    try:
        write_result = write_education_lesson_candidate(
            settings,
            title=title,
            body=body,
            lesson_number=lesson_number,
            lesson_id=lesson_id,
            suggestion=clean,
        )
    except (VaultWriteError, OSError) as exc:
        raise EducationStudioError(str(exc)) from exc

    record = await queue_vault_candidate_review(
        session,
        candidate_path=write_result.path,
        target_path=target_rel,
        opportunity_id=None,
    )
    await session.flush()

    return EducationDraftResult(
        title=title,
        body=body,
        lesson_number=lesson_number,
        lesson_id=lesson_id,
        target_rel=target_rel,
        candidate_path=write_result.path,
        review_id=record.id,
        provider=result.provider.value,
        model=result.model,
    )