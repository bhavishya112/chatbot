from __future__ import annotations

SYSTEM_PROMPT = """You are a production chatbot agent. Answer clearly and directly.
Use tools only when they are needed. Keep internal scratchpad reasoning private.
If UI state is needed and no UI context was provided, request UI context instead
of guessing from hidden browser state."""

REACT_TOOL_PROMPT = """Available tools:
- search: current or web-backed facts, when Google Search tooling is configured.
- ui_resolution: analyze frontend-provided visible HTML and console errors only.
- retrieval: project/document context from Qdrant collection webdoc.""" 


def build_prompt(query: str, memory: str, retrieval: str, ui_context: str) -> str:
    sections = [
        SYSTEM_PROMPT,
        REACT_TOOL_PROMPT,
        f"Recent conversation:\n{memory or '(none)'}",
        f"Retrieved context:\n{retrieval or '(none)'}",
        f"UI context:\n{ui_context or '(none)'}",
        f"User query:\n{query}",
    ]
    return "\n\n".join(sections)
