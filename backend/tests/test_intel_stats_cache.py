"""Intel stats must not full-scan 64M-row tables on dashboard load."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from thread.config import Settings
from thread.intel import pg_queries


@pytest.mark.asyncio
async def test_intel_stats_uses_state_file_counts(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / ".thread"
    state_dir.mkdir()
    state = {
        "phase": "complete",
        "indexes_built": True,
        "prime_rows": 64_231_918,
        "sub_rows": 9_876_543,
    }
    (state_dir / "intel_migration_state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    settings = Settings(thread_state_dir=state_dir)
    monkeypatch.setattr("thread.intel.pg_queries.get_settings", lambda: settings)
    pg_queries.clear_intel_stats_cache()

    session = AsyncMock()

    def _scalar_result(value):
        result = MagicMock()
        result.scalar.return_value = value
        return result

    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(True),  # table_exists prime
            _scalar_result(True),  # table_exists subawards
            _scalar_result(True),  # table_exists naics_cache
            _scalar_result(42),  # naics_cache COUNT
        ]
    )

    stats = await pg_queries.get_intel_stats(session, force_refresh=True)
    assert stats["prime_award_count"] == 64_231_918
    assert stats["subaward_count"] == 9_876_543
    sql_calls = [str(call.args[0]) for call in session.execute.call_args_list]
    assert not any("COUNT(*)" in sql and "intel_usaspending" in sql for sql in sql_calls)


@pytest.mark.asyncio
async def test_intel_stats_cached_within_ttl(monkeypatch):
    pg_queries.clear_intel_stats_cache()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=False)))

    stats1 = await pg_queries.get_intel_stats(session, force_refresh=True)
    stats2 = await pg_queries.get_intel_stats(session)
    assert stats1 == stats2
    assert session.execute.await_count == 1