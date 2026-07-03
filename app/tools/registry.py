from __future__ import annotations

from app.schemas import ToolObservation, ToolRequest
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def execute(self, name: str, arguments: dict, session_id: str) -> ToolObservation:
        return self.get(name).execute(ToolRequest(name=name, arguments=arguments, session_id=session_id))

    def names(self) -> list[str]:
        return sorted(self._tools)
