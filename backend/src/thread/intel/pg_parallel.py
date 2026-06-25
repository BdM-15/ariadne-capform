"""Run independent intel PG queries concurrently — each on its own session."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.session import SessionLocal

T = TypeVar("T")

# Stay within connection pool headroom while overview fans out ~15 queries.
# Bind one semaphore per running loop so tests (new loop each) never reuse a
# semaphore bound to a closed loop.
_PG_SEMS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _pg_sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _PG_SEMS.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(8)
        _PG_SEMS[loop] = sem
    return sem


async def run_pg(coro_fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async with _pg_sem():
        async with SessionLocal() as session:
            return await coro_fn(session)


async def gather_pg(*coro_fns: Callable[[AsyncSession], Awaitable[T]]) -> tuple[T, ...]:
    return await asyncio.gather(*(run_pg(fn) for fn in coro_fns))