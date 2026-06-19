"""MinerU autostart lifecycle."""

from __future__ import annotations

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


def test_build_controller_when_enabled():
    settings = Settings(mineru_enabled=True, mineru_local_endpoint="http://localhost:9001")
    ctrl = build_controller_from_settings(settings)
    assert ctrl is not None
    assert ctrl.endpoint.port == 9001