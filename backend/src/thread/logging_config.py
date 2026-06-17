"""Central logging — keep startup quiet unless explicitly debugging."""

from __future__ import annotations

import logging


def configure_logging(*, level: str = "INFO", sql_echo: bool = False) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(message)s", force=True)

    # SQLAlchemy echoes every statement when engine.echo=True; keep logger quiet anyway.
    sql_level = logging.INFO if sql_echo else logging.WARNING
    for name in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(sql_level)

    # Uvicorn access lines on every HTTP request add noise during local dev.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)