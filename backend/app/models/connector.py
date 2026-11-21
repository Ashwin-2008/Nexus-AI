"""Connector models: data sources and sync jobs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DataSource(Base):
    """A configured external data source (connector).

    `config` holds non-secret connection settings (host, url, query, ...).
    `credentials_encrypted` holds secrets (passwords, tokens) encrypted at
    rest with Fernet; it is never returned by the API.
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # postgres | mysql | rest | website | github | gdrive | email
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active | error | disabled
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet token of JSON
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sync_jobs: Mapped[list["ConnectorSyncJob"]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan", order_by="ConnectorSyncJob.started_at.desc()"
    )
    organization = relationship("Organization")


class ConnectorSyncJob(Base):
    """One execution of a connector sync."""

    __tablename__ = "connector_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")  # queued|running|succeeded|failed
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    data_source: Mapped["DataSource"] = relationship(back_populates="sync_jobs")
