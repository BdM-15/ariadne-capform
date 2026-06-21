"""MinerU path resolution."""

from __future__ import annotations

from thread.bootstrap.mineru_paths import mineru_install_hint, repo_root
from thread.config import Settings


def test_repo_root_exists():
    assert (repo_root() / "app.py").is_file()


def test_install_hint_points_at_script():
    hint = mineru_install_hint(Settings())
    assert "install-mineru.ps1" in hint