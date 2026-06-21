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


def _port_in_use(host: str, port: int) -> bool:
    import socket

    bind_host = "127.0.0.1" if host in {"0.0.0.0", "localhost"} else host
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((bind_host, port))
        return False
    except OSError:
        return True
    finally:
        sock.close()


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
    parser.add_argument(
        "--legacy-frontend",
        action="store_true",
        help="Also spawn archived Next.js in frontend/ (dev archaeology only — not the command center)",
    )
    args = parser.parse_args()

    import uvicorn

    from thread.bootstrap.vault import bootstrap_vault
    from thread.config import get_settings
    from thread.logging_config import configure_logging

    if args.no_warmup:
        os.environ["ENABLE_STARTUP_WARMUP"] = "false"

    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(level=settings.log_level, sql_echo=settings.database_echo)

    from thread.orchestration.tracing import apply_langsmith_env

    apply_langsmith_env(settings)

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
    if args.legacy_frontend and not args.api_only:
        print(
            "[thread] --legacy-frontend: spawning archived Next.js. "
            "Command center is HTMX on :9622 (python app.py without this flag)."
        )
        frontend_proc = _spawn_frontend(settings.frontend_port)
    elif settings.autostart_frontend and not args.api_only:
        print(
            "[thread] AUTOSTART_FRONTEND is deprecated and ignored. "
            "Use python app.py --legacy-frontend only if you need the archived Next shell."
        )

    from thread.bootstrap.mineru_lifecycle import build_controller_from_settings
    from thread.main import create_app

    mineru_controller = build_controller_from_settings(settings)
    if settings.mineru_enabled:
        from thread.bootstrap.mineru_paths import mineru_install_hint, mineru_installed
        from thread.services.mineru_client import probe_mineru_health

        ep_url = settings.mineru_local_endpoint
        if mineru_controller is not None:
            ep = mineru_controller.endpoint
            if mineru_controller.start():
                mode = "spawned" if mineru_controller.started_by_us else "already running"
                print(
                    f"[thread] MinerU: {mode} @ {ep.base_url} "
                    f"({settings.mineru_backend}, {settings.mineru_device_mode})"
                )
            else:
                detail = mineru_controller.last_error or "startup failed"
                print(f"[thread] MinerU: not ready @ {ep.base_url} — {detail}")
                print("[thread] MinerU: capture will stage files; parse retries when API is up")
        elif not mineru_installed(settings):
            print(f"[thread] MinerU: not installed — {mineru_install_hint(settings)}")
        elif probe_mineru_health(settings):
            print(f"[thread] MinerU: ready @ {ep_url} (external process)")
        elif not settings.mineru_autostart:
            print(f"[thread] MinerU: enabled, autostart off — expect API @ {ep_url}")
        else:
            print("[thread] MinerU: enabled — waiting for parser service")
    else:
        print("[thread] MinerU: off (MINERU_ENABLED=false)")

    bind_host = settings.host if hasattr(settings, "host") else "127.0.0.1"
    if _port_in_use(bind_host, settings.port):
        print(
            f"[thread] ERROR: Port {settings.port} already in use — "
            f"server likely already running at http://127.0.0.1:{settings.port}"
        )
        print("[thread] Stop the other python app.py window, then restart. Do not run two instances.")
        return 1

    print(f"[thread] Command center → http://127.0.0.1:{settings.port}")
    if frontend_proc:
        print(f"[thread] Archived Next.js → http://127.0.0.1:{settings.frontend_port}")

    try:
        uvicorn.run(
            create_app(),
            host=bind_host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    finally:
        if mineru_controller is not None:
            mineru_controller.stop()
        if frontend_proc:
            frontend_proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())