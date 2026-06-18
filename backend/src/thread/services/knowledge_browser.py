"""Vault browser context — read-only knowledge/thread UI (Phase 15)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thread.config import Settings
from thread.services.knowledge import KnowledgeVaultError, list_vault_entries, read_vault_page
from thread.services.knowledge_digest import _parse_frontmatter, _title_from_file


@dataclass(frozen=True)
class VaultBreadcrumb:
    label: str
    path: str


@dataclass(frozen=True)
class VaultBrowserContext:
    vault_ready: bool
    vault_path: str
    browse_path: str
    parent_path: str
    active_page: str | None
    dirs: tuple[str, ...]
    files: tuple[str, ...]
    page_content: str | None
    page_kind: str | None
    page_title: str | None
    breadcrumbs: tuple[VaultBreadcrumb, ...]
    error: str | None


def _vault_root(settings: Settings) -> Path:
    return settings.resolve(settings.knowledge_vault_path)


def _normalize_rel(rel: str) -> str:
    return rel.replace("\\", "/").strip("/")


def _parent_dir(rel: str) -> str:
    clean = _normalize_rel(rel)
    if not clean:
        return ""
    return clean.rsplit("/", 1)[0] if "/" in clean else ""


def build_breadcrumbs(browse_path: str) -> tuple[VaultBreadcrumb, ...]:
    clean = _normalize_rel(browse_path)
    crumbs: list[VaultBreadcrumb] = [VaultBreadcrumb(label="vault", path="")]
    if not clean:
        return tuple(crumbs)
    parts = clean.split("/")
    acc = ""
    for part in parts:
        acc = f"{acc}/{part}" if acc else part
        crumbs.append(VaultBreadcrumb(label=part, path=acc))
    return tuple(crumbs)


def _page_kind(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".json":
        return "json"
    return None


def _page_title(vault: Path, rel: str, content: str) -> str:
    return _title_from_file(vault / rel, content)


def build_vault_browser_context(
    settings: Settings,
    *,
    path: str = "",
    page: str = "",
) -> VaultBrowserContext:
    vault = _vault_root(settings)
    vault_ready = vault.is_dir()
    browse_path = _normalize_rel(path)
    active_page = _normalize_rel(page) or None

    if active_page and not browse_path:
        browse_path = _parent_dir(active_page)

    parent_path = _parent_dir(browse_path)

    if not vault_ready:
        return VaultBrowserContext(
            vault_ready=False,
            vault_path=str(vault),
            browse_path=browse_path,
            parent_path=parent_path,
            active_page=active_page,
            dirs=(),
            files=(),
            page_content=None,
            page_kind=None,
            page_title=None,
            breadcrumbs=build_breadcrumbs(browse_path),
            error="Knowledge vault not found — run app bootstrap or check knowledge/thread.",
        )

    dirs: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    listing_error: str | None = None
    try:
        listing = list_vault_entries(vault, browse_path)
        dirs = tuple(listing["dirs"])
        files = tuple(listing["files"])
    except KnowledgeVaultError as exc:
        listing_error = str(exc)
        if active_page:
            browse_path = _parent_dir(active_page)
            try:
                listing = list_vault_entries(vault, browse_path)
                dirs = tuple(listing["dirs"])
                files = tuple(listing["files"])
                listing_error = None
            except KnowledgeVaultError:
                browse_path = ""
                try:
                    listing = list_vault_entries(vault, "")
                    dirs = tuple(listing["dirs"])
                    files = tuple(listing["files"])
                    listing_error = None
                except KnowledgeVaultError as inner:
                    listing_error = str(inner)

    page_content: str | None = None
    page_kind: str | None = None
    page_title: str | None = None
    page_error: str | None = None

    if active_page:
        page_kind = _page_kind(active_page)
        if page_kind is None:
            page_error = "Unsupported file type — open .md or .json pages."
        else:
            try:
                data = read_vault_page(vault, active_page)
                page_content = data["content"]
                page_title = _page_title(vault, active_page, page_content)
            except KnowledgeVaultError as exc:
                page_error = str(exc)

    error = page_error or listing_error
    return VaultBrowserContext(
        vault_ready=True,
        vault_path=str(vault),
        browse_path=browse_path,
        parent_path=_parent_dir(browse_path),
        active_page=active_page,
        dirs=dirs,
        files=files,
        page_content=page_content,
        page_kind=page_kind,
        page_title=page_title,
        breadcrumbs=build_breadcrumbs(browse_path),
        error=error,
    )


def vault_href(*, path: str = "", page: str = "") -> str:
    """Build /knowledge deep link."""
    params: list[str] = []
    clean_path = _normalize_rel(path)
    clean_page = _normalize_rel(page)
    if clean_path:
        params.append(f"path={clean_path}")
    if clean_page:
        params.append(f"page={clean_page}")
    if not params:
        return "/knowledge"
    return f"/knowledge?{'&'.join(params)}"


def child_dir_href(browse_path: str, name: str) -> str:
    base = _normalize_rel(browse_path)
    child = f"{base}/{name}" if base else name
    return vault_href(path=child)


def child_file_href(browse_path: str, name: str) -> str:
    base = _normalize_rel(browse_path)
    rel = f"{base}/{name}" if base else name
    return vault_href(path=base, page=rel)