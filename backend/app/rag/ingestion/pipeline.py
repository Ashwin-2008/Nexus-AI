"""End-to-end ingestion pipeline.

Stages: storage load → validation → loader/parse → normalize → metadata →
dedupe/version detection → chunking → embedding → vector indexing → lexical
persistence (PostgreSQL chunk rows) → version record.

The pipeline deliberately does not own the durable job status transitions; the
caller (``app.services.ingestion_service.process_document_job``) marks the job
running/succeeded/failed so a conversation, API request or worker all share the
same status semantics.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.rag.chunking.parent_child import PARENT_STRATEGY
from app.rag.chunking.strategies import build_chunker
from app.rag.config import RagConfig
from app.rag.embeddings.provider import RagEmbeddingProvider
from app.rag.exceptions import (
    ChunkingError,
    EmbeddingUnavailableError,
    ParsingError,
    ValidationError,
)
from app.rag.ingestion.deduplication import find_duplicates
from app.rag.ingestion.metadata_extractor import enrich_metadata, file_hash
from app.rag.ingestion.validators import validate_document
from app.rag.ingestion.versioning import next_version, record_version
from app.rag.loaders import LoaderContext
from app.rag.parsing.parser import DocumentParser
from app.rag.types import ChunkRecord, IngestionOutcome
from app.services.vector_index import get_vector_index


class IngestionPipeline:
    def __init__(
        self,
        config: RagConfig | None = None,
        *,
        embedder: RagEmbeddingProvider | None = None,
        vector_index: Any | None = None,
        parser: DocumentParser | None = None,
    ) -> None:
        self.config = config or RagConfig.from_settings()
        self._embedder = embedder
        self._vector_index = vector_index
        self.parser = parser or DocumentParser()

    @property
    def embedder(self) -> RagEmbeddingProvider:
        if self._embedder is None:
            self._embedder = RagEmbeddingProvider(self.config)
        return self._embedder

    @property
    def vector_index(self) -> Any:
        if self._vector_index is None:
            self._vector_index = get_vector_index(dimensions=self.embedder.dimensions or None)
        return self._vector_index

    def run(self, db: Session, document: Document) -> IngestionOutcome:
        # Imported lazily: ingestion_service imports this module through the
        # ingestion package, so a module-level import would be circular.
        from app.services.ingestion_service import load_document_bytes

        timings: dict[str, int] = {}
        started = time.monotonic()

        stage = time.monotonic()
        data = load_document_bytes(document.storage_path, getattr(document, "storage_backend", None))
        timings["load_ms"] = _ms(stage)

        stage = time.monotonic()
        validate_document(document.filename, document.content_type, data, self.config)
        timings["validate_ms"] = _ms(stage)

        existing_meta = _metadata_from_json(document.doc_metadata)
        loader_ctx = LoaderContext(
            document_id=str(document.id),
            organization_id=str(document.organization_id),
            filename=document.filename,
            content_type=document.content_type,
            storage_path=document.storage_path,
            storage_backend=getattr(document, "storage_backend", "local"),
            max_bytes=self.config.max_document_bytes,
        )

        stage = time.monotonic()
        parsed = self.parser.parse(
            data,
            loader_ctx,
            extra_metadata={
                key: existing_meta[key]
                for key in ("source", "connector_type", "external_id", "uri", "connector_metadata", "access_roles")
                if key in existing_meta
            },
        )
        timings["parse_ms"] = _ms(stage)

        # Prefer the user/connector supplied title over the filename the parser
        # infers. It is used for citation labels and contextual embeddings.
        stored_title = existing_meta.get("document_title") or existing_meta.get("title")
        if stored_title:
            parsed.title = str(stored_title)

        digest = file_hash(data)
        metadata = enrich_metadata(
            parsed,
            file_digest=digest,
            filename=document.filename,
            content_type=document.content_type,
        )
        # Preserve connector provenance that the parser did not know about.
        for key in ("source", "connector_type", "external_id", "uri", "connector_metadata", "access_roles"):
            if key in existing_meta:
                metadata[key] = existing_meta[key]
        warnings = list(parsed.warnings)

        duplicates = find_duplicates(db, document.organization_id, digest, exclude_document_id=document.id)
        if duplicates:
            metadata["duplicate_of"] = duplicates
            warnings.append(
                f"identical content is already stored in {len(duplicates)} other document(s) of this organization"
            )

        version = next_version(db, document.id)
        access_scope = getattr(document, "access_scope", None) or "organization"

        stage = time.monotonic()
        chunker = build_chunker(self.config)
        chunks = chunker.chunk(
            parsed,
            document_id=str(document.id),
            organization_id=str(document.organization_id),
            document_version=version,
            access_scope=access_scope,
            source_id=str(document.source_id) if getattr(document, "source_id", None) else None,
        )
        if not chunks:
            raise ChunkingError(f"document '{document.filename}' produced no chunks")
        timings["chunk_ms"] = _ms(stage)

        indexable = [chunk for chunk in chunks if chunk.strategy != PARENT_STRATEGY]
        if not indexable:
            raise ChunkingError("chunking produced no indexable chunks")

        stage = time.monotonic()
        # Embed each chunk with its document title and section heading. The
        # stored/cited text stays the original passage, but the vector and the
        # lexical index both see the surrounding meaning instead of an isolated
        # fragment. This is what makes section-level paraphrases retrievable.
        embedding_texts = [_contextual_embedding_text(chunk, parsed) for chunk in indexable]
        try:
            vectors = self.embedder.embed_documents(embedding_texts)
        except EmbeddingUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingUnavailableError(f"embedding generation failed: {exc}") from exc
        if len(vectors) != len(indexable):
            raise EmbeddingUnavailableError(
                f"embedding count mismatch: {len(indexable)} chunks, {len(vectors)} vectors"
            )
        timings["embed_ms"] = _ms(stage)

        stage = time.monotonic()
        index = self.vector_index
        index.ensure_collection()
        # Remove stale points first so shrinking document versions cannot leave orphans.
        index.delete_document(str(document.organization_id), str(document.id))
        try:
            index.upsert_chunks([chunk.to_vector_payload() for chunk in indexable], vectors)
        except Exception:
            # Keep relational and vector state consistent: no stale lexical rows either.
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(synchronize_session=False)
            raise
        timings["index_ms"] = _ms(stage)

        stage = time.monotonic()
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(synchronize_session=False)
        embed_info = self.embedder.info()
        now = datetime.now(timezone.utc)
        indexable_ids = {chunk.chunk_id for chunk in indexable}
        for chunk in chunks:
            fields = chunk.to_db_fields()
            fields.update(
                {
                    "provenance": json.dumps(chunk.provenance, ensure_ascii=False),
                    "embedding_provider": embed_info["provider"] if chunk.chunk_id in indexable_ids else None,
                    "embedding_model": embed_info["model"] if chunk.chunk_id in indexable_ids else None,
                    "indexed_at": now if chunk.chunk_id in indexable_ids else None,
                }
            )
            db.add(DocumentChunk(**fields))
        timings["persist_ms"] = _ms(stage)

        metadata["processing"] = {
            "chunks": len(indexable),
            "parent_chunks": len(chunks) - len(indexable),
            "total_chunk_rows": len(chunks),
            "embeddings": len(vectors),
            "indexed": True,
            "index_backend": getattr(index, "name", "unknown"),
            "embedding_provider": embed_info["provider"],
            "embedding_model": embed_info["model"],
            "embedding_dimensions": self.embedder.dimensions,
            "chunk_strategy": chunker.strategy,
            "document_version": version,
            "content_hash": digest,
        }
        if warnings:
            metadata["ingestion_warnings"] = _dedupe(warnings)

        record_version(
            db,
            document,
            version=version,
            content_hash=digest,
            chunk_count=len(indexable),
            chunk_strategy=chunker.strategy,
            embedding_provider=embed_info["provider"],
            embedding_model=embed_info["model"],
            embedding_dimensions=self.embedder.dimensions or None,
            detail={"parent_chunks": len(chunks) - len(indexable), "warnings": warnings[:20]},
        )

        document.content_hash = digest
        document.version = version
        timings["total_ms"] = _ms(started)
        return IngestionOutcome(
            document_id=str(document.id),
            organization_id=str(document.organization_id),
            status="indexed",
            version=version,
            chunks=len(indexable),
            embeddings=len(vectors),
            content_hash=digest,
            chunk_strategy=chunker.strategy,
            embedding_provider=embed_info["provider"],
            embedding_model=embed_info["model"],
            index_backend=getattr(index, "name", "unknown"),
            indexed=True,
            duplicate_of=[item["document_id"] for item in duplicates],
            warnings=_dedupe(warnings),
            metadata=metadata,
            timings=timings,
        )


def _contextual_embedding_text(chunk, parsed) -> str:
    """Prefix a chunk with its document/section context for embedding."""
    title = str(parsed.title or "").strip()
    heading = str(chunk.section_heading or "").strip()
    prefix = "Document: " + title if title else ""
    if heading and heading.lower() != title.lower():
        prefix = (prefix + "\nSection: " + heading).strip()
    if not prefix:
        return chunk.text
    return f"{prefix}\n\n{chunk.text}"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _metadata_from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


__all__ = ["IngestionPipeline", "ValidationError", "ParsingError"]
