"""Manifest loading for tools/mcps/<name>/thread_manifest.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPManifest:
    name: str
    description: str
    command: list[str]
    cwd: Path
    env_required: list[str] = field(default_factory=list)
    env_optional: list[str] = field(default_factory=list)
    vendored_from: str = ""

    def missing_env(self, env: dict[str, str] | None = None) -> list[str]:
        scope = env if env is not None else os.environ
        return [key for key in self.env_required if not scope.get(key)]


def load_manifest(manifest_path: Path) -> MCPManifest:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest {manifest_path}: must be object")
    name = str(raw.get("name") or "").strip()
    command = raw.get("command")
    if not name:
        raise ValueError(f"manifest {manifest_path}: missing name")
    if not isinstance(command, list) or not command:
        raise ValueError(f"manifest {manifest_path}: invalid command")
    return MCPManifest(
        name=name,
        description=str(raw.get("description") or ""),
        command=[str(c) for c in command],
        cwd=manifest_path.parent.resolve(),
        env_required=[str(e) for e in (raw.get("env_required") or [])],
        env_optional=[str(e) for e in (raw.get("env_optional") or [])],
        vendored_from=str(raw.get("vendored_from") or ""),
    )


def discover_manifests(mcps_root: Path) -> dict[str, MCPManifest]:
    found: dict[str, MCPManifest] = {}
    if not mcps_root.is_dir():
        return found
    for child in sorted(mcps_root.iterdir()):
        if not child.is_dir():
            continue
        for fname in ("thread_manifest.json", "theseus_manifest.json"):
            manifest_path = child / fname
            if manifest_path.is_file():
                manifest = load_manifest(manifest_path)
                found.setdefault(manifest.name, manifest)
                break
    return found