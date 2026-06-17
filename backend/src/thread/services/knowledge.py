"""Vault browser — read-only knowledge/thread access."""

from __future__ import annotations

from pathlib import Path


class KnowledgeVaultError(Exception):
    pass


def _safe_path(vault_root: Path, rel: str) -> Path:
    clean = rel.replace("\\", "/").strip("/")
    target = (vault_root / clean).resolve()
    root = vault_root.resolve()
    if not str(target).startswith(str(root)):
        raise KnowledgeVaultError("Path escapes vault root")
    return target


def list_vault_entries(vault_root: Path, rel: str = "") -> dict:
    target = _safe_path(vault_root, rel) if rel else vault_root.resolve()
    if not target.exists():
        raise KnowledgeVaultError("Path not found")
    if not target.is_dir():
        raise KnowledgeVaultError("Not a directory")

    dirs: list[str] = []
    files: list[str] = []
    for child in sorted(target.iterdir()):
        name = child.name
        if name.startswith("."):
            continue
        if child.is_dir():
            dirs.append(name)
        elif child.suffix.lower() in (".md", ".json", ".jsonl"):
            files.append(name)
    return {"path": rel or "/", "dirs": dirs, "files": files}


def read_vault_page(vault_root: Path, rel: str) -> dict:
    if not rel:
        raise KnowledgeVaultError("path required")
    target = _safe_path(vault_root, rel)
    if not target.is_file():
        raise KnowledgeVaultError("File not found")
    if target.suffix.lower() not in (".md", ".json"):
        raise KnowledgeVaultError("Unsupported file type")
    return {"path": rel, "content": target.read_text(encoding="utf-8", errors="replace")}