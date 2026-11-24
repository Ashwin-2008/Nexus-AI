"""Qdrant vector index service.

Real vector operations against Qdrant with organization-scoped filtering.
Collection layout: one collection per deployment (configurable name), each
point payload carries organization_id so retrieval is always org-filtered.
"""
from __future__ import annotations

import logging
import math
from typing import Any
import uuid as uuid_mod

try:
    import math as _math
    from qdrant_client import QdrantClient
    from qdrant_client import models as qmodels
except ImportError:  # optional dependency in minimal local envs
    QdrantClient = None  # type: ignore[assignment]
    qmodels = None  # type: ignore[assignment]

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorIndexError(RuntimeError):
    pass


class QdrantVectorIndex:
    name = "qdrant"

    def __init__(self, dimensions: int | None = None) -> None:
        if QdrantClient is None:
            raise VectorIndexError(
                "qdrant-client is not installed. Install backend/requirements.txt or set "
                "VECTOR_INDEX_BACKEND=memory for offline development."
            )
        self.dimensions = dimensions or settings.embedding_dimensions or 256
        self.collection = settings.qdrant_collection or "nexus_chunks"
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            url = settings.qdrant_url
            api_key = settings.qdrant_api_key or None
            self._client = QdrantClient(url=url, api_key=api_key, timeout=15)
        return self._client

    # -- collection lifecycle -------------------------------------------------

    def ensure_collection(self) -> None:
        try:
            if self.client.collection_exists(self.collection):
                info = self.client.get_collection(self.collection)
                size = (info.config and info.config.params and info.config.params.vectors) or {}
                if isinstance(size, dict) and size.get("size") not in (None, self.dimensions):
                    raise VectorIndexError(
                        f"Qdrant collection '{self.collection}' exists with vector size "
                        f"{size.get('size')} but configured embedding dimensions are {self.dimensions}. "
                        "Recreate the collection or change EMBEDDING_DIMENSIONS."
                    )
                return
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(
                    size=self.dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            # Payload indexes make org-scoped filtering efficient.
            for field in ("organization_id", "document_id"):
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("payload index creation for %s failed: %s", field, e)
            logger.info("created qdrant collection %s (dim=%s)", self.collection, self.dimensions)
        except VectorIndexError:
            raise
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"failed to ensure qdrant collection: {e}") from e

    def collection_exists(self) -> bool:
        try:
            return self.client.collection_exists(self.collection)
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant collection check failed: {e}") from e

    def delete_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection)
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant collection delete failed: {e}") from e

    # -- point operations ------------------------------------------------------

    @staticmethod
    def _point_id(chunk_uuid: str) -> str:
        # Qdrant accepts UUID point ids; use the chunk's own UUID.
        try:
            return str(uuid_mod.UUID(chunk_uuid))
        except ValueError:
            # Deterministic UUID v5 fallback for non-UUID ids.
            return str(uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, chunk_uuid))

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert chunk vectors. Each chunk dict must include:
        chunk_id (str uuid), organization_id, document_id, text, index, metadata.
        Returns number of points upserted.
        """
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise VectorIndexError(
                f"chunk/vector count mismatch: {len(chunks)} chunks vs {len(embeddings)} vectors"
            )
        self.ensure_collection()
        points = []
        for chunk, vector in zip(chunks, embeddings):
            if len(vector) != self.dimensions:
                raise VectorIndexError(
                    f"vector dimension mismatch: expected {self.dimensions}, got {len(vector)}"
                )
            payload = {
                "organization_id": str(chunk["organization_id"]),
                "document_id": str(chunk["document_id"]),
                "chunk_id": str(chunk["chunk_id"]),
                "chunk_index": chunk.get("index", 0),
                "text": chunk.get("text", ""),
                "section_heading": chunk.get("section_heading"),
                "parent_chunk_id": chunk.get("parent_chunk_id"),
                "content_hash": chunk.get("content_hash"),
                "token_count": chunk.get("token_count"),
                "chunk_strategy": chunk.get("strategy"),
                "document_version": chunk.get("document_version", 1),
                "access_scope": chunk.get("access_scope") or "organization",
                "source_id": str(chunk["source_id"]) if chunk.get("source_id") else None,
                "metadata": {**(chunk.get("metadata") or {}), "provenance": chunk.get("provenance", [])},
            }
            points.append(
                qmodels.PointStruct(
                    id=self._point_id(str(chunk["chunk_id"])),
                    vector=vector,
                    payload=payload,
                )
            )
        try:
            # wait=True for read-your-writes consistency after indexing.
            operation_info = self.client.upsert(collection_name=self.collection, points=points, wait=True)
            if getattr(operation_info, "status", "") not in ("completed", None):
                raise VectorIndexError(f"qdrant upsert not completed: {operation_info}")
            return len(points)
        except VectorIndexError:
            raise
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant upsert failed: {e}") from e

    def search(
        self,
        vector: list[float],
        organization_id: str,
        top_k: int = 8,
        document_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        access_scopes: list[str] | None = None,
        document_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search scoped to one organization (never crosses orgs)."""
        if len(vector) != self.dimensions:
            raise VectorIndexError(
                f"query vector dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )
        must_filters: list[qmodels.FieldCondition] = [
            qmodels.FieldCondition(key="organization_id", match=qmodels.MatchValue(value=organization_id))
        ]
        if document_ids:
            must_filters.append(
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchAny(any=[str(d) for d in document_ids]),
                )
            )
        if source_ids:
            must_filters.append(
                qmodels.FieldCondition(
                    key="source_id",
                    match=qmodels.MatchAny(any=[str(s) for s in source_ids]),
                )
            )
        if document_version is not None:
            must_filters.append(
                qmodels.FieldCondition(
                    key="document_version", match=qmodels.MatchValue(value=int(document_version))
                )
            )
        should_filters = None
        if access_scopes:
            # Missing access_scope (legacy points) is treated as organization scope.
            try:
                empty_scope = qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="access_scope"))
            except Exception:  # pragma: no cover - older client versions
                empty_scope = None
            conditions = [
                qmodels.FieldCondition(
                    key="access_scope", match=qmodels.MatchAny(any=[str(scope) for scope in access_scopes])
                )
            ]
            if empty_scope is not None:
                conditions.append(empty_scope)
            should_filters = conditions
        query_filter = qmodels.Filter(must=must_filters, should=should_filters)
        try:
            if hasattr(self.client, "query_points"):
                # qdrant-client >= 1.10 (search() was removed in 1.16).
                response = self.client.query_points(
                    collection_name=self.collection,
                    query=vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
                hits = getattr(response, "points", response)
            else:  # pragma: no cover - qdrant-client < 1.10
                hits = self.client.search(
                    collection_name=self.collection,
                    query_vector=vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant search failed: {e}") from e
        return [
            {
                "chunk_id": h.payload.get("chunk_id"),
                "document_id": h.payload.get("document_id"),
                "organization_id": h.payload.get("organization_id"),
                "chunk_index": h.payload.get("chunk_index"),
                "text": h.payload.get("text", ""),
                "metadata": h.payload.get("metadata") or {},
                "section_heading": h.payload.get("section_heading"),
                "parent_chunk_id": h.payload.get("parent_chunk_id"),
                "content_hash": h.payload.get("content_hash"),
                "document_version": h.payload.get("document_version"),
                "access_scope": h.payload.get("access_scope"),
                "source_id": h.payload.get("source_id"),
                "score": h.score,
            }
            for h in hits
        ]

    def delete_document(self, organization_id: str, document_id: str) -> int:
        """Delete all points belonging to a document. Returns count deleted."""
        must_filters = [
            qmodels.FieldCondition(key="organization_id", match=qmodels.MatchValue(value=organization_id)),
            qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=str(document_id))),
        ]
        try:
            deleted = self.count_for_document(organization_id, document_id)
            self.client.delete(
                collection_name=self.collection,
                points_selector=qmodels.FilterSelector(filter=qmodels.Filter(must=must_filters)),
                wait=True,
            )
            return int(deleted)
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant delete failed: {e}") from e

    def count_for_document(self, organization_id: str, document_id: str) -> int:
        must_filters = [
            qmodels.FieldCondition(key="organization_id", match=qmodels.MatchValue(value=organization_id)),
            qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=str(document_id))),
        ]
        try:
            result = self.client.count(
                collection_name=self.collection,
                count_filter=qmodels.Filter(must=must_filters),
                exact=True,
            )
            return result.count
        except Exception as e:  # noqa: BLE001
            raise VectorIndexError(f"qdrant count failed: {e}") from e

    def health(self) -> dict[str, Any]:
        try:
            ok = self.client.collection_exists(self.collection)
            info = self.client.get_collection(self.collection) if ok else None
            return {
                "healthy": True,
                "collection": self.collection,
                "exists": ok,
                "points": int(getattr(info, "points_count", 0) or 0) if info else 0,
            }
        except Exception as e:  # noqa: BLE001
            return {"healthy": False, "error": str(e)}


def get_vector_index(dimensions: int | None = None) -> QdrantVectorIndex:
    backend = (settings.vector_index_backend or "qdrant").strip().lower()
    if backend == "memory":
        # Explicitly configured ephemeral backend (tests / offline dev).
        # Real cosine-similarity math, but data is lost on restart. A single
        # process-wide instance is required: ingestion and query code construct
        # the index independently and must see the same points.
        logger.warning("VECTOR_INDEX_BACKEND=memory: in-memory vector index in use; data is ephemeral.")
        key = int(dimensions or settings.embedding_dimensions or 256)
        index = _MEMORY_INDEXES.get(key)
        if index is None:
            index = InMemoryVectorIndex(dimensions=key)
            _MEMORY_INDEXES[key] = index
        return index
    return QdrantVectorIndex(dimensions=dimensions)


_MEMORY_INDEXES: dict[int, "InMemoryVectorIndex"] = {}


class InMemoryVectorIndex:
    """Process-local vector index implementing the same contract as Qdrant.

    Real cosine similarity and real org/document filtering — but storage is
    ephemeral (per process). Intended for unit tests and offline development.
    NOT for production deployment.
    """

    name = "memory"

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.embedding_dimensions or 256
        # point_id -> (vector, payload)
        self._points: dict[str, tuple[list[float], dict[str, Any]]] = {}

    def ensure_collection(self) -> None:
        return None

    def collection_exists(self) -> bool:
        return True

    def delete_collection(self) -> None:
        self._points.clear()

    def upsert_chunks(self, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> int:
        if len(chunks) != len(embeddings):
            raise VectorIndexError(
                f"chunk/vector count mismatch: {len(chunks)} chunks vs {len(embeddings)} vectors"
            )
        for chunk, vector in zip(chunks, embeddings):
            if len(vector) != self.dimensions:
                raise VectorIndexError(
                    f"vector dimension mismatch: expected {self.dimensions}, got {len(vector)}"
                )
            payload = {
                "organization_id": str(chunk["organization_id"]),
                "document_id": str(chunk["document_id"]),
                "chunk_id": str(chunk["chunk_id"]),
                "chunk_index": chunk.get("index", 0),
                "text": chunk.get("text", ""),
                "section_heading": chunk.get("section_heading"),
                "parent_chunk_id": chunk.get("parent_chunk_id"),
                "content_hash": chunk.get("content_hash"),
                "token_count": chunk.get("token_count"),
                "chunk_strategy": chunk.get("strategy"),
                "document_version": chunk.get("document_version", 1),
                "access_scope": chunk.get("access_scope") or "organization",
                "source_id": str(chunk["source_id"]) if chunk.get("source_id") else None,
                "metadata": chunk.get("metadata") or {},
            }
            self._points[str(chunk["chunk_id"])] = (list(vector), payload)
        return len(chunks)

    def search(
        self,
        vector: list[float],
        organization_id: str,
        top_k: int = 8,
        document_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        access_scopes: list[str] | None = None,
        document_version: int | None = None,
    ) -> list[dict[str, Any]]:
        if len(vector) != self.dimensions:
            raise VectorIndexError(
                f"query vector dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )

        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(y * y for y in b)) or 1.0
            return dot / (na * nb)

        scored = []
        for point_id, (vec, payload) in self._points.items():
            if payload["organization_id"] != str(organization_id):
                continue  # hard org filter
            if document_ids and str(payload["document_id"]) not in {str(d) for d in document_ids}:
                continue
            if source_ids and not payload.get("source_id"):
                continue
            if source_ids and str(payload.get("source_id")) not in {str(s) for s in source_ids}:
                continue
            if access_scopes:
                scope = payload.get("access_scope") or "organization"
                if scope not in set(access_scopes):
                    continue
            if document_version is not None and int(payload.get("document_version") or 1) != int(document_version):
                continue
            scored.append((cosine(vector, vec), payload))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "chunk_id": p["chunk_id"],
                "document_id": p["document_id"],
                "organization_id": p["organization_id"],
                "chunk_index": p.get("chunk_index"),
                "text": p.get("text", ""),
                "metadata": p.get("metadata") or {},
                "section_heading": p.get("section_heading"),
                "parent_chunk_id": p.get("parent_chunk_id"),
                "content_hash": p.get("content_hash"),
                "document_version": p.get("document_version"),
                "access_scope": p.get("access_scope"),
                "source_id": p.get("source_id"),
                "score": score,
            }
            for score, p in scored[:top_k]
        ]

    def delete_document(self, organization_id: str, document_id: str) -> int:
        to_delete = [
            pid
            for pid, (_v, p) in self._points.items()
            if p["organization_id"] == str(organization_id) and p["document_id"] == str(document_id)
        ]
        for pid in to_delete:
            self._points.pop(pid, None)
        return len(to_delete)

    def count_for_document(self, organization_id: str, document_id: str) -> int:
        return sum(
            1
            for (_v, p) in self._points.values()
            if p["organization_id"] == str(organization_id) and p["document_id"] == str(document_id)
        )

    def health(self) -> dict[str, Any]:
        return {"healthy": True, "backend": "memory", "points": len(self._points)}
