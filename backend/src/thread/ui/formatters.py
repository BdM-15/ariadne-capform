"""Jinja-friendly display formatters."""

from __future__ import annotations

from datetime import date, datetime


def _compact_sign(value: float) -> tuple[str, float]:
    sign = "-" if value < 0 else ""
    return sign, abs(value)


def format_money(value: float | int | None) -> str:
    """Format a raw dollar obligation (not pre-scaled to millions)."""
    if value is None:
        return "—"
    sign, amount = _compact_sign(float(value))
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:.0f}K"
    return f"{sign}${amount:,.0f}"


def format_money_from_millions(value: float | int | None) -> str:
    """Format dollars when the input is already expressed in millions."""
    if value is None:
        return "—"
    sign, amount = _compact_sign(float(value))
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}T"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:.1f}B"
    if amount >= 1:
        return f"{sign}${amount:.1f}M"
    if amount > 0:
        return f"{sign}${amount * 1_000:.0f}K"
    return f"{sign}$0"


def format_count(value: int | float | None) -> str:
    if value is None:
        return "—"
    n = int(value)
    sign = "-" if n < 0 else ""
    amount = abs(n)
    if amount >= 1_000_000:
        return f"{sign}{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{sign}{amount / 1_000:.1f}k"
    return f"{sign}{n:,}"


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