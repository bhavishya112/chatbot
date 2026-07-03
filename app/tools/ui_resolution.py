from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from app.schemas import ToolObservation, ToolRequest


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.text_parts.append(text)


class UIResolutionTool:
    name = "ui_resolution"
    description = "Analyze only frontend-provided visible HTML and console errors for UI debugging."

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "visible_html": {"type": "string"},
                "console_errors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question", "visible_html", "console_errors"],
        }

    def execute(self, request: ToolRequest) -> ToolObservation:
        visible_html = str(request.arguments.get("visible_html") or "")
        question = str(request.arguments.get("question") or "")
        errors = request.arguments.get("console_errors") or []
        if not isinstance(errors, list):
            errors = []

        parser = _VisibleTextParser()
        parser.feed(visible_html[:120000])
        visible_text = " ".join(parser.text_parts)
        ids = sorted(set(re.findall(r'id=["\']([^"\']+)["\']', visible_html)))[:30]
        classes = sorted(set(re.findall(r'class=["\']([^"\']+)["\']', visible_html)))[:30]

        parts = [f"Question: {question}"]
        if visible_text:
            parts.append(f"Visible text: {visible_text[:4000]}")
        if ids:
            parts.append("Visible element ids: " + ", ".join(ids))
        if classes:
            parts.append("Visible classes: " + ", ".join(classes))
        if errors:
            parts.append("Console errors: " + " | ".join(str(error)[:1000] for error in errors[:10]))
        if len(parts) == 1:
            return ToolObservation(False, "No visible UI context was provided.")
        return ToolObservation(True, "\n".join(parts), {"source": "frontend_visible_context"})
