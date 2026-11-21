"""Context construction."""
from app.rag.context.builder import ContextBuilder, ContextBundle, ContextPassage
from app.rag.context.compression import compress_evidence, compress_extractive, split_sentences
from app.rag.context.deduplication import dedupe_evidence
from app.rag.context.source_grouping import group_by_document, group_by_source_type
from app.rag.context.token_budget import TokenBudget, estimate_tokens

__all__ = [
    "ContextBuilder",
    "ContextBundle",
    "ContextPassage",
    "TokenBudget",
    "compress_evidence",
    "compress_extractive",
    "dedupe_evidence",
    "estimate_tokens",
    "group_by_document",
    "group_by_source_type",
    "split_sentences",
]
