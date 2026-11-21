"""add agent execution retry count

Revision ID: 0011_agent_execution_retries
Revises: 0010_agent_execution_reliability
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_agent_execution_retries"
down_revision: Union[str, None] = "0010_agent_execution_reliability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_executions", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("agent_executions", "retry_count")
