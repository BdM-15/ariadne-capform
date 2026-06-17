"""Command Center quick actions — 12h, action-first C&C strip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuickAction:
    id: str
    label: str
    href: str
    icon: str
    hint: str
    enabled: bool = True


def _hot_signal(signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    hot = [s for s in signals if s.get("months_to_end") is not None and s["months_to_end"] <= 6]
    if not hot:
        return None
    return min(hot, key=lambda s: s["months_to_end"])


def build_quick_actions(
    *,
    opportunities: list[dict[str, Any]],
    intel_signals: list[dict[str, Any]],
) -> tuple[QuickAction, ...]:
    research_href = "/pulse"
    research_hint = "Track a signal or create pursuit first"
    if opportunities:
        research_href = f"/opportunities/{opportunities[0]['id']}?tab=research"
        research_hint = f"Research tab · {opportunities[0]['name'][:48]}"

    actions: list[QuickAction] = [
        QuickAction(
            id="track",
            label="Track signal",
            href="/pulse#recompete-radar",
            icon="crosshair",
            hint="Morning briefing · recompete radar",
        ),
        QuickAction(
            id="research",
            label="Run research",
            href=research_href,
            icon="search",
            hint=research_hint,
            enabled=bool(opportunities) or False,
        ),
        QuickAction(
            id="insights",
            label="Data insights",
            href="/insights",
            icon="chart-no-axes-combined",
            hint="USAspending trends · saved lenses (Phase 17)",
        ),
        QuickAction(
            id="vault",
            label="Vault",
            href="/knowledge",
            icon="book-open",
            hint="Knowledge · domain_intel · entities",
        ),
        QuickAction(
            id="review",
            label="Review queue",
            href="/review",
            icon="list-checks",
            hint="Promote candidates to trusted",
        ),
    ]

    hottest = _hot_signal(intel_signals)
    if hottest:
        actions.insert(
            1,
            QuickAction(
                id="track-hot",
                label="Track hot signal",
                href="/pulse#recompete-radar",
                icon="flame",
                hint=f"{hottest.get('title', 'Recipient')[:40]} · ≤6 mo",
            ),
        )

    return tuple(actions)