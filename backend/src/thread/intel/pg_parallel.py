"""Run independent intel PG queries concurrently — each on its own session."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from thread.db.session import SessionLocal

T = TypeVar("T")

# Stay within connection pool headroom while overview fans out ~15 queries.
_PG_SEM = asyncio.Semaphore(8)


async def run_pg(coro_fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async with _PG_SEM:
        async with SessionLocal() as session:
            return await coro_fn(session)


async def gather_pg(*coro_fns: Callable[[AsyncSession], Awaitable[T]]) -> tuple[T, ...]:
    return await asyncio.gather(*(run_pg(fn) for fn in coro_fns))