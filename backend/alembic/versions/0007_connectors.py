"""add data sources and connector sync jobs

Revision ID: 0007_connectors
Revises: 0006_chat
Create Date: 2026-11-15 14:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_connectors"
down_revision: Union[str, None] = "0006_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_sources_organization_id"), "data_sources", ["organization_id"], unique=False)
    op.create_index(op.f("ix_data_sources_type"), "data_sources", ["type"], unique=False)

    op.create_table(
        "connector_sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_connector_sync_jobs_data_source_id"), "connector_sync_jobs", ["data_source_id"], unique=False)
    op.create_index(op.f("ix_connector_sync_jobs_organization_id"), "connector_sync_jobs", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_connector_sync_jobs_organization_id"), table_name="connector_sync_jobs")
    op.drop_index(op.f("ix_connector_sync_jobs_data_source_id"), table_name="connector_sync_jobs")
    op.drop_table("connector_sync_jobs")
    op.drop_index(op.f("ix_data_sources_type"), table_name="data_sources")
    op.drop_index(op.f("ix_data_sources_organization_id"), table_name="data_sources")
    op.drop_table("data_sources")
