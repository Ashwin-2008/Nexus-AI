"""add approval expiry

Revision ID: 0012_agent_approval_expiry
Revises: 0011_agent_execution_retries
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_agent_approval_expiry"
down_revision: Union[str, None] = "0011_agent_execution_retries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_approval_requests", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_approval_requests", "expires_at")
