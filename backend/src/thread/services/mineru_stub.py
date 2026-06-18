"""MinerU document parse status — Phase 19 hook."""

from __future__ import annotations

from typing import Any

from thread.config import Settings


def mineru_ingest_status(settings: Settings) -> dict[str, Any]:
    """Theseus uses MinerU 3.3; Thread wires ingest when MINERU_ENABLED=true."""
    enabled = bool(settings.mineru_enabled)
    return {
        "product": "MinerU",
        "version": "3.3",
        "enabled": enabled,
        "status": "ready" if enabled else "stub",
        "role": "Solicitation / PDF → structured markdown → vault wiki (Phase 19).",
        "not_used": "Legacy third-party pdfparser forks — Thread uses MinerU only.",
        "theseus_note": "MinerU 3.3 already runs on Theseus; enable here when opp attach pipeline lands.",
    }