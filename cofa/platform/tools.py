"""The agents' only way into client systems: MCP tool calls, each one traced."""
from __future__ import annotations

import json
from contextlib import AsyncExitStack

from mcp import Client

from cofa.platform.trace import Tracer, mask


class ToolBelt:
    def __init__(self, servers: dict, tracer: Tracer, actor: str):
        self.servers, self.tracer, self.actor = servers, tracer, actor
        self.clients: dict[str, Client] = {}
        self.calls = 0

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        for name, srv in self.servers.items():
            self.clients[name] = await self._stack.enter_async_context(Client(srv))
        return self

    async def __aexit__(self, *exc):
        await self._stack.__aexit__(*exc)

    async def call(self, server: str, tool: str, **args) -> dict:
        shown = {k: (mask(v) if "iban" in k else v) for k, v in args.items() if k not in ("lines", "body")}
        with self.tracer.span(f"mcp.{server}.{tool}", args=shown):
            self.calls += 1
            res = await self.clients[server].call_tool(tool, args)
            text = res.content[0].text if res.content else "{}"
            out = json.loads(text)
            if getattr(res, "is_error", False) or getattr(res, "isError", False):
                raise RuntimeError(f"{server}.{tool} failed: {text[:300]}")
            return out
