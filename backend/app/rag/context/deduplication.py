"""Context deduplication (identical and near-identical passages)."""
from __future__ import annotations

from app.rag.types import EvidenceChunk


def dedupe_evidence(items: list[EvidenceChunk], threshold: float = 0.92) -> list[EvidenceChunk]:
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    kept: list[EvidenceChunk] = []
    token_cache: list[set[str]] = []
    for item in items:
        key = item.chunk_id or item.citation_key
        if key in seen_ids:
            continue
        if item.content_hash and item.content_hash in seen_hashes:
            continue
        tokens = set((item.text or "").lower().split()[:400])
        duplicate = False
        for existing in token_cache:
            if not tokens or not existing:
                continue
            overlap = len(tokens & existing) / len(tokens | existing)
            if overlap >= threshold:
                duplicate = True
                break
        if duplicate:
            continue
        seen_ids.add(key)
        if item.content_hash:
            seen_hashes.add(item.content_hash)
        token_cache.append(tokens)
        kept.append(item)
    return kept
