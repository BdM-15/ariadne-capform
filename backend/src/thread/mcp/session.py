"""MCP stdio session — spawn, handshake, tool call."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

from thread.mcp.manifest import MCPManifest
from thread.mcp.protocol import MCPToolDescriptor, extract_text_content, parse_tool_descriptors

logger = logging.getLogger(__name__)

_PROTOCOL = "2025-06-18"


class MCPError(Exception):
    pass


class MCPSession:
    def __init__(self, manifest: MCPManifest, *, handshake_timeout: float = 30, tool_timeout: float = 60):
        self.manifest = manifest
        self._handshake_timeout = handshake_timeout
        self._tool_timeout = tool_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._tools: list[MCPToolDescriptor] = []
        self._closed = False

    async def start(self, env_extra: dict[str, str] | None = None) -> None:
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        missing = self.manifest.missing_env(env)
        if missing:
            raise MCPError(f"MCP {self.manifest.name}: missing env {missing}")

        exe = shutil.which(self.manifest.command[0]) or self.manifest.command[0]
        argv = [exe, *self.manifest.command[1:]]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(self.manifest.cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"MCP {self.manifest.name}: executable not found ({exe})") from exc

        self._reader_task = asyncio.create_task(self._read_stdout())
        try:
            await asyncio.wait_for(self._handshake(), timeout=self._handshake_timeout)
            self._tools = await asyncio.wait_for(self._fetch_tools(), timeout=self._handshake_timeout)
        except Exception:
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    @property
    def tools(self) -> list[MCPToolDescriptor]:
        return list(self._tools)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            response = await asyncio.wait_for(
                self._request("tools/call", {"name": tool_name, "arguments": arguments}),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MCPError(f"MCP tool {tool_name} timed out") from exc
        result = response.get("result") or {}
        text = extract_text_content(result.get("content"))
        if result.get("isError"):
            raise MCPError(text or "tool error")
        return text

    async def _handshake(self) -> None:
        response = await self._request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "thread-mcp", "version": "0.1"},
            },
        )
        if response.get("error"):
            raise MCPError(str(response["error"]))
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _fetch_tools(self) -> list[MCPToolDescriptor]:
        response = await self._request("tools/list", {})
        if response.get("error"):
            raise MCPError(str(response["error"]))
        raw = (response.get("result") or {}).get("tools") or []
        return parse_tool_descriptors(self.manifest.name, raw)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        msg_id = self._next_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[msg_id] = future
        try:
            await self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
            return await future
        finally:
            self._pending.pop(msg_id, None)

    async def _send(self, message: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise MCPError("stdin unavailable")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                msg_id = message.get("id")
                if msg_id is None:
                    continue
                future = self._pending.get(int(msg_id))
                if future and not future.done():
                    future.set_result(message)
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(MCPError("stdout closed"))