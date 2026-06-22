"""Ollama admin polish for vault candidates — diff preview, accept to save only."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from thread.config import Settings
from thread.llm.router import CompletionResult, LlmRouterError, LlmTaskKind, complete
from thread.services.incubator_capture import is_incubator_path
from thread.services.vault_write import (
    VaultWriteError,
    load_candidate_note,
    save_candidate_note,
)

Completer = Callable[..., Awaitable[CompletionResult]]


class CandidatePolishError(Exception):
    pass


@dataclass(frozen=True)
class PolishedCandidate:
    name: str
    page_type: str
    body: str
    related: tuple[str, ...]


@dataclass(frozen=True)
class CandidatePolishResult:
    candidate_path: str
    before: PolishedCandidate
    after: PolishedCandidate
    provider: str
    model: str | None = None
    raw_response: str | None = None


@dataclass(frozen=True)
class PolishDiffLine:
    field: str
    before: str
    after: str
    changed: bool


def _loaded_to_polished(loaded: dict[str, Any]) -> PolishedCandidate:
    return PolishedCandidate(
        name=str(loaded.get("name") or ""),
        page_type=str(loaded.get("page_type") or "synthesis"),
        body=str(loaded.get("body") or ""),
        related=tuple(loaded.get("related") or ()),
    )


def _normalize_related(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for raw in values:
        token = raw.strip().strip("-").strip()
        if token.startswith("[[") and token.endswith("]]"):
            token = token[2:-2].strip()
        if token and token not in seen:
            seen.append(token)
    if "capture-llm-wiki" not in seen:
        seen.append("capture-llm-wiki")
    return tuple(seen)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


_TYPO_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bameetting\b", re.I), "a meeting"),
    (re.compile(r"\bkonweldge\b", re.I), "knowledge"),
    (re.compile(r"\bkonwledge\b", re.I), "knowledge"),
    (re.compile(r"\bcapabilitiy\b", re.I), "capability"),
    (re.compile(r"\brecieve\b", re.I), "receive"),
    (re.compile(r"\bseperate\b", re.I), "separate"),
)


def _rules_fix_common_typos(text: str) -> str:
    cleaned = text
    for pattern, replacement in _TYPO_FIXES:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def rules_polish_candidate(loaded: dict[str, Any]) -> PolishedCandidate:
    """Deterministic admin normalize when Ollama is off or unreachable."""
    body = _rules_fix_common_typos(_collapse_blank_lines(str(loaded.get("body") or "")))
    if (
        body
        and not body.lstrip().startswith(">")
        and "## Document —" not in body[:240]
        and "## Intent" not in body[:240]
    ):
        body = f"> [!note] Candidate draft\n\n{body}"
    return PolishedCandidate(
        name=_rules_fix_common_typos(str(loaded.get("name") or "").strip()),
        page_type=str(loaded.get("page_type") or "synthesis"),
        body=body,
        related=_normalize_related(loaded.get("related") or ()),
    )


def _parse_ingest_polish_json(raw: str) -> PolishedCandidate:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CandidatePolishError("Ingest polish returned non-JSON output") from exc
    if not isinstance(data, dict):
        raise CandidatePolishError("Ingest polish JSON must be an object")
    return PolishedCandidate(
        name=str(data.get("name") or "").strip(),
        page_type="synthesis",
        body=_collapse_blank_lines(str(data.get("body") or "")),
        related=(),
    )


def build_ingest_polish_prompt(loaded: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "name": loaded.get("name"),
        "body": loaded.get("body"),
    }
    return [
        {
            "role": "system",
            "content": (
                "Return ONLY JSON: {\"name\": \"...\", \"body\": \"...\"}. "
                "Fix typos, grammar, and spacing in name and body. "
                "Keep all facts, names, and intent — do not invent content or change meaning. "
                "Light cleanup only: spelling, punctuation, sentence breaks. "
                "Do not add callouts or restructure beyond fixing broken prose."
            ),
        },
        {"role": "user", "content": f"Clean this brain dump for vault ingest:\n{json.dumps(payload, indent=2)}"},
    ]


async def ingest_polish_candidate(
    settings: Settings,
    loaded: dict[str, Any],
    *,
    completer: Completer | None = None,
    timeout_sec: float = 20.0,
) -> tuple[PolishedCandidate, str]:
    """FAB ingest — typo/grammar cleanup at capture time; full polish stays in Capture Studio."""
    before = _loaded_to_polished(loaded)
    if settings.local_admin_model_enabled:
        try:
            run = completer or complete
            result = await run(
                settings,
                task_kind=LlmTaskKind.ADMIN,
                messages=build_ingest_polish_prompt(loaded),
                max_tokens=1024,
                temperature=0.1,
                client=httpx.AsyncClient(timeout=timeout_sec),
            )
            parsed = _parse_ingest_polish_json(result.text)
            after = PolishedCandidate(
                name=parsed.name or before.name,
                page_type=before.page_type,
                body=parsed.body or before.body,
                related=before.related,
            )
            provider = getattr(result.provider, "value", str(result.provider))
            return after, f"{provider}-ingest"
        except (LlmRouterError, CandidatePolishError, httpx.HTTPError, OSError):
            pass

    return rules_polish_candidate(loaded), "rules"


def _parse_polish_json(raw: str) -> PolishedCandidate:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CandidatePolishError("Polish model returned non-JSON output") from exc
    if not isinstance(data, dict):
        raise CandidatePolishError("Polish model JSON must be an object")
    return PolishedCandidate(
        name=str(data.get("name") or "").strip(),
        page_type=str(data.get("page_type") or "synthesis").strip() or "synthesis",
        body=_collapse_blank_lines(str(data.get("body") or "")),
        related=_normalize_related(data.get("related") or []),
    )


def build_incubator_polish_prompt(loaded: dict[str, Any]) -> list[dict[str, str]]:
    schema = (
        "Return ONLY JSON with keys: name, page_type, body, related.\n"
        "- body: keep ## Intent, ## Extract, ## Source sections when present\n"
        "- Refine intent/extract prose only — never embed full document parse\n"
        "- page_type: hint for future publish routing (synthesis|concept|agency|competitor|opportunity)\n"
        "- related: wikilink stems (no brackets), include capture-llm-wiki\n"
        "- maturity stays seed; do not add publish/approve language"
    )
    user = json.dumps(
        {
            "name": loaded.get("name"),
            "page_type": loaded.get("page_type"),
            "body": loaded.get("body"),
            "related": loaded.get("related"),
            "intent": loaded.get("intent"),
            "capture_kind": loaded.get("capture_kind"),
        },
        indent=2,
    )
    return [
        {
            "role": "system",
            "content": "You polish incubator seed notes before develop/publish. " + schema,
        },
        {"role": "user", "content": f"Polish this incubator seed:\n{user}"},
    ]


def build_polish_prompt(loaded: dict[str, Any]) -> list[dict[str, str]]:
    schema = (
        "Return ONLY JSON with keys: name, page_type, body, related.\n"
        "- page_type: synthesis|concept|agency|competitor|opportunity\n"
        "- body: Obsidian markdown; use > [!note] callouts when helpful\n"
        "- related: array of wikilink stems (no brackets), include capture-llm-wiki\n"
        "- Do not change factual claims; normalize structure and wikilinks only\n"
        "- trust stays candidate; never invent trusted paths"
    )
    user = json.dumps(
        {
            "name": loaded.get("name"),
            "page_type": loaded.get("page_type"),
            "body": loaded.get("body"),
            "related": loaded.get("related"),
            "citations": loaded.get("citations"),
        },
        indent=2,
    )
    return [
        {
            "role": "system",
            "content": "You are a vault admin assistant for Karpathy llm-wiki ingest. " + schema,
        },
        {"role": "user", "content": f"Polish this candidate draft:\n{user}"},
    ]


def build_polish_diff(before: PolishedCandidate, after: PolishedCandidate) -> tuple[PolishDiffLine, ...]:
    lines: list[PolishDiffLine] = []
    for field in ("name", "page_type", "body"):
        b = getattr(before, field)
        a = getattr(after, field)
        lines.append(
            PolishDiffLine(
                field=field,
                before=b,
                after=a,
                changed=b != a,
            )
        )
    b_rel = ", ".join(before.related)
    a_rel = ", ".join(after.related)
    lines.append(
        PolishDiffLine(
            field="related",
            before=b_rel,
            after=a_rel,
            changed=before.related != after.related,
        )
    )
    return tuple(lines)


async def polish_candidate_note(
    settings: Settings,
    candidate_rel: str,
    *,
    completer: Completer | None = None,
) -> CandidatePolishResult:
    """Run admin polish — preview only until accept."""
    loaded = load_candidate_note(settings, candidate_rel)
    before = _loaded_to_polished(loaded)

    incubator = is_incubator_path(candidate_rel)
    if settings.local_admin_model_enabled:
        try:
            messages = (
                build_incubator_polish_prompt(loaded)
                if incubator
                else build_polish_prompt(loaded)
            )
            run = completer or complete
            result = await run(
                settings,
                task_kind=LlmTaskKind.ADMIN,
                messages=messages,
                max_tokens=min(settings.llm_max_output_tokens, 2048),
            )
            after = _parse_polish_json(result.text)
            if not after.name:
                after = PolishedCandidate(
                    name=before.name,
                    page_type=after.page_type,
                    body=after.body,
                    related=after.related,
                )
            provider = getattr(result.provider, "value", str(result.provider))
            return CandidatePolishResult(
                candidate_path=candidate_rel,
                before=before,
                after=after,
                provider=provider,
                model=result.model,
                raw_response=result.text,
            )
        except (LlmRouterError, CandidatePolishError):
            pass

    after = rules_polish_candidate(loaded)
    return CandidatePolishResult(
        candidate_path=candidate_rel,
        before=before,
        after=after,
        provider="rules",
        model=None,
        raw_response=None,
    )


def apply_polished_candidate(
    settings: Settings,
    candidate_rel: str,
    polished: PolishedCandidate,
) -> None:
    save_candidate_note(
        settings,
        candidate_rel,
        name=polished.name,
        body=polished.body,
        page_type=polished.page_type,
        related=list(polished.related),
    )