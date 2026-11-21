"""add durable agent execution records

Revision ID: 0008_agent_executions
Revises: 0007_connectors
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_agent_executions"
down_revision: Union[str, None] = "0007_connectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_type", sa.String(length=64), nullable=False, server_default="supervisor"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_executions_organization_id"), "agent_executions", ["organization_id"], unique=False)
    op.create_index(op.f("ix_agent_executions_user_id"), "agent_executions", ["user_id"], unique=False)
    op.create_index(op.f("ix_agent_executions_status"), "agent_executions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_executions_status"), table_name="agent_executions")
    op.drop_index(op.f("ix_agent_executions_user_id"), table_name="agent_executions")
    op.drop_index(op.f("ix_agent_executions_organization_id"), table_name="agent_executions")
    op.drop_table("agent_executions")
