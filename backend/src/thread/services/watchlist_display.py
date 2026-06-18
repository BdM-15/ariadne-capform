"""Watchlist widget — Pulse Potential panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.intel import pg_queries as intel_queries
from thread.services.watchlist import WatchlistItem, load_watchlist


@dataclass(frozen=True)
class WatchlistDisplayItem:
    item: WatchlistItem
    hot: bool


@dataclass(frozen=True)
class WatchlistWidget:
    items: tuple[WatchlistDisplayItem, ...]
    count: int
    hot_count: int


def watchlist_item_to_signal(item: WatchlistItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "award_key": item.award_key,
        "notice_id": item.notice_id,
        "title": item.title,
        "agency": item.agency,
        "end_date": item.end_date,
        "months_to_end": item.months_to_end,
        "obligation": item.obligation,
        "naics_code": item.naics_code,
        "solicitation_number": item.solicitation_number,
        "notice_type": item.notice_type,
        "watchlist_id": item.id,
        "opportunity_name": item.title,
    }


async def enrich_watchlist_items(
    session: AsyncSession,
    items: tuple[WatchlistItem, ...],
    *,
    intel_live: bool,
) -> list[WatchlistItem]:
    if not intel_live or not items:
        return list(items)

    recompete_keys = [i.award_key for i in items if i.kind == "recompete" and i.award_key]
    if not recompete_keys:
        return list(items)

    by_key = await intel_queries.get_awards_by_keys(session, recompete_keys)
    enriched: list[WatchlistItem] = []
    for item in items:
        if item.kind != "recompete" or not item.award_key:
            enriched.append(item)
            continue
        row = by_key.get(item.award_key)
        if not row:
            enriched.append(item)
            continue
        enriched.append(
            WatchlistItem(
                id=item.id,
                kind=item.kind,
                watched_at=item.watched_at,
                source=item.source,
                title=row.get("recipient") or item.title,
                agency=row.get("agency") or item.agency,
                award_key=item.award_key,
                notice_id=item.notice_id,
                naics_code=row.get("naics_code") or item.naics_code,
                solicitation_number=item.solicitation_number,
                notice_type=item.notice_type,
                end_date=row.get("end_date") or item.end_date,
                obligation=row.get("obligation") if row.get("obligation") is not None else item.obligation,
                months_to_end=row.get("months_to_end") if row.get("months_to_end") is not None else item.months_to_end,
                notes=item.notes,
            )
        )
    return enriched


async def build_watchlist_widget(session: AsyncSession, settings: Settings) -> WatchlistWidget:
    stats = await intel_queries.get_intel_stats(session)
    intel_live = bool(stats.get("prime_awards_ready") and stats.get("prime_award_count", 0) > 0)

    raw = load_watchlist(settings)
    enriched = await enrich_watchlist_items(session, raw, intel_live=intel_live)

    display: list[WatchlistDisplayItem] = []
    for item in enriched:
        hot = item.months_to_end is not None and item.months_to_end <= 6
        display.append(WatchlistDisplayItem(item=item, hot=hot))

    hot_count = sum(1 for d in display if d.hot)
    return WatchlistWidget(items=tuple(display), count=len(display), hot_count=hot_count)


def watchlist_signals(widget: WatchlistWidget) -> list[dict[str, Any]]:
    return [watchlist_item_to_signal(d.item) for d in widget.items]