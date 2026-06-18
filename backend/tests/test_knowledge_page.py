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
    assert "vault-browser-layout" in res.text
    assert "vault-tree-panel" in res.text
    assert "vault-page-panel" in res.text
    assert "Shell stub" not in res.text
    assert "marked.min.js" in res.text
    assert "vault_markdown.js" in res.text


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