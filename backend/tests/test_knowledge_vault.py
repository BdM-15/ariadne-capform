from pathlib import Path

import pytest

from thread.services.knowledge import KnowledgeVaultError, list_vault_entries, read_vault_page


def test_list_vault_root(tmp_path: Path):
    (tmp_path / "global").mkdir()
    (tmp_path / "index.md").write_text("# vault", encoding="utf-8")
    data = list_vault_entries(tmp_path, "")
    assert "global" in data["dirs"]
    assert "index.md" in data["files"]


def test_path_traversal_blocked(tmp_path: Path):
    with pytest.raises(KnowledgeVaultError, match="escapes"):
        list_vault_entries(tmp_path, "../outside")


def test_read_markdown_page(tmp_path: Path):
    page = tmp_path / "notes.md"
    page.write_text("hello", encoding="utf-8")
    data = read_vault_page(tmp_path, "notes.md")
    assert data["content"] == "hello"