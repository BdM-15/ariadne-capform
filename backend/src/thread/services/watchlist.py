"""Operator watchlist — explicit potential on Pulse (Insights → Watch → Opportunity)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from thread.config import Settings


WATCHLIST_KINDS = frozenset({"recompete", "sam_notice"})


@dataclass(frozen=True)
class WatchlistItem:
    id: str
    kind: str
    watched_at: str
    source: str
    title: str
    agency: str = ""
    award_key: str | None = None
    notice_id: str | None = None
    naics_code: str | None = None
    solicitation_number: str | None = None
    notice_type: str | None = None
    end_date: str | None = None
    obligation: float | None = None
    months_to_end: int | None = None
    notes: str = ""

    def dedupe_key(self) -> str | None:
        if self.kind == "recompete" and self.award_key:
            return f"recompete:{self.award_key}"
        if self.kind == "sam_notice" and self.notice_id:
            return f"sam:{self.notice_id}"
        return None


def _watchlist_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "watchlist.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "entity"
    return base[:64]


def item_from_dict(raw: dict[str, Any]) -> WatchlistItem | None:
    kind = str(raw.get("kind") or "").strip()
    if kind not in WATCHLIST_KINDS:
        return None
    item_id = str(raw.get("id") or "").strip() or str(uuid.uuid4())
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    obligation_raw = raw.get("obligation")
    obligation = float(obligation_raw) if obligation_raw is not None else None
    months_raw = raw.get("months_to_end")
    months = int(months_raw) if months_raw is not None else None
    return WatchlistItem(
        id=item_id,
        kind=kind,
        watched_at=str(raw.get("watched_at") or _utc_now_iso()),
        source=str(raw.get("source") or "manual"),
        title=title,
        agency=str(raw.get("agency") or ""),
        award_key=(str(raw["award_key"]).strip() or None) if raw.get("award_key") else None,
        notice_id=(str(raw["notice_id"]).strip() or None) if raw.get("notice_id") else None,
        naics_code=(str(raw["naics_code"]).strip() or None) if raw.get("naics_code") else None,
        solicitation_number=(
            (str(raw["solicitation_number"]).strip() or None) if raw.get("solicitation_number") else None
        ),
        notice_type=(str(raw["notice_type"]).strip() or None) if raw.get("notice_type") else None,
        end_date=(str(raw["end_date"]).strip() or None) if raw.get("end_date") else None,
        obligation=obligation,
        months_to_end=months,
        notes=str(raw.get("notes") or ""),
    )


def _write_items(settings: Settings, items: list[WatchlistItem]) -> None:
    path = _watchlist_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": i.id,
            "kind": i.kind,
            "watched_at": i.watched_at,
            "source": i.source,
            "title": i.title,
            "agency": i.agency,
            "award_key": i.award_key,
            "notice_id": i.notice_id,
            "naics_code": i.naics_code,
            "solicitation_number": i.solicitation_number,
            "notice_type": i.notice_type,
            "end_date": i.end_date,
            "obligation": i.obligation,
            "months_to_end": i.months_to_end,
            "notes": i.notes,
        }
        for i in items
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_watchlist(settings: Settings) -> tuple[WatchlistItem, ...]:
    path = _watchlist_path(settings)
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, list):
        return ()
    parsed = [item_from_dict(item) for item in data if isinstance(item, dict)]
    items = [i for i in parsed if i is not None]
    return tuple(sorted(items, key=lambda i: i.watched_at, reverse=True))


def add_watchlist_item(settings: Settings, item: WatchlistItem) -> WatchlistItem:
    items = list(load_watchlist(settings))
    key = item.dedupe_key()
    if key:
        for existing in items:
            if existing.dedupe_key() == key:
                return existing
    items.insert(0, item)
    _write_items(settings, items)
    return item


def remove_watchlist_item(settings: Settings, item_id: str) -> bool:
    before = load_watchlist(settings)
    items = [i for i in before if i.id != item_id]
    if len(items) == len(before):
        return False
    _write_items(settings, list(items))
    return True


def new_recompete_watch_item(
    *,
    award_key: str,
    title: str,
    agency: str = "",
    naics_code: str | None = None,
    end_date: str | None = None,
    obligation: float | None = None,
    months_to_end: int | None = None,
    source: str = "insights_explore",
) -> WatchlistItem:
    return WatchlistItem(
        id=str(uuid.uuid4()),
        kind="recompete",
        watched_at=_utc_now_iso(),
        source=source,
        title=title.strip() or "Unknown recipient",
        agency=agency.strip(),
        award_key=award_key.strip(),
        naics_code=naics_code,
        end_date=end_date,
        obligation=obligation,
        months_to_end=months_to_end,
    )


def new_sam_watch_item(
    *,
    notice_id: str,
    title: str,
    agency: str = "",
    solicitation_number: str | None = None,
    notice_type: str | None = None,
    naics_code: str | None = None,
    source: str = "insights_explore",
) -> WatchlistItem:
    return WatchlistItem(
        id=str(uuid.uuid4()),
        kind="sam_notice",
        watched_at=_utc_now_iso(),
        source=source,
        title=title.strip() or f"SAM notice {notice_id[:12]}",
        agency=agency.strip(),
        notice_id=notice_id.strip(),
        solicitation_number=solicitation_number,
        notice_type=notice_type,
        naics_code=naics_code,
    )