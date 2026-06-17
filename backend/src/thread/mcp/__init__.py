"""Vendored 1102 MCP adapters — manifest discovery + stdio invoke."""

from thread.mcp.manifest import MCPManifest, discover_manifests
from thread.mcp.service import MCPService

__all__ = ["MCPManifest", "MCPService", "discover_manifests"]