from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import Settings

SUPPORTED_EXTENSIONS = {".html", ".css", ".js", ".php", ".py"}


class SourceIngestor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def iter_files(self, root: Path | None = None) -> list[Path]:
        base = root or self.settings.project_root
        ignored = {".git", "__pycache__", "data"}
        return [
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
            and not any(part in ignored for part in path.parts)
        ]

    @staticmethod
    def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + size])
            start += max(1, size - overlap)
        return chunks

    def build_points(self, root: Path | None = None) -> list[dict]:
        points: list[dict] = []
        for path in self.iter_files(root):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for index, chunk in enumerate(self.chunk_text(text)):
                digest = hashlib.sha256(f"{path}:{index}:{chunk}".encode("utf-8")).hexdigest()
                points.append(
                    {
                        "id": digest,
                        "text": chunk,
                        "metadata": {"path": str(path), "source": path.name, "chunk": index},
                    }
                )
        return points

    def upsert(self, root: Path | None = None) -> int:
        points = self.build_points(root)
        if not points:
            return 0
        try:
            from qdrant_client import QdrantClient  # type: ignore
            from qdrant_client.models import PointStruct  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            embedder = SentenceTransformer(self.settings.embedding_model)
            vectors = embedder.encode([point["text"] for point in points]).tolist()
            client = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key or None)
            client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=[
                    PointStruct(
                        id=point["id"],
                        vector=vector,
                        payload={"text": point["text"], "metadata": point["metadata"]},
                    )
                    for point, vector in zip(points, vectors, strict=True)
                ],
            )
            return len(points)
        except Exception:
            return 0
