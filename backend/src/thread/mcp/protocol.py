"""MCP JSON-RPC helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPToolDescriptor:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


def parse_tool_descriptors(server_name: str, raw_tools: list[Any]) -> list[MCPToolDescriptor]:
    out: list[MCPToolDescriptor] = []
    for entry in raw_tools:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        schema = entry.get("inputSchema") or {"type": "object", "properties": {}}
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        out.append(
            MCPToolDescriptor(
                server=server_name,
                name=name,
                description=str(entry.get("description") or ""),
                input_schema=schema,
            )
        )
    return out


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, default=str)
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        else:
            parts.append(str(item))
    return "\n".join(p for p in parts if p)