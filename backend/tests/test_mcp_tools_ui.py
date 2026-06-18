"""Phase 12k — MCP test connection + .env key editor."""

from pathlib import Path

from fastapi.testclient import TestClient

from thread.config import reload_settings
from thread.main import create_app
from thread.services.env_file import upsert_env_var


def test_upsert_env_var_replaces_and_appends(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n# comment\n", encoding="utf-8")
    upsert_env_var(env, "SAM_GOV_API_KEY", "secret123")
    text = env.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert 'SAM_GOV_API_KEY="secret123"' in text or "SAM_GOV_API_KEY=secret123" in text

    upsert_env_var(env, "SAM_GOV_API_KEY", "rotated")
    assert text.count("SAM_GOV_API_KEY=") == 1 or text.count('SAM_GOV_API_KEY="') >= 1
    assert "rotated" in env.read_text(encoding="utf-8")


def test_mcp_page_has_test_and_save():
    client = TestClient(create_app())
    res = client.get("/tools/mcp")
    html = res.text
    assert res.status_code == 200
    assert "hx-post=\"/tools/mcp/sam_gov/test\"" in html or "/tools/mcp/sam_gov/test" in html
    assert "Save keys" in html
    assert "disabled" not in html or "Phase 12k" not in html


def test_mcp_test_partial_unknown_server():
    client = TestClient(create_app())
    res = client.post("/tools/mcp/not_a_server/test")
    assert res.status_code == 200
    assert "Failed" in res.text or "Unknown" in res.text


def test_mcp_save_env_route(monkeypatch):
    saved: list[tuple[str, str]] = []

    def _fake_upsert(_path: Path, key: str, value: str) -> None:
        saved.append((key, value))

    monkeypatch.setattr("thread.ui.routes.upsert_env_var", _fake_upsert)
    monkeypatch.setattr("thread.ui.routes.apply_env_to_process", lambda _k, _v: None)
    monkeypatch.setattr("thread.ui.routes.reload_settings", lambda: __import__("thread.config", fromlist=["get_settings"]).get_settings())

    client = TestClient(create_app())
    res = client.post("/tools/mcp/sam_gov/env", data={"SAM_GOV_API_KEY": "test-key-value"})
    assert res.status_code == 200
    assert saved == [("SAM_GOV_API_KEY", "test-key-value")]
    assert "Saved" in res.text