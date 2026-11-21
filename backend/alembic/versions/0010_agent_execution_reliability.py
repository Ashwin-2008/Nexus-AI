"""add agent execution claiming and retry metadata

Revision ID: 0010_agent_execution_reliability
Revises: 0009_agent_workflow
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_agent_execution_reliability"
down_revision: Union[str, None] = "0009_agent_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_executions", sa.Column("task_id", sa.String(255), nullable=True))
    op.add_column("agent_executions", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_executions_task_id", "agent_executions", ["task_id"], unique=False)
    op.add_column("agent_execution_steps", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("agent_execution_steps", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("agent_execution_steps", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_agent_execution_steps_execution_key", "agent_execution_steps", ["execution_id", "step_key"])


def downgrade() -> None:
    op.drop_constraint("uq_agent_execution_steps_execution_key", "agent_execution_steps", type_="unique")
    op.drop_column("agent_execution_steps", "claimed_at")
    op.drop_column("agent_execution_steps", "max_retries")
    op.drop_column("agent_execution_steps", "last_error")
    op.drop_index("ix_agent_executions_task_id", table_name="agent_executions")
    op.drop_column("agent_executions", "claimed_at")
    op.drop_column("agent_executions", "task_id")
