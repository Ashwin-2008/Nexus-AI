from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Protocol


@dataclass
class ProcessingContext:
    document_id: str
    organization_id: str
    filename: str
    content_type: str
    storage_path: str
    storage_backend: str


@dataclass
class ExtractedContent:
    text: str
    metadata: dict[str, Any]


class FileExtractor(Protocol):
    def extract(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        ...


class TextNormalizer(Protocol):
    def normalize(self, content: ExtractedContent) -> ExtractedContent:
        ...


class Chunker(Protocol):
    def chunk(self, content: ExtractedContent) -> list[dict[str, Any]]:
        ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class VectorIndex(Protocol):
    def upsert(self, document_id: str, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        ...


class DefaultFileExtractor:
    def extract(self, data: bytes, ctx: ProcessingContext) -> ExtractedContent:
        # Best-effort text extraction placeholder; metadata extraction handled in ingestion service.
        text = ""
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        return ExtractedContent(text=text, metadata={"filename": ctx.filename, "content_type": ctx.content_type})


class DefaultTextNormalizer:
    def normalize(self, content: ExtractedContent) -> ExtractedContent:
        text = (content.text or "").replace("\r\n", "\n").strip()
        return ExtractedContent(text=text, metadata=dict(content.metadata))


class DefaultChunker:
    def chunk(self, content: ExtractedContent) -> list[dict[str, Any]]:
        # Placeholder chunking: single chunk when text exists. Real chunking to be implemented with indexing.
        if not content.text:
            return []
        return [{"index": 0, "text": content.text[:20000], "metadata": content.metadata}]


class NoopEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        # Interface placeholder; embeddings not generated in this milestone.
        return []


class NoopVectorIndex:
    def upsert(self, document_id: str, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        # Interface placeholder; Qdrant indexing not performed in this milestone.
        return None


def build_default_pipeline() -> dict[str, Any]:
    return {
        "extractor": DefaultFileExtractor(),
        "normalizer": DefaultTextNormalizer(),
        "chunker": DefaultChunker(),
        "embedder": NoopEmbeddingProvider(),
        "index": NoopVectorIndex(),
    }
