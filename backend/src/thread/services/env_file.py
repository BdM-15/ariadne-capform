"""Upsert key/value pairs in repo-root .env (Phase 12k MCP key editor)."""

from __future__ import annotations

import re
from pathlib import Path

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    """Set or replace one env var. Preserves comments and unrelated lines."""
    if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        raise ValueError(f"Invalid env key: {key!r}")

    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'{key}="{escaped}"' if re.search(r"\s|#|=", value) else f"{key}={value}"

    replaced = False
    out: list[str] = []
    for line in lines:
        m = _ENV_LINE.match(line.strip())
        if m and m.group(1) == key:
            out.append(new_line)
            replaced = True
        else:
            out.append(line)

    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(new_line)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")