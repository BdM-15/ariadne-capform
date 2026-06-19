"""Graceful self-restart for dev server (Theseus-style re-exec)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logger = logging.getLogger(__name__)


def self_restart() -> None:
    """Re-exec current python process with same argv."""
    logger.warning("Re-execing process: %s %s", sys.executable, sys.argv)
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except Exception:
        logger.exception("Self-restart failed")
        os._exit(1)


def schedule_restart(delay: float = 0.75) -> None:
    """Schedule graceful restart after response is sent."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.info("Restart skipped during pytest")
        return

    loop = asyncio.get_event_loop()
    loop.call_later(delay, self_restart)