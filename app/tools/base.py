from __future__ import annotations

from typing import Any, Protocol

from app.schemas import ToolObservation, ToolRequest


class Tool(Protocol):
    name: str
    description: str

    def input_schema(self) -> dict[str, Any]:
        ...

    def execute(self, request: ToolRequest) -> ToolObservation:
        ...
