"""Startup warmup — Ollama VRAM load, MCP/skill catalog caches."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from fastapi import FastAPI

from thread.config import Settings
from thread.llm.router import ollama_model_available, probe_ollama, warm_ollama_model
from thread.mcp.service import MCPService
from thread.services.mineru_client import mineru_base_url, probe_mineru_health
from thread.skills.registry import discover_skills


@dataclass
class WarmupReport:
    enabled: bool = True
    skipped_reason: str | None = None
    ollama_reachable: bool = False
    model: str = ""
    model_available: bool = False
    model_warmed: bool = False
    model_warm_seconds: float | None = None
    mcp_server_count: int = 0
    skill_count: int = 0
    mineru_enabled: bool = False
    mineru_reachable: bool = False
    mineru_endpoint: str = ""
    notes: list[str] = field(default_factory=list)


async def run_startup_warmup(app: FastAPI, settings: Settings) -> WarmupReport:
    report = WarmupReport()
    if not settings.enable_startup_warmup:
        report.enabled = False
        report.skipped_reason = "enable_startup_warmup=false"
        return report

    mcp = MCPService(settings)
    app.state.mcp_service = mcp
    report.mcp_server_count = len(mcp.list_servers())

    skills = discover_skills(settings.resolve(settings.skills_root))
    app.state.skill_catalog = skills
    report.skill_count = len(skills)

    report.mineru_enabled = bool(settings.mineru_enabled)
    report.mineru_endpoint = mineru_base_url(settings)
    if report.mineru_enabled:
        report.mineru_reachable = probe_mineru_health(settings)
        if not report.mineru_reachable:
            report.notes.append(
                f"MinerU enabled but unreachable at {report.mineru_endpoint} — capture uses mineru_error fallback"
            )

    if not settings.local_admin_model_enabled:
        report.notes.append("local_admin_model_enabled=false — Ollama warm skipped")
        return report

    report.ollama_reachable = await probe_ollama(settings)
    if not report.ollama_reachable:
        report.notes.append("Ollama unreachable — start Ollama or check OLLAMA_HOST")
        return report

    report.model = settings.local_daily_model
    report.model_available = await ollama_model_available(settings, report.model)
    if not report.model_available:
        report.notes.append(f"Model missing — run: ollama pull {report.model}")
        return report

    started = time.perf_counter()
    try:
        report.model_warmed = await warm_ollama_model(settings)
        report.model_warm_seconds = round(time.perf_counter() - started, 2)
    except Exception as exc:
        report.notes.append(f"Ollama warm failed: {exc}")

    return report


def log_warmup_report(report: WarmupReport) -> None:
    if not report.enabled:
        print(f"[thread] warmup skipped ({report.skipped_reason})")
        return

    parts = [f"mcp={report.mcp_server_count}", f"skills={report.skill_count}"]
    if report.mineru_enabled:
        parts.append(
            f"mineru={'ready' if report.mineru_reachable else 'unreachable'}"
            + (f"@{report.mineru_endpoint.replace('http://', '')}" if report.mineru_endpoint else "")
        )
    else:
        parts.append("mineru=off")

    if report.ollama_reachable:
        parts.append("ollama=ok")
        if report.model_warmed:
            parts.append(f"model={report.model} loaded {report.model_warm_seconds}s")
        elif report.model_available:
            parts.append(f"model={report.model} present warm-failed")
        else:
            parts.append(f"model={report.model} missing")
    else:
        parts.append("ollama=offline")

    print(f"[thread] warmup: {', '.join(parts)}")
    for note in report.notes:
        print(f"[thread] warmup note: {note}")