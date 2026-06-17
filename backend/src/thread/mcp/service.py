"""MCP catalog + one-shot tool invoke."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from thread.config import Settings
from thread.mcp.manifest import MCPManifest, discover_manifests
from thread.mcp.session import MCPError, MCPSession


class MCPService:
    def __init__(self, settings: Settings):
        root = settings.resolve(Path("tools/mcps"))
        self._manifests = discover_manifests(root)
        self._settings = settings

    def list_servers(self) -> list[dict[str, Any]]:
        env = self._build_env()
        out: list[dict[str, Any]] = []
        for manifest in sorted(self._manifests.values(), key=lambda m: m.name):
            missing = manifest.missing_env(env)
            out.append(
                {
                    "id": manifest.name,
                    "description": manifest.description,
                    "env_required": manifest.env_required,
                    "configured": not missing,
                    "missing_env": missing,
                    "vendored_from": manifest.vendored_from,
                }
            )
        return out

    def get_manifest(self, server_id: str) -> MCPManifest | None:
        return self._manifests.get(server_id)

    async def list_tools(self, server_id: str) -> list[dict[str, Any]]:
        manifest = self._require(server_id)
        session = MCPSession(manifest, tool_timeout=float(self._settings.mcp_tool_timeout_seconds))
        try:
            await session.start(self._build_env())
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in session.tools
            ]
        finally:
            await session.shutdown()

    async def invoke(
        self,
        server_id: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest = self._require(server_id)
        session = MCPSession(manifest, tool_timeout=float(self._settings.mcp_tool_timeout_seconds))
        try:
            await session.start(self._build_env())
            text = await session.call_tool(tool, arguments or {})
            return {
                "server": server_id,
                "tool": tool,
                "ok": True,
                "output": text,
            }
        except MCPError as exc:
            return {
                "server": server_id,
                "tool": tool,
                "ok": False,
                "error": str(exc),
            }
        finally:
            await session.shutdown()

    def _require(self, server_id: str) -> MCPManifest:
        manifest = self._manifests.get(server_id)
        if not manifest:
            raise KeyError(f"Unknown MCP server: {server_id}")
        return manifest

    def _build_env(self) -> dict[str, str]:
        return self._settings.mcp_subprocess_env(
            [key for m in self._manifests.values() for key in m.env_required]
        )