from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UIContext:
    visible_html: str = ""
    console_errors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UIContext":
        if not isinstance(data, dict):
            return cls()
        errors = data.get("console_errors") or []
        if not isinstance(errors, list):
            errors = []
        return cls(
            visible_html=str(data.get("visible_html") or ""),
            console_errors=[str(item) for item in errors if str(item).strip()],
        )


@dataclass(frozen=True)
class AgentRequest:
    query: str
    ui_context: UIContext
    session_id: str
    stream: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentRequest":
        query = str(data.get("query") or "").strip()
        if not query:
            raise ValueError("query required")
        session_id = str(data.get("session_id") or "default").strip() or "default"
        return cls(
            query=query,
            ui_context=UIContext.from_dict(data.get("ui_context")),
            session_id=session_id,
            stream=bool(data.get("stream", True)),
        )


@dataclass(frozen=True)
class ToolRequest:
    name: str
    arguments: dict[str, Any]
    session_id: str


@dataclass(frozen=True)
class ToolObservation:
    ok: bool
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
