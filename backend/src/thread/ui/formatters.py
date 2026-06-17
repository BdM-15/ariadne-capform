"""Jinja-friendly display formatters."""

from __future__ import annotations

from datetime import date, datetime


def format_money(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}" if abs(value) < 1_000_000 else f"${value / 1_000_000:.1f}M"


def format_date(value: str | date | datetime | None) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return value
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%b %d, %Y")


def urgency_label(months: int | None) -> str:
    if months is None:
        return "unknown horizon"
    if months <= 6:
        return f"{months} mo — hot"
    if months <= 12:
        return f"{months} mo — warm"
    return f"{months} mo"