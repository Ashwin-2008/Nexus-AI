"""Embedding engine (provider adapters, batching, cache, validation)."""
from app.rag.embeddings.batcher import embed_batched
from app.rag.embeddings.cache import EmbeddingCache
from app.rag.embeddings.provider import RagEmbeddingProvider, get_rag_embedder
from app.rag.embeddings.registry import AVAILABLE_PROVIDERS, build_embedder, provider_metadata, provider_names
from app.rag.embeddings.validation import cosine_similarity, validate_vectors

__all__ = [
    "AVAILABLE_PROVIDERS",
    "EmbeddingCache",
    "RagEmbeddingProvider",
    "build_embedder",
    "cosine_similarity",
    "embed_batched",
    "get_rag_embedder",
    "provider_metadata",
    "provider_names",
    "validate_vectors",
]
