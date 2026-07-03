from __future__ import annotations

from app.config import Settings


class QdrantRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def retrieve(self, query: str) -> list[dict]:
        try:
            from qdrant_client import QdrantClient  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            embedder = SentenceTransformer(self.settings.embedding_model)
            vector = embedder.encode(query).tolist()
            client = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key or None)
            results = client.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=vector,
                limit=self.settings.retrieval_top_k,
                with_payload=True,
            )
            return [
                {
                    "score": result.score,
                    "text": (result.payload or {}).get("text", ""),
                    "metadata": (result.payload or {}).get("metadata", {}),
                }
                for result in results
            ]
        except Exception:
            return []

    @staticmethod
    def format(chunks: list[dict]) -> str:
        formatted: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = chunk.get("metadata") or {}
            source = metadata.get("source") or metadata.get("path") or "unknown"
            text = str(chunk.get("text") or "").strip()
            if text:
                formatted.append(f"[{index}] {source}\n{text[:2000]}")
        return "\n\n".join(formatted)
