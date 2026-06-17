"""Hot recompete widget — Command Center (12f)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HOT_MONTHS_THRESHOLD = 6


@dataclass(frozen=True)
class HotSignalsWidget:
    hot_count: int
    radar_count: int
    intel_live: bool
    lens_summary: str
    preview: tuple[dict[str, Any], ...]
    needs_attention: bool


def filter_hot_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hot = [
        s
        for s in signals
        if s.get("months_to_end") is not None and int(s["months_to_end"]) <= HOT_MONTHS_THRESHOLD
    ]
    return sorted(hot, key=lambda s: int(s.get("months_to_end") or 99))


def build_hot_signals_widget(
    *,
    intel_signals: list[dict[str, Any]],
    intel_live: bool,
    lens_summary: str,
    preview_limit: int = 3,
) -> HotSignalsWidget:
    hot = filter_hot_signals(intel_signals)
    return HotSignalsWidget(
        hot_count=len(hot),
        radar_count=len(intel_signals),
        intel_live=intel_live,
        lens_summary=lens_summary,
        preview=tuple(hot[:preview_limit]),
        needs_attention=bool(intel_live and hot),
    )