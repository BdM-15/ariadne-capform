"""Saved insight lenses — named facet presets for radar + Data Insights (12f seed)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings


@dataclass(frozen=True)
class SavedLens:
    id: str
    name: str
    naics_codes: tuple[str, ...]
    agency: str | None = None
    incumbent: str | None = None
    description: str = ""


# Operator seed lenses — Phase 17 persists/edits; not NAICS-only single code.
_BUILTIN_LENSES: tuple[SavedLens, ...] = (
    SavedLens(
        id="facilities-recompete",
        name="Facilities recompete",
        naics_codes=("561210", "561720"),
        description="Facilities support + remediation — primary capture lane",
    ),
    SavedLens(
        id="it-professional",
        name="IT professional services",
        naics_codes=("541512", "541519", "518210"),
        description="Systems integration, IT consulting, hosting",
    ),
)


def _lenses_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "saved_lenses.json"


def _lens_from_dict(raw: dict[str, Any]) -> SavedLens | None:
    lens_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or lens_id).strip()
    codes = raw.get("naics_codes") or raw.get("naics") or []
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    naics = tuple(str(c).strip() for c in codes if str(c).strip())
    if not lens_id or not naics:
        return None
    return SavedLens(
        id=lens_id,
        name=name,
        naics_codes=naics,
        agency=(str(raw["agency"]).strip() or None) if raw.get("agency") else None,
        incumbent=(str(raw["incumbent"]).strip() or None) if raw.get("incumbent") else None,
        description=str(raw.get("description") or ""),
    )


def load_saved_lenses(settings: Settings) -> tuple[SavedLens, ...]:
    path = _lenses_path(settings)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _BUILTIN_LENSES
        if isinstance(data, list):
            parsed = [_lens_from_dict(item) for item in data if isinstance(item, dict)]
            lenses = tuple(l for l in parsed if l is not None)
            if lenses:
                return lenses
    return _BUILTIN_LENSES


def naics_codes_for_radar(settings: Settings) -> list[str]:
    lenses = load_saved_lenses(settings)
    seen: set[str] = set()
    codes: list[str] = []
    for lens in lenses:
        for code in lens.naics_codes:
            if code not in seen:
                seen.add(code)
                codes.append(code)
    if codes:
        return codes
    return [settings.default_naics]


def radar_lens_summary(settings: Settings) -> str:
    lenses = load_saved_lenses(settings)
    if not lenses:
        return settings.default_naics
    if len(lenses) == 1:
        return lenses[0].name
    return f"{len(lenses)} saved lenses"