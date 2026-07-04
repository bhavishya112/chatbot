from __future__ import annotations

import logging
from collections.abc import Iterator

from app.config import Settings
from app.memory import JsonConversationMemory
from app.prompts import build_prompt
from app.retrieval import QdrantRetriever
from app.schemas import AgentRequest
from app.services.local_model import LocalModelService
from app.tools import SearchTool, ToolRegistry, UIResolutionTool


UI_KEYWORDS = ("ui", "screen", "button", "frontend", "page", "browser", "console", "dom", "layout", "error")
SEARCH_KEYWORDS = ("latest", "today", "current", "news", "search", "web", "recent")
logger = logging.getLogger(__name__)


class ProductionAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory = JsonConversationMemory(settings.memory_dir, settings.memory_window)
        self.retriever = QdrantRetriever(settings)
        self.model = LocalModelService(settings)
        self.tools = ToolRegistry()
        self.tools.register(SearchTool(settings))
        self.tools.register(UIResolutionTool())

    def stream(self, request: AgentRequest) -> Iterator[dict]:
        if self._needs_ui_context(request):
            yield {
                "event": "ui_context_request",
                "message": "The agent needs visible UI context to answer this.",
                "done": False,
            }
            yield {"event": "done", "finished": True}
            return

        answer = self._answer(request)
        for token in self._chunk(answer):
            yield {"event": "message", "token": token, "done": False}
        yield {"event": "message", "token": "", "done": True}
        yield {"event": "done", "finished": True}
        self.memory.save_turn(request.session_id, request.query, answer)

    def _answer(self, request: AgentRequest) -> str:
        memory_text = self.memory.format(request.session_id)
        retrieval_text = ""
        if self.settings.enable_rag:
            logger.info("RAG retrieval enabled; retrieving context from Qdrant")
            retrieval_text = QdrantRetriever.format(self.retriever.retrieve(request.query))
        else:
            logger.info("RAG retrieval skipped because ENABLE_RAG is false")
        ui_text = ""

        if request.ui_context.visible_html or request.ui_context.console_errors:
            ui_observation = self.tools.execute(
                "ui_resolution",
                {
                    "question": request.query,
                    "visible_html": request.ui_context.visible_html,
                    "console_errors": request.ui_context.console_errors,
                },
                request.session_id,
            )
            ui_text = ui_observation.content

        search_text = ""
        if self._needs_search(request.query):
            search = self.tools.execute("search", {"query": request.query}, request.session_id)
            if search.ok:
                search_text = f"Search result:\n{search.content}"

        prompt = build_prompt(
            query=request.query,
            memory=memory_text,
            retrieval="\n\n".join(part for part in [retrieval_text, search_text] if part),
            ui_context=ui_text,
        )
        model_answer = self.model.generate(prompt)
        if model_answer:
            return model_answer
        return self._fallback_answer(request, retrieval_text, search_text, ui_text)

    @staticmethod
    def _needs_search(query: str) -> bool:
        lowered = query.lower()
        return any(keyword in lowered for keyword in SEARCH_KEYWORDS)

    @staticmethod
    def _needs_ui_context(request: AgentRequest) -> bool:
        if request.ui_context.visible_html or request.ui_context.console_errors:
            return False
        lowered = request.query.lower()
        return any(keyword in lowered for keyword in UI_KEYWORDS)

    @staticmethod
    def _fallback_answer(request: AgentRequest, retrieval: str, search: str, ui: str) -> str:
        context_parts = [part for part in [ui, search, retrieval] if part]
        if context_parts:
            return "\n\n".join(context_parts)
        return (
            "I can help with that, but the local model is not reachable yet. "
            "Start Ollama and confirm LOCAL_MODEL_NAME is installed."
        )

    @staticmethod
    def _chunk(text: str, size: int = 80) -> Iterator[str]:
        for index in range(0, len(text), size):
            yield text[index : index + size]
