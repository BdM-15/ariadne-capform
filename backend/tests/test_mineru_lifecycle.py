"""MinerU autostart lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

from thread.bootstrap.mineru_lifecycle import (
    MineruController,
    MineruEndpoint,
    build_controller_from_settings,
    parse_mineru_endpoint,
)
from thread.config import Settings


def test_parse_mineru_endpoint():
    assert parse_mineru_endpoint("http://127.0.0.1:8888") == MineruEndpoint("127.0.0.1", 8888)


def test_build_controller_none_when_disabled():
    settings = Settings(mineru_enabled=False)
    assert build_controller_from_settings(settings) is None


def test_build_controller_none_when_autostart_off():
    settings = Settings(mineru_enabled=True, mineru_autostart=False)
    assert build_controller_from_settings(settings) is None


def test_build_controller_when_enabled():
    settings = Settings(
        mineru_enabled=True,
        mineru_autostart=True,
        mineru_local_endpoint="http://localhost:9001",
    )
    ctrl = build_controller_from_settings(settings)
    assert ctrl is not None
    assert ctrl.endpoint.port == 9001


def test_start_fails_fast_when_not_installed(monkeypatch):
    settings = Settings(mineru_enabled=True)
    monkeypatch.setattr(
        "thread.bootstrap.mineru_lifecycle.mineru_installed",
        lambda _s: False,
    )
    monkeypatch.setattr(
        "thread.bootstrap.mineru_lifecycle.mineru_api_executable",
        lambda _s: None,
    )
    ctrl = MineruController(settings=settings, endpoint=MineruEndpoint("127.0.0.1", 18888))
    assert ctrl.start(port_check=lambda _h, _p: False) is False
    assert "missing" in ctrl.last_error.lower() or "install" in ctrl.last_error.lower()


def test_start_reuses_existing_port():
    settings = Settings(mineru_enabled=True)
    ctrl = MineruController(settings=settings, endpoint=MineruEndpoint("127.0.0.1", 8888))
    assert ctrl.start(port_check=lambda _h, _p: True) is True
    assert ctrl.started_by_us is False


def test_start_non_blocking_skips_readiness_wait(monkeypatch):
    settings = Settings(mineru_enabled=True, mineru_spawn_fail_seconds=1.0)
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stderr = None
    monkeypatch.setattr(
        "thread.bootstrap.mineru_lifecycle.mineru_installed",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "thread.bootstrap.mineru_lifecycle.mineru_api_executable",
        lambda _s: "/fake/mineru-api.exe",
    )
    waited = {"called": False}

    def _should_not_wait(_ep):
        waited["called"] = True
        return False

    ctrl = MineruController(settings=settings, endpoint=MineruEndpoint("127.0.0.1", 18889))
    assert ctrl.start(
        wait_ready=False,
        port_check=lambda _h, _p: False,
        popen=lambda *a, **k: proc,
        wait=_should_not_wait,
    )
    assert waited["called"] is False
    assert ctrl.started_by_us is True