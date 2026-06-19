"""Phase 15 — Knowledge vault browser UI."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.main import create_app
from thread.services.knowledge_browser import build_vault_browser_context, vault_href


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_knowledge_page_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_vault_href_builds_deep_links():
    assert vault_href() == "/knowledge"
    assert vault_href(path="global/domain_intel") == "/knowledge?path=global/domain_intel"
    assert vault_href(page="entities/foo.md") == "/knowledge?page=entities/foo.md"


def test_build_vault_browser_context_with_page(tmp_path: Path):
    (tmp_path / "global").mkdir()
    (tmp_path / "global" / "readme.md").write_text("# Hello\n\nBody", encoding="utf-8")
    settings = Settings(knowledge_vault_path=str(tmp_path))
    ctx = build_vault_browser_context(settings, page="global/readme.md")
    assert ctx.vault_ready is True
    assert ctx.browse_path == "global"
    assert ctx.active_page == "global/readme.md"
    assert ctx.page_content == "# Hello\n\nBody"
    assert ctx.page_kind == "markdown"
    assert ctx.page_title == "Hello"


def test_knowledge_page_loads():
    client = TestClient(create_app())
    res = client.get("/knowledge")
    assert res.status_code == 200
    assert "knowledge-body" in res.text
    assert "knowledge-vault-ops-mount" in res.text
    assert "knowledge-capture-studio-mount" in res.text
    assert "vault-tree-collapse-btn" in res.text
    assert "vault-browser-layout" in res.text
    assert "vault-browser-layout" in res.text
    assert "vault-tree-panel" in res.text
    assert "vault-page-panel" in res.text
    assert "Shell stub" not in res.text
    assert "marked.min.js" in res.text
    assert "vault_markdown.js" in res.text
    assert "settings-tip-box" in res.text
    assert "guide-modal" in res.text
    assert "openGuideDialog('guide-knowledge')" in res.text
    assert "guide-vault-ops" in res.text


def test_knowledge_page_deep_link():
    client = TestClient(create_app())
    res = client.get("/knowledge?path=global")
    assert res.status_code == 200
    assert "global" in res.text


def test_knowledge_tree_partial():
    client = TestClient(create_app())
    res = client.get("/partials/knowledge/tree")
    assert res.status_code == 200
    assert "vault-entry-list" in res.text


def test_knowledge_page_partial_empty():
    client = TestClient(create_app())
    res = client.get("/partials/knowledge/page")
    assert res.status_code == 200
    assert "vault-page-empty" in res.text


def test_knowledge_ssr_page_panel_no_duplicate_tree(tmp_path: Path, monkeypatch):
    """Full page render must not embed browse tree inside vault-page-panel."""
    vault = tmp_path / "vault"
    (vault / "entities").mkdir(parents=True)
    (vault / "entities" / "note.md").write_text("# Note\n", encoding="utf-8")
    monkeypatch.setenv("KNOWLEDGE_VAULT_PATH", str(vault))
    from thread.config import get_settings

    get_settings.cache_clear()
    client = TestClient(create_app())
    res = client.get("/knowledge?page=entities/note.md")
    assert res.status_code == 200
    page_panel_start = res.text.index('id="vault-page-panel"')
    page_panel_chunk = res.text[page_panel_start : page_panel_start + 4000]
    assert "vault-tree-inner" not in page_panel_chunk
    assert "vault-page-inner" in page_panel_chunk
    get_settings.cache_clear()


def test_knowledge_vault_ops_partial():
    client = TestClient(create_app())
    res = client.get("/partials/knowledge/vault-ops")
    assert res.status_code == 200
    assert "knowledge-vault-ops" in res.text
    assert "Vault operations" in res.text
    assert "openGuideDialog('guide-vault-ops')" in res.text
    assert "settings-label-tip" in res.text
    assert 'title="Scan for broken wikilinks' in res.text


def test_knowledge_vault_lint_op(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    from thread.main import create_app
    from thread.config import get_settings

    get_settings.cache_clear()
    import os
    os.environ["KNOWLEDGE_VAULT_PATH"] = str(vault)
    client = TestClient(create_app())
    res = client.post(
        "/partials/knowledge/vault-op",
        data={"action": "lint", "apply": "false"},
    )
    assert res.status_code == 200
    assert "issue" in res.text.lower()
    get_settings.cache_clear()