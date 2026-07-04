from __future__ import annotations

from typing import Any

from app.config import Settings
from app.schemas import ToolObservation, ToolRequest


class SearchTool:
    name = "search"
    description = "Search is disabled for fully local model mode unless a separate local/web search adapter is added."

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    def execute(self, request: ToolRequest) -> ToolObservation:
        query = str(request.arguments.get("query") or "").strip()
        if not query:
            return ToolObservation(False, "Search query is required.")
        if not self.settings.enable_google_search:
            return ToolObservation(False, "Search is disabled by ENABLE_GOOGLE_SEARCH.")
        return ToolObservation(
            False,
            "Search is not configured in local-only mode. Add a SearxNG/Tavily/SerpAPI adapter if web search is needed.",
        )
