"""FAB intent router — knowledge (vault) vs admin_task (operator_tasks)."""

from __future__ import annotations

import json
import re
from enum import StrEnum

import httpx

from thread.config import Settings
from thread.llm.router import LlmRouterError, LlmTaskKind, complete

_TASK_KEYWORDS: tuple[str, ...] = (
    "schedule",
    "meeting",
    "remind",
    "follow up",
    "follow-up",
    "followup",
    "call ",
    "email ",
    " due ",
    "due:",
    "todo",
    "to-do",
    "need to",
)


class CaptureIntent(StrEnum):
    KNOWLEDGE = "knowledge"
    ADMIN_TASK = "admin_task"


def classify_capture_intent_deterministic(raw_dump: str) -> CaptureIntent | None:
    """Instant keyword pass. None = ambiguous → LLM or default knowledge."""
    low = f" {raw_dump.lower()} "
    if any(token in low for token in _TASK_KEYWORDS):
        return CaptureIntent.ADMIN_TASK
    if re.search(r"\bby\s+(mon|tue|wed|thu|fri|sat|sun)\b", low):
        return CaptureIntent.ADMIN_TASK
    return None


def _parse_intent_json(raw: str) -> CaptureIntent:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    intent = str(data.get("intent") or "").strip().lower()
    if intent in ("admin_task", "task", "admin"):
        return CaptureIntent.ADMIN_TASK
    return CaptureIntent.KNOWLEDGE


async def classify_capture_intent(
    settings: Settings,
    raw_dump: str,
    *,
    timeout_sec: float = 12.0,
) -> tuple[CaptureIntent, str]:
    """Deterministic first; Ollama ADMIN when ambiguous."""
    deterministic = classify_capture_intent_deterministic(raw_dump)
    if deterministic is not None:
        return deterministic, "rules"

    if not settings.local_admin_model_enabled:
        return CaptureIntent.KNOWLEDGE, "rules-default"

    try:
        result = await complete(
            settings,
            task_kind=LlmTaskKind.ADMIN,
            messages=[
                {
                    "role": "system",
                    "content": (
                        'Return ONLY JSON: {"intent": "knowledge" | "admin_task"}. '
                        "admin_task = meetings, reminders, calls, emails, todos, scheduling. "
                        "knowledge = facts, intel, capabilities, research notes for vault."
                    ),
                },
                {"role": "user", "content": f"Classify this FAB dump:\n{raw_dump[:2000]}"},
            ],
            max_tokens=64,
            temperature=0.0,
            client=httpx.AsyncClient(timeout=timeout_sec),
        )
        return _parse_intent_json(result.text), "ollama"
    except (LlmRouterError, json.JSONDecodeError, httpx.HTTPError, OSError, KeyError, TypeError):
        return CaptureIntent.KNOWLEDGE, "rules-default"