"""Ariadne's Thread — single entry point.

Usage (from repo root):
    python app.py

Prerequisites are installed automatically into .venv on first run by scripts/bootstrap.ps1
(which this launcher invokes if the venv is missing).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_SRC = ROOT / "backend" / "src"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        print("[thread] ERROR: .env not found. Contact maintainer — .env should exist at repo root.")
        raise SystemExit(1)
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _ensure_venv() -> None:
    """Re-exec with root .venv Python if we're not already using it."""
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(ROOT / "app.py"), *sys.argv[1:]])

    bootstrap = ROOT / "scripts" / "bootstrap.ps1"
    if not VENV_PYTHON.exists() and bootstrap.exists():
        print("[thread] First run — creating .venv and installing dependencies...")
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(bootstrap)],
            cwd=str(ROOT),
            check=True,
        )
        if VENV_PYTHON.exists():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(ROOT / "app.py"), *sys.argv[1:]])


def _sync_frontend_env() -> None:
    api_url = os.environ.get("NEXT_PUBLIC_API_URL", "http://127.0.0.1:9622")
    port = os.environ.get("FRONTEND_PORT", "3000")
    frontend_env = ROOT / "frontend" / ".env.local"
    frontend_env.write_text(
        f"# Auto-synced from root .env by app.py — do not edit manually\n"
        f"NEXT_PUBLIC_API_URL={api_url}\n"
        f"PORT={port}\n",
        encoding="utf-8",
    )


def _docker_up(*, research: bool) -> bool:
    env = os.environ.copy()
    compose = ROOT / "docker-compose.yml"
    if research:
        cmd = ["docker", "compose", "-f", str(compose), "--profile", "research", "up", "-d", "--wait"]
    else:
        cmd = ["docker", "compose", "-f", str(compose), "up", "-d", "--wait", "postgres"]
    quiet = {"cwd": str(ROOT), "env": env, "check": False, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    loud = {"cwd": str(ROOT), "env": env, "check": False}
    try:
        result = subprocess.run(cmd, **quiet)
        if result.returncode != 0 and "--wait" in cmd:
            cmd = [c for c in cmd if c != "--wait"]
            result = subprocess.run(cmd, **quiet)
        if result.returncode != 0:
            print("[thread] docker compose failed:")
            subprocess.run(cmd, **loud)
        return result.returncode == 0
    except FileNotFoundError:
        print("[thread] Docker not found — ensure PostgreSQL is running at DATABASE_URL")
        return False


async def _preflight_postgres(settings) -> bool:
    """Wait for PG only when docker was skipped; dispose engine so uvicorn gets a fresh loop."""
    from thread.db.ready import wait_for_postgres
    from thread.db.session import engine

    ok = await wait_for_postgres(engine, settings)
    await engine.dispose()
    return ok


def _spawn_frontend(port: int) -> subprocess.Popen | None:
    frontend = ROOT / "frontend"
    node_modules = frontend / "node_modules"
    if not node_modules.exists():
        print("[thread] Installing frontend dependencies (first run)...")
        subprocess.run(["npm", "install"], cwd=str(frontend), shell=True, check=False)
    if not (frontend / "package.json").exists():
        return None
    try:
        return subprocess.Popen(
            ["npm", "run", "dev", "--", "-p", str(port)],
            cwd=str(frontend),
            shell=sys.platform == "win32",
        )
    except Exception as exc:
        print(f"[thread] Frontend spawn note: {exc}")
        return None


def main() -> int:
    _ensure_venv()
    _load_dotenv()

    if str(BACKEND_SRC) not in sys.path:
        sys.path.insert(0, str(BACKEND_SRC))

    parser = argparse.ArgumentParser(description="Ariadne's Thread launcher")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--no-research-providers", action="store_true")
    parser.add_argument(
        "--migrate-intel",
        action="store_true",
        help="Run DuckDB→PostgreSQL intel migration before starting API",
    )
    parser.add_argument(
        "--skip-intel-migrate",
        action="store_true",
        help="Disable INTEL_AUTO_MIGRATE_ON_START for this run",
    )
    args = parser.parse_args()

    import uvicorn

    from thread.bootstrap.vault import bootstrap_vault
    from thread.config import get_settings
    from thread.logging_config import configure_logging

    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(level=settings.log_level, sql_echo=settings.database_echo)

    from thread.orchestration.tracing import apply_langsmith_env

    apply_langsmith_env(settings)

    _sync_frontend_env()

    docker_ok = True
    if not args.skip_docker:
        docker_ok = _docker_up(research=settings.autostart_research_providers and not args.no_research_providers)
        if docker_ok:
            print(f"[thread] PostgreSQL ready 127.0.0.1:{settings.thread_postgres_port}")
        else:
            print(f"[thread] PostgreSQL target 127.0.0.1:{settings.thread_postgres_port}")

    if args.skip_docker or not docker_ok:
        if not asyncio.run(_preflight_postgres(settings)):
            print("[thread] ERROR: Cannot start without PostgreSQL. Check docker compose / DATABASE_URL.")
            return 1

    if settings.knowledge_bootstrap_on_start:
        result = bootstrap_vault(settings)
        if result.get("bootstrapped"):
            n = len(result.get("created") or [])
            print(f"[thread] Vault seed +{n} files → {result.get('path')}")

    from thread.intel.migration import get_migration_status, needs_migration, run_intel_migration

    if args.migrate_intel:
        print("[thread] Running intel migration in this window (prefer scripts/run-intel-migration.ps1)...")
        run_intel_migration(settings, force=False)
    elif needs_migration(settings) and not args.skip_intel_migrate:
        status = get_migration_status(settings)
        print(
            f"[thread] Intel migration {status.prime_migrated:,}/{status.prime_source_total:,} prime — "
            r"resume: .\scripts\run-intel-migration.ps1"
        )

    frontend_proc = None
    if settings.autostart_frontend and not args.api_only:
        print(
            "[thread] AUTOSTART_FRONTEND=true — legacy Next on :3000. "
            f"HTMX UI: http://127.0.0.1:{settings.port} — set AUTOSTART_FRONTEND=false to skip Node."
        )
        frontend_proc = _spawn_frontend(settings.frontend_port)

    from thread.main import create_app

    ui_url = (
        f"http://127.0.0.1:{settings.frontend_port} (legacy Next)"
        if frontend_proc
        else f"http://127.0.0.1:{settings.port}"
    )
    print(f"[thread] {settings.public_app_name} → {ui_url}")

    try:
        uvicorn.run(
            create_app(),
            host=settings.host if hasattr(settings, "host") else "127.0.0.1",
            port=settings.port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    finally:
        if frontend_proc:
            frontend_proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())