"""Resolve MinerU install paths — isolated GPU venv (.venv-mineru)."""

from __future__ import annotations

import sys
from pathlib import Path

from thread.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[4]


def repo_root() -> Path:
    return _REPO_ROOT


def mineru_venv_python(settings: Settings) -> Path | None:
    override = (settings.mineru_python or "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None

    candidates = [
        settings.resolve(settings.mineru_venv_path) / "Scripts" / "python.exe",
        repo_root() / ".venv-mineru" / "Scripts" / "python.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def mineru_api_executable(settings: Settings) -> Path | None:
    py = mineru_venv_python(settings)
    if py is None:
        return None
    api = py.with_name("mineru-api.exe")
    if api.is_file():
        return api
    # Unix layout
    api_unix = py.parent / "mineru-api"
    return api_unix if api_unix.is_file() else None


def mineru_installed(settings: Settings) -> bool:
    py = mineru_venv_python(settings)
    if py is None:
        return False
    try:
        import subprocess

        result = subprocess.run(
            [str(py), "-c", "import mineru"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def mineru_install_hint(settings: Settings) -> str:
    root = repo_root()
    script = root / "scripts" / "install-mineru.ps1"
    return f"Run: powershell -File {script}"