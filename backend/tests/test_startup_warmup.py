"""Startup warmup — catalog cache + Ollama warm hooks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from thread.bootstrap.warmup import log_warmup_report, run_startup_warmup
from thread.config import Settings


@pytest.mark.asyncio
async def test_warmup_skipped_when_disabled():
    app = FastAPI()
    settings = Settings(enable_startup_warmup=False)
    report = await run_startup_warmup(app, settings)
    assert report.enabled is False
    assert report.skipped_reason == "enable_startup_warmup=false"
    assert not hasattr(app.state, "mcp_service")


@pytest.mark.asyncio
async def test_warmup_caches_catalog_and_warms_ollama(tmp_path):
    app = FastAPI()
    settings = Settings(
        enable_startup_warmup=True,
        local_admin_model_enabled=True,
        local_daily_model="qwen3:8b",
        skills_root=tmp_path / "skills",
        knowledge_vault_path=tmp_path / "vault",
    )
    (settings.skills_root).mkdir(parents=True)

    with (
        patch("thread.bootstrap.warmup.MCPService") as mcp_cls,
        patch("thread.bootstrap.warmup.discover_skills", return_value={"a": object()}),
        patch("thread.bootstrap.warmup.probe_ollama", new_callable=AsyncMock, return_value=True),
        patch("thread.bootstrap.warmup.ollama_model_available", new_callable=AsyncMock, return_value=True),
        patch("thread.bootstrap.warmup.warm_ollama_model", new_callable=AsyncMock, return_value=True),
    ):
        mcp_cls.return_value.list_servers.return_value = [{"id": "sam_gov"}]
        report = await run_startup_warmup(app, settings)

    assert report.mcp_server_count == 1
    assert report.skill_count == 1
    assert report.ollama_reachable is True
    assert report.model_available is True
    assert report.model_warmed is True
    assert app.state.mcp_service is mcp_cls.return_value
    assert len(app.state.skill_catalog) == 1


def test_log_warmup_report_skipped(capsys):
    from thread.bootstrap.warmup import WarmupReport

    log_warmup_report(WarmupReport(enabled=False, skipped_reason="enable_startup_warmup=false"))
    assert "warmup skipped" in capsys.readouterr().out


def test_log_warmup_report_loaded(capsys):
    from thread.bootstrap.warmup import WarmupReport

    log_warmup_report(
        WarmupReport(
            mcp_server_count=8,
            skill_count=3,
            ollama_reachable=True,
            model="qwen3:8b",
            model_warmed=True,
            model_warm_seconds=4.2,
        )
    )
    out = capsys.readouterr().out
    assert "warmup:" in out
    assert "qwen3:8b loaded 4.2s" in out