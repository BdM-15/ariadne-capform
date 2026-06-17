import asyncio

import pytest

from thread.db.session import SessionLocal
from thread.intel import pg_queries


def test_intel_queries_roundtrip():
    async def _run():
        async with SessionLocal() as session:
            stats = await pg_queries.get_intel_stats(session)
            assert "prime_award_count" in stats
            if not stats["prime_awards_ready"] or stats["prime_award_count"] == 0:
                return
            rows = await pg_queries.get_expiring_contracts(session, ["561210"], limit=5)
            assert isinstance(rows, list)

    asyncio.run(_run())