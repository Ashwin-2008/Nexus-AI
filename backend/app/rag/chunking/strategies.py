"""Chunking strategy factory."""
from __future__ import annotations

from app.rag.chunking.base import BaseChunker
from app.rag.chunking.parent_child import ParentChildChunker
from app.rag.chunking.recursive import RecursiveChunker
from app.rag.chunking.semantic import SemanticChunker
from app.rag.chunking.sentence import SentenceChunker
from app.rag.chunking.token import TokenChunker
from app.rag.config import RagConfig
from app.rag.exceptions import ConfigurationError

_STRATEGIES = {
    "recursive": lambda cfg: RecursiveChunker(cfg.chunk_size, cfg.chunk_overlap),
    "token": lambda cfg: TokenChunker(*TokenChunker.tokens_for(cfg.chunk_size, cfg.chunk_overlap)),
    "sentence": lambda cfg: SentenceChunker(cfg.chunk_size, cfg.chunk_overlap),
    "semantic": lambda cfg: SemanticChunker(cfg.chunk_size),
    "parent_child": lambda cfg: ParentChildChunker(
        parent_size=cfg.parent_chunk_size,
        parent_overlap=cfg.chunk_overlap,
        child_size=cfg.child_chunk_size,
        child_overlap=cfg.child_overlap,
    ),
}


def build_chunker(config: RagConfig, strategy: str | None = None) -> BaseChunker:
    name = (strategy or config.chunk_strategy or "recursive").strip().lower()
    factory = _STRATEGIES.get(name)
    if factory is None:
        raise ConfigurationError(f"Unknown chunking strategy '{name}' (valid: {sorted(_STRATEGIES)})")
    return factory(config)


def available_strategies() -> list[str]:
    return sorted(_STRATEGIES)
