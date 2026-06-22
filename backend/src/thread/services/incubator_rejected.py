"""Rejected incubator seeds — operator dismissals under generated-projections/rejected/."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thread.config import Settings
from thread.services.vault_write import _parse_frontmatter, _vault_root

REJECTED_PREFIX = "generated-projections/rejected/"


@dataclass(frozen=True)
class RejectedSeedItem:
    rel_path: str
    name: str
    capture_kind: str
    maturity: str
    is_test: bool
    modified_at: datetime | None


def list_rejected_seeds(settings: Settings, *, limit: int = 24) -> tuple[RejectedSeedItem, ...]:
    vault = _vault_root(settings)
    rejected_dir = vault / "generated-projections" / "rejected"
    if not rejected_dir.is_dir():
        return ()

    items: list[RejectedSeedItem] = []
    for path in sorted(rejected_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        rel = path.relative_to(vault).as_posix()
        meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
        name = meta.get("name") or path.stem
        capture_kind = meta.get("capture_kind", "")
        maturity = meta.get("maturity", "")
        is_test = "sandbox" in rel or meta.get("source", "").lower() == "test"
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        items.append(
            RejectedSeedItem(
                rel_path=rel,
                name=name,
                capture_kind=capture_kind,
                maturity=maturity,
                is_test=is_test,
                modified_at=mtime,
            )
        )
        if len(items) >= limit:
            break
    return tuple(items)