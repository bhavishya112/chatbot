from __future__ import annotations

from typing import Any

from app.config import Settings
from app.schemas import ToolObservation, ToolRequest


class SearchTool:
    name = "search"
    description = "Use Gemini Google Search/tooling for current web-backed answers when configured."

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
            return ToolObservation(False, "Google Search is disabled by ENABLE_GOOGLE_SEARCH.")
        if not self.settings.gemini_api_key:
            return ToolObservation(False, "Google Search is unavailable because GEMINI_API_KEY is not configured.")

        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            client = genai.Client(api_key=self.settings.gemini_api_key)
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=query,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
            )
            text = getattr(response, "text", "") or ""
            return ToolObservation(True, text.strip() or "Search completed with no text result.")
        except Exception as exc:
            return ToolObservation(False, f"Google Search is unavailable: {exc.__class__.__name__}.")
