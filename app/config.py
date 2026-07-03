from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    memory_dir: Path
    gemini_api_key: str
    gemini_model: str
    enable_google_search: bool
    enable_rag: bool
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    retrieval_top_k: int
    embedding_model: str
    memory_window: int

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parent.parent
        data_dir = root / "data"
        memory_dir = data_dir / "memory"
        return cls(
            project_root=root,
            data_dir=data_dir,
            memory_dir=memory_dir,
            gemini_api_key=os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LY64RSsueWDhAZymz66BFJngaGdpVBxmp4zg82Y5DKjA"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            enable_google_search=_bool_env("ENABLE_GOOGLE_SEARCH", True),
            enable_rag=_bool_env("ENABLE_RAG", False),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "webdoc"),
            retrieval_top_k=max(1, int(os.getenv("RETRIEVAL_TOP_K", "5"))),
            embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            memory_window=max(1, int(os.getenv("MEMORY_WINDOW", "5"))),
        )
