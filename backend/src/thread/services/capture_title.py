"""Glanceable capture titles — keyword rules for obvious cases, Ollama for the rest."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from thread.config import Settings
from thread.llm.router import LlmRouterError, LlmTaskKind, complete

_MAX_TITLE_WORDS = 8
_MAX_TITLE_CHARS = 72
_GENERIC_RULES_TITLE = "Quick Capture Note"
MatchKind = Literal["keyword", "first_line", "fallback", "generic"]


@dataclass(frozen=True)
class InferredCaptureTitle:
    title: str
    page_type: str | None = None
    provider: str = "rules"
    match_kind: MatchKind = "generic"


def rules_is_confident(result: InferredCaptureTitle) -> bool:
    """Only hard keyword patterns skip Ollama — not first-line compression."""
    return result.match_kind == "keyword"


def _collapse_words(text: str, *, max_words: int = _MAX_TITLE_WORDS) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text)
    if not words:
        return ""
    return " ".join(words[:max_words])


def _title_case_phrase(text: str) -> str:
    cleaned = _collapse_words(text)
    if not cleaned:
        return ""
    small = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "from", "with"}
    parts = cleaned.split()
    out: list[str] = []
    for index, word in enumerate(parts):
        low = word.lower()
        if index > 0 and low in small:
            out.append(low)
        elif word.isupper() and len(word) <= 4:
            out.append(word)
        else:
            out.append(low.capitalize())
    phrase = " ".join(out)
    return phrase[:_MAX_TITLE_CHARS].strip()


def _is_proposal_review_feedback_dump(low: str) -> bool:
    """Proposal reviewer feedback — not boss Q&A, artifact prep, or generic 'review my X'."""
    if any(phrase in low for phrase in ("grill me", "grill-me", "/grill-me")):
        return False
    if "boss" in low and any(token in low for token in ("skill", "meeting", "asks", "artifact", "present")):
        return False
    if "reviewer" in low and any(token in low for token in ("feedback", "comment", "proposal", "rfp")):
        return True
    if "proposal" in low and any(token in low for token in ("review", "feedback", "comment", "reviewer", "rfp")):
        return True
    if any(phrase in low for phrase in ("proposal review", "reviewer feedback", "review comments repository")):
        return True
    return False


def rules_infer_capture_title(dump: str, *, fallback: str = "", page_type: str = "synthesis") -> InferredCaptureTitle:
    """Fast keyword patterns — any dump can match, not session-specific."""
    text = (dump or "").strip()
    low = text.lower()

    if any(phrase in low for phrase in ("grill me", "grill-me", "/grill-me")) or (
        "boss" in low
        and any(token in low for token in ("skill", "grill"))
        and any(token in low for token in ("artifact", "present", "meeting", "comment", "question"))
    ):
        return InferredCaptureTitle(
            "Boss Grill Prep Skill",
            page_type="concept",
            provider="rules",
            match_kind="keyword",
        )
    if _is_proposal_review_feedback_dump(low):
        return InferredCaptureTitle(
            "Proposal Review Comments Repository",
            page_type=page_type,
            provider="rules",
            match_kind="keyword",
        )
    if "repository" in low and "knowledge" in low:
        return InferredCaptureTitle("Knowledge Repository", page_type=page_type, provider="rules", match_kind="keyword")
    if "competitor" in low or "incumbent" in low:
        return InferredCaptureTitle("Competitor Intel Note", page_type="competitor", provider="rules", match_kind="keyword")
    if any(token in low for token in ("agency", "customer", "command")):
        return InferredCaptureTitle("Agency Context Note", page_type="agency", provider="rules", match_kind="keyword")
    if any(token in low for token in ("pursuit", "opportunity", "capture plan", "idiq", "rfp")):
        return InferredCaptureTitle("Pursuit Capture Note", page_type="opportunity", provider="rules", match_kind="keyword")
    if any(token in low for token in ("framework", "playbook", "process")):
        return InferredCaptureTitle("Framework Note", page_type="concept", provider="rules", match_kind="keyword")

    for line in text.splitlines():
        clean = re.sub(r"^#+\s*", "", line.strip())
        clean = re.sub(r"^[-*]\s+", "", clean)
        clean = re.sub(r"^(i want to|we need to|need to|create a|build a)\s+", "", clean, flags=re.I)
        phrase = _title_case_phrase(clean)
        if len(phrase) >= 8:
            return InferredCaptureTitle(phrase, page_type=page_type, provider="rules", match_kind="first_line")

    if fallback:
        phrase = _title_case_phrase(fallback)
        if phrase:
            return InferredCaptureTitle(phrase, page_type=page_type, provider="rules", match_kind="fallback")

    return InferredCaptureTitle(_GENERIC_RULES_TITLE, page_type=page_type, provider="rules", match_kind="generic")


def _parse_title_json(raw: str) -> InferredCaptureTitle | None:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    if not title or len(title) < 4:
        return None
    if "-" in title and " " not in title and len(title) > 24:
        return None
    page_type = str(data.get("page_type") or "").strip().lower() or None
    return InferredCaptureTitle(title[:_MAX_TITLE_CHARS], page_type=page_type, provider="ollama", match_kind="keyword")


async def infer_capture_title(
    settings: Settings,
    dump: str,
    *,
    fallback: str = "",
    page_type: str = "synthesis",
    quick: bool = False,
) -> InferredCaptureTitle:
    """Keyword rules when obvious; otherwise Ollama (12s cap) for glanceable titles."""
    rules_result = rules_infer_capture_title(dump, fallback=fallback, page_type=page_type)
    if quick or rules_is_confident(rules_result):
        return rules_result
    if not settings.local_admin_model_enabled:
        return rules_result

    prompt_dump = (dump or fallback or "").strip()[:2500]
    if not prompt_dump:
        return rules_result

    messages = [
        {
            "role": "system",
            "content": (
                "Return ONLY JSON: {\"title\": \"...\", \"page_type\": \"...\"}. "
                "title = 3-7 words, Title Case, noun phrase a busy capture manager recognizes weeks later. "
                "Not a sentence. Not a filename slug. No dates. "
                "page_type = synthesis|concept|agency|competitor|opportunity — picks vault folder on approve."
            ),
        },
        {"role": "user", "content": f"Brain dump:\n{prompt_dump}"},
    ]
    try:
        result = await complete(
            settings,
            task_kind=LlmTaskKind.ADMIN,
            messages=messages,
            max_tokens=96,
            temperature=0.2,
            client=httpx.AsyncClient(timeout=12.0),
        )
        parsed = _parse_title_json(result.text)
        if parsed:
            merged_type = parsed.page_type or page_type
            return InferredCaptureTitle(parsed.title, page_type=merged_type, provider="ollama", match_kind="keyword")
    except (LlmRouterError, httpx.HTTPError, OSError):
        pass

    return rules_result