"""Plain-language guide for Tasks / GTD accomplish lane."""

from __future__ import annotations

from typing import Any

TASKS_GUIDE: dict[str, Any] = {
    "title": "Tasks — accomplish lane",
    "accent": "cyan",
    "purpose": (
        "Admin execution truth in Postgres — meetings, follow-ups, reminders from FAB. "
        "Not vault knowledge. Click a card for full context, hand-jam notes, EA checklist."
    ),
    "when": (
        "Dump admin work from global FAB, triage inbox, pick what to do now, log progress "
        "over days/weeks, mark done when finished."
    ),
    "output": (
        "GTD board lanes (Inbox → Next → Scheduled → Waiting → Deferred → Done). "
        "Work notes append on task — never overwrite EA title. Done tasks can seed vault playbooks later (16e)."
    ),
    "context_impact": (
        "Knowledge dumps still route Vault Inbox via FAB. Tasks = operator execution only. "
        "Opp-linked tasks show pursuit chip → /capture/{id}."
    ),
    "how_to_use": [
        "Capture task (header) or global FAB → meeting/reminder dump → lands Inbox or Scheduled.",
        "Click any card → right drawer opens: notes, checklist, provenance, lane actions.",
        "Lane buttons only move status — they do NOT open a form. Add context in drawer Work notes.",
        "Move to Next = do-now queue. Complete = done. Waiting = blocked on someone. Defer = someday.",
        "Bookmark /tasks?task={id} to reopen same task weeks later.",
        "Opportunity dropdown links task to pursuit (DB: opportunity_id) — enables workspace + Clew shortcuts.",
        "Assist section: MCP/Skills always available; pursuit tools need opportunity link.",
    ],
    "tips": [
        "Hover action buttons for one-line tooltips.",
        "EA suggests checklist steps at ingest — click square in drawer to tick off.",
        "Board = kanban lanes; List = flat filter view.",
        "If drawer shows empty, restart python app.py after git pull (migration + static refresh).",
        "Capture task opens centered modal (not bottom-right FAB only).",
        "LIS SECREP-style dumps auto-match pursuit name when FAB has no opp context.",
    ],
}

ACTION_HINTS: dict[str, str] = {
    "next": "Move to Next lane — your do-now queue. Instant. No form. Add notes in drawer.",
    "scheduled": "Move to Scheduled — time-bound / calendar work. Instant status change.",
    "waiting": "Move to Waiting — blocked on someone else. Instant status change.",
    "done": "Mark complete — moves to Done filter. Instant. Does not delete notes.",
    "deferred": "Defer to Someday — low urgency backlog lane.",
    "inbox": "Back to Inbox — clarify / triage again.",
}


def guide_for_tasks() -> dict[str, Any]:
    return dict(TASKS_GUIDE)


def action_hint(status: str) -> str:
    return ACTION_HINTS.get(status, "Change task lane status.")