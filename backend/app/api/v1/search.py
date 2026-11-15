from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import search_service
from app.services.embeddings import EmbeddingError

router = APIRouter(prefix="/search", tags=["search"])


class SearchHitOut(BaseModel):
    chunk_id: str
    document_id: str
    document_filename: str
    chunk_index: int
    text: str
    provenance: list[dict] = []
    score: float
    mode: str
    metadata: dict = {}


class SearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    hits: list[SearchHitOut]


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=512, description="Search query text"),
    mode: Literal["semantic", "lexical", "hybrid"] = Query("hybrid"),
    top_k: int = Query(8, ge=1, le=50),
    document_ids: str | None = Query(None, description="Comma-separated document UUIDs to restrict search"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search the organization's indexed knowledge.

    All modes are scoped to the authenticated user's organization: results can
    never include another organization's documents or chunks.
    """
    org_id = current_user.organization_id
    doc_ids = None
    if document_ids:
        doc_ids = [d.strip() for d in document_ids.split(",") if d.strip()]

    try:
        if mode == "semantic":
            hits = search_service.semantic_search(org_id, q, top_k, doc_ids)
            hits = search_service.attach_document_info(db, org_id, hits)
        elif mode == "lexical":
            hits = search_service.lexical_search(db, org_id, q, top_k, doc_ids)
        else:
            hits = search_service.hybrid_search(db, org_id, q, top_k, doc_ids)
            hits = search_service.attach_document_info(db, org_id, hits)
    except EmbeddingError as e:
        raise HTTPException(status_code=503, detail={
            "code": "embedding_unavailable",
            "message": f"Semantic search unavailable: {e}",
        })
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={
            "code": "search_unavailable",
            "message": f"Search backend error: {e}",
        })

    return SearchResponse(
        query=q,
        mode=mode,
        total=len(hits),
        hits=[
            SearchHitOut(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_filename=h.document_filename,
                chunk_index=h.chunk_index,
                text=h.text,
                provenance=h.provenance,
                score=h.score,
                mode=h.mode,
                metadata=h.metadata or {},
            )
            for h in hits
        ],
    )
