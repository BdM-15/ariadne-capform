from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from thread.config import get_settings

_settings = get_settings()
engine = create_async_engine(
    _settings.database_url,
    pool_size=_settings.database_pool_size,
    pool_pre_ping=True,
    echo=_settings.database_echo,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from thread.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)