"""Discover skills/*/SKILL.md frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillDescriptor:
    id: str
    description: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def discover_skills(skills_root: Path) -> dict[str, SkillDescriptor]:
    found: dict[str, SkillDescriptor] = {}
    if not skills_root.is_dir():
        return found
    for child in sorted(skills_root.iterdir()):
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        skill_id = meta.get("name") or child.name
        found[skill_id] = SkillDescriptor(
            id=skill_id,
            description=meta.get("description", ""),
            path=child,
            metadata={"capability": meta.get("metadata", "")},
        )
    return found