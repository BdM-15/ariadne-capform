"""Context builders for Tools lane pages (MCP Servers, Agent Skills)."""

from __future__ import annotations

from typing import Any

from thread.config import Settings
from thread.mcp.service import MCPService
from thread.skills.registry import discover_skills
from thread.ui.mcp_guides import guide_for_server
from thread.ui.skill_forms import skill_is_wired


def build_mcp_tools_context(settings: Settings) -> dict[str, Any]:
    service = MCPService(settings)
    servers: list[dict[str, Any]] = []
    for row in service.list_servers():
        manifest = service.get_manifest(row["id"])
        guide = guide_for_server(row["id"])
        missing = set(row.get("missing_env") or [])
        env_fields: list[dict[str, Any]] = []
        if manifest:
            for key in manifest.env_required:
                env_fields.append({"name": key, "required": True, "set": key not in missing})
            for key in manifest.env_optional:
                env_fields.append({"name": key, "required": False, "set": key not in missing})
        servers.append(
            {
                **row,
                "command": " ".join(manifest.command) if manifest else "",
                "vendored_from": manifest.vendored_from if manifest else "",
                "env_fields": env_fields,
                "guide": guide,
            }
        )
    ready = sum(1 for s in servers if s["configured"])
    return {
        "servers": servers,
        "ready_count": ready,
        "total_count": len(servers),
    }


def build_skills_tools_context(settings: Settings) -> dict[str, Any]:
    skills_root = settings.resolve(settings.skills_root)
    skills = discover_skills(skills_root)
    items = []
    for s in sorted(skills.values(), key=lambda x: x.id):
        try:
            rel = s.path.relative_to(settings.repo_root)
            path = str(rel).replace("\\", "/")
        except ValueError:
            path = str(s.path)
        items.append(
            {
                "id": s.id,
                "description": s.description,
                "path": path,
                "wired": skill_is_wired(s.id),
            }
        )
    return {"skills": items, "skills_root": str(skills_root)}