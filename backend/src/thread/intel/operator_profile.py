"""Operator profile — NAICS portfolio and other explicit operator config (not platform defaults)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thread.config import Settings

_MAX_NAICS_PORTFOLIO = 12


@dataclass(frozen=True)
class OperatorProfile:
    naics_portfolio: tuple[str, ...] = ()

    def has_naics_portfolio(self) -> bool:
        return bool(self.naics_portfolio)


def _profile_path(settings: Settings) -> Path:
    return settings.resolve(settings.thread_state_dir) / "operator_profile.json"


def _parse_naics_codes(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [c.strip() for c in re.split(r"[,;\s]+", raw) if c.strip()]
    elif isinstance(raw, list):
        items = [str(c).strip() for c in raw if str(c).strip()]
    else:
        return ()
    cleaned: list[str] = []
    for code in items:
        digits = re.sub(r"\D", "", code)
        if len(digits) >= 2:
            cleaned.append(digits[:6])
    return tuple(dict.fromkeys(cleaned))[:_MAX_NAICS_PORTFOLIO]


def load_operator_profile(settings: Settings) -> OperatorProfile:
    path = _profile_path(settings)
    if not path.is_file():
        return OperatorProfile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OperatorProfile()
    if not isinstance(data, dict):
        return OperatorProfile()
    return OperatorProfile(naics_portfolio=_parse_naics_codes(data.get("naics_portfolio")))


def save_operator_profile(settings: Settings, profile: OperatorProfile) -> OperatorProfile:
    path = _profile_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"naics_portfolio": list(profile.naics_portfolio)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return profile


def save_naics_portfolio_from_text(settings: Settings, raw: str) -> OperatorProfile:
    profile = OperatorProfile(naics_portfolio=_parse_naics_codes(raw))
    return save_operator_profile(settings, profile)