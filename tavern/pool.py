from __future__ import annotations

import asyncpg


def asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def create_tavern_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(asyncpg_dsn(database_url), min_size=1, max_size=5)


async def close_tavern_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()