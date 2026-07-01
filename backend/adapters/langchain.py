"""LangChain Adapter — Use WalletPress tools in LangChain agents."""
from __future__ import annotations
from langchain.tools import BaseTool


class WalletPressTool(BaseTool):
    """LangChain tool wrapping a WalletPress MCP tool."""
    name: str = ""
    description: str = ""
    _fn = None

    def __init__(self, name: str, description: str, fn, **kwargs):
        super().__init__(name=name, description=description, **kwargs)
        self._fn = fn

    def _run(self, **kwargs) -> str:
        import json
        result = self._fn(**kwargs) if callable(self._fn) else {"error": "no fn"}
        return json.dumps(result, default=str)

    async def _arun(self, **kwargs) -> str:
        import json
        import asyncio
        if asyncio.iscoroutinefunction(self._fn):
            result = await self._fn(**kwargs)
        else:
            result = self._fn(**kwargs)
        return json.dumps(result, default=str)


def get_tools() -> list[BaseTool]:
    """Get all WalletPress MCP tools as LangChain tools."""
    from agent.mcp_server import mcp
    return [WalletPressTool(name=t.name, description=t.description or t.name, fn=t.fn)
            for t in mcp._tool_manager.list_tools()]
