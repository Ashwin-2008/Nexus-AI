"""Request/response schemas for the RAG API."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RagFiltersIn(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    document_version: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RagQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    filters: RagFiltersIn | None = None
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool | None = None
    verify: bool | None = None
    conversation_id: str | None = Field(default=None, max_length=100)
    max_context_tokens: int | None = Field(default=None, ge=256, le=32000)
    include_evidence: bool = True

    model_config = ConfigDict(extra="forbid")


class RagRetrievalIn(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    filters: RagFiltersIn | None = None
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=100)
    rerank: bool | None = None
    include_text: bool = True

    model_config = ConfigDict(extra="forbid")


class RagIngestTextIn(BaseModel):
    content: str = Field(min_length=1)
    filename: str = Field(default="text.txt", max_length=255)
    title: str | None = Field(default=None, max_length=500)
    content_type: str = Field(default="text/plain", max_length=150)
    source_id: uuid.UUID | None = None
    access_scope: Literal["organization", "private", "admin"] = "organization"
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RagEvaluationIn(BaseModel):
    dataset: str | None = Field(default=None, max_length=100)
    items: list[dict[str, Any]] | None = None
    name: str = Field(default="evaluation", max_length=255)
    mode: Literal["hybrid", "dense", "sparse"] | None = None
    k: int = Field(default=5, ge=1, le=50)
    generate: bool = False
    persist: bool = True

    model_config = ConfigDict(extra="forbid")


class RagEvaluationItemIn(BaseModel):
    query: str
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    tags: list[str] = Field(default_factory=list)
