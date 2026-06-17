---
name: mcp_federal_tools
description: Invoke 1102 federal-contracting MCP servers via pinned thread manifests.
metadata:
  capability: retrieve
  personas_primary: capture_manager
---

# mcp_federal_tools

Wraps USAspending, SAM.gov, eCFR, and related MCP tools from `tools/mcps/`.
All invocations logged to `mcp_invocations`; outputs are ExtractionBundle candidates.