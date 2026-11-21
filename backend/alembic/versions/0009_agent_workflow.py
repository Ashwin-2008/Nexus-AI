"""add durable agent steps, events, and approvals

Revision ID: 0009_agent_workflow
Revises: 0008_agent_executions
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_agent_workflow"
down_revision: Union[str, None] = "0008_agent_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_indexes(table: str, columns: list[str]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column], unique=False)


def upgrade() -> None:
    op.create_table(
        "agent_execution_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _common_indexes("agent_execution_steps", ["execution_id", "status"])
    op.create_table(
        "agent_execution_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_execution_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _common_indexes("agent_execution_events", ["execution_id", "step_id"])
    op.create_table(
        "agent_approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("action_summary", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="high"),
        sa.Column("requested_permissions", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["execution_id"], ["agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["agent_execution_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _common_indexes("agent_approval_requests", ["execution_id", "step_id", "organization_id", "status"])


def downgrade() -> None:
    for table, columns in (
        ("agent_approval_requests", ["status", "organization_id", "step_id", "execution_id"]),
        ("agent_execution_events", ["step_id", "execution_id"]),
        ("agent_execution_steps", ["status", "execution_id"]),
    ):
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_table("agent_approval_requests")
    op.drop_table("agent_execution_events")
    op.drop_table("agent_execution_steps")
