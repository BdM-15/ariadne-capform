"""EA polish at FAB ingest — chicken-scratch → normalized operator_tasks fields."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from thread.config import Settings
from thread.domain.enums import (
    OperatorTaskKind,
    OperatorTaskPriority,
    OperatorTaskStatus,
)
from thread.llm.router import LlmRouterError, LlmTaskKind, complete
from thread.services.vault_candidate_polish import _rules_fix_common_typos

_MAX_TITLE = 80


@dataclass(frozen=True)
class PolishedTaskDraft:
    title: str
    description: str
    task_kind: str
    status: str
    priority: str
    due_at: datetime | None
    start_at: datetime | None
    duration_minutes: int | None
    project_label: str | None
    context_tags: tuple[str, ...]
    attendees: tuple[dict[str, str], ...]
    location: str | None
    waiting_on: str | None
    checklist: tuple[dict[str, object], ...]
    categories: tuple[str, ...]
    provider: str


def _title_case_words(text: str) -> str:
    words = re.sub(r"\s+", " ", text.strip()).split()
    small = {"a", "an", "the", "for", "with", "and", "to", "of", "on", "at"}
    out: list[str] = []
    for idx, word in enumerate(words):
        low = word.lower()
        if idx > 0 and low in small:
            out.append(low)
        else:
            out.append(low[:1].upper() + low[1:] if low else low)
    return " ".join(out)[:_MAX_TITLE]


def _infer_task_kind(raw: str) -> str:
    low = raw.lower()
    if "meeting" in low or "schedule" in low:
        return OperatorTaskKind.MEETING.value
    if "call" in low:
        return OperatorTaskKind.CALL.value
    if "email" in low:
        return OperatorTaskKind.EMAIL.value
    if "follow" in low:
        return OperatorTaskKind.FOLLOW_UP.value
    if "remind" in low:
        return OperatorTaskKind.PREP.value
    return OperatorTaskKind.OTHER.value


def _extract_attendees(raw: str) -> tuple[dict[str, str], ...]:
    names: list[dict[str, str]] = []
    for match in re.finditer(
        r"\bwith\s+((?:[A-Z][a-z]+(?:\s+[A-Z]\.?)?)(?:\s+and\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))*)",
        raw,
    ):
        chunk = match.group(1)
        for part in re.split(r"\s+and\s+", chunk):
            name = part.strip()
            if name and not any(n["name"] == name for n in names):
                names.append({"name": name})
    return tuple(names)


def _parse_checklist_raw(raw: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    items: list[dict[str, object]] = []
    for entry in raw[:12]:
        if isinstance(entry, dict) and entry.get("item"):
            items.append({"item": str(entry["item"]).strip(), "done": bool(entry.get("done"))})
        elif isinstance(entry, str) and entry.strip():
            items.append({"item": entry.strip(), "done": False})
    return tuple(items)


def _meeting_checklist_fallback() -> tuple[dict[str, object], ...]:
    return (
        {"item": "Confirm attendees and time", "done": False},
        {"item": "Draft agenda / objectives", "done": False},
        {"item": "Send calendar invite", "done": False},
    )


def rules_polish_task(raw_dump: str) -> PolishedTaskDraft:
    """Deterministic fallback when Ollama off or unreachable."""
    cleaned = _rules_fix_common_typos(raw_dump.strip())
    first_line = ""
    for line in cleaned.splitlines():
        token = line.strip().lstrip("-*#").strip()
        if len(token) >= 3:
            first_line = token
            break
    title = _title_case_words(first_line or cleaned[:_MAX_TITLE])
    kind = _infer_task_kind(cleaned)
    status = OperatorTaskStatus.SCHEDULED.value if kind == OperatorTaskKind.MEETING.value else OperatorTaskStatus.INBOX.value
    project = None
    proj_match = re.search(r"\bfor\s+([A-Z][A-Za-z0-9 /-]{4,48})", cleaned)
    if proj_match:
        project = proj_match.group(1).strip()
    return PolishedTaskDraft(
        title=title,
        description=cleaned,
        task_kind=kind,
        status=status,
        priority=OperatorTaskPriority.NORMAL.value,
        due_at=None,
        start_at=None,
        duration_minutes=60 if kind == OperatorTaskKind.MEETING.value else None,
        project_label=project,
        context_tags=(),
        attendees=_extract_attendees(cleaned),
        location=None,
        waiting_on=None,
        checklist=_meeting_checklist_fallback() if kind == OperatorTaskKind.MEETING.value else (),
        categories=("admin",),
        provider="rules",
    )


def _parse_task_json(raw: str) -> PolishedTaskDraft:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("task JSON must be object")

    def _enum(value: str, allowed: set[str], default: str) -> str:
        clean = str(value or default).strip().lower()
        return clean if clean in allowed else default

    kind_allowed = {k.value for k in OperatorTaskKind}
    status_allowed = {s.value for s in OperatorTaskStatus}
    priority_allowed = {p.value for p in OperatorTaskPriority}

    attendees_raw = data.get("attendees") or []
    attendees: list[dict[str, str]] = []
    if isinstance(attendees_raw, list):
        for item in attendees_raw:
            if isinstance(item, dict) and item.get("name"):
                attendees.append({"name": str(item["name"]).strip()})

    return PolishedTaskDraft(
        title=_title_case_words(str(data.get("title") or "")),
        description=str(data.get("description") or "").strip(),
        task_kind=_enum(str(data.get("task_kind") or ""), kind_allowed, OperatorTaskKind.OTHER.value),
        status=_enum(str(data.get("status") or ""), status_allowed, OperatorTaskStatus.INBOX.value),
        priority=_enum(str(data.get("priority") or ""), priority_allowed, OperatorTaskPriority.NORMAL.value),
        due_at=None,
        start_at=None,
        duration_minutes=int(data["duration_minutes"]) if data.get("duration_minutes") else None,
        project_label=str(data.get("project_label")).strip() if data.get("project_label") else None,
        context_tags=tuple(str(t) for t in (data.get("context_tags") or []) if t),
        attendees=tuple(attendees),
        location=str(data.get("location")).strip() if data.get("location") else None,
        waiting_on=str(data.get("waiting_on")).strip() if data.get("waiting_on") else None,
        checklist=_parse_checklist_raw(data.get("checklist")),
        categories=tuple(str(c) for c in (data.get("categories") or []) if c),
        provider="ollama",
    )


def build_task_polish_prompt(raw_dump: str, *, opportunity_name: str = "") -> list[dict[str, str]]:
    ctx = f"Linked pursuit: {opportunity_name}" if opportunity_name else "No pursuit link"
    return [
        {
            "role": "system",
            "content": (
                "Return ONLY JSON with keys: title, description, task_kind, status, priority, "
                "duration_minutes, project_label, context_tags, attendees, location, waiting_on, "
                "categories, checklist. "
                "title = Title Case 3-8 words. Fix typos; do not invent facts. "
                "task_kind: meeting|call|email|follow_up|prep|errand|waiting_for|someday|other. "
                "status: inbox|next|waiting|scheduled. priority: low|normal|high|urgent. "
                "attendees: [{\"name\": \"...\"}]. "
                "checklist: [{\"item\": \"actionable sub-step\", \"done\": false}] — 2-6 steps when task is multi-step; [] if single action. "
                "Null/omit unknown fields."
            ),
        },
        {"role": "user", "content": f"{ctx}\n\nPolish this admin task dump:\n{raw_dump[:3000]}"},
    ]


async def polish_task_at_ingest(
    settings: Settings,
    raw_dump: str,
    *,
    opportunity_name: str = "",
    timeout_sec: float = 20.0,
) -> PolishedTaskDraft:
    if not settings.local_admin_model_enabled:
        return rules_polish_task(raw_dump)
    try:
        result = await complete(
            settings,
            task_kind=LlmTaskKind.ADMIN,
            messages=build_task_polish_prompt(raw_dump, opportunity_name=opportunity_name),
            max_tokens=1024,
            temperature=0.1,
            client=httpx.AsyncClient(timeout=timeout_sec),
        )
        parsed = _parse_task_json(result.text)
        provider = getattr(result.provider, "value", str(result.provider))
        if not parsed.title:
            fallback = rules_polish_task(raw_dump)
            return PolishedTaskDraft(
                title=fallback.title,
                description=parsed.description or fallback.description,
                task_kind=parsed.task_kind or fallback.task_kind,
                status=parsed.status,
                priority=parsed.priority,
                due_at=parsed.due_at,
                start_at=parsed.start_at,
                duration_minutes=parsed.duration_minutes,
                project_label=parsed.project_label or fallback.project_label,
                context_tags=parsed.context_tags,
                attendees=parsed.attendees or fallback.attendees,
                location=parsed.location,
                waiting_on=parsed.waiting_on,
                checklist=parsed.checklist,
                categories=parsed.categories or fallback.categories,
                provider=provider,
            )
        return PolishedTaskDraft(
            title=parsed.title,
            description=parsed.description or _rules_fix_common_typos(raw_dump),
            task_kind=parsed.task_kind,
            status=parsed.status,
            priority=parsed.priority,
            due_at=parsed.due_at,
            start_at=parsed.start_at,
            duration_minutes=parsed.duration_minutes,
            project_label=parsed.project_label,
            context_tags=parsed.context_tags,
            attendees=parsed.attendees,
            location=parsed.location,
            waiting_on=parsed.waiting_on,
            checklist=parsed.checklist,
            categories=parsed.categories,
            provider=provider,
        )
    except (LlmRouterError, ValueError, json.JSONDecodeError, httpx.HTTPError, OSError):
        return rules_polish_task(raw_dump)