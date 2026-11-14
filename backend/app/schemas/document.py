from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IngestionJobRead(BaseModel):
    id: uuid.UUID
    status: str
    attempt: int
    max_attempts: int
    task_id: Optional[str] = None
    worker: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    uploaded_by: Optional[uuid.UUID] = None
    filename: str
    content_type: str
    file_size: int
    storage_backend: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias="doc_metadata")
    latest_job: Optional[IngestionJobRead] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentList(BaseModel):
    items: list[DocumentRead]
