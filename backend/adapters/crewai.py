"""CrewAI Adapter — Use WalletPress tools in CrewAI agents."""
from __future__ import annotations
from crewai.tools import BaseTool

class WalletPressCrewTool(BaseTool):
    name: str = ""
    description: str = ""
    _fn = None

    def __init__(self, name: str, description: str, fn):
        super().__init__(name=name, description=description)
        self._fn = fn

    def _run(self, **kwargs) -> str:
        import json
        result = self._fn(**kwargs) if callable(self._fn) else {"error": "no fn"}
        return json.dumps(result, default=str)


def get_tools() -> list[BaseTool]:
    from agent.mcp_server import mcp
    return [WalletPressCrewTool(name=t.name, description=t.description or t.name, fn=t.fn)
            for t in mcp._tool_manager.list_tools()]
