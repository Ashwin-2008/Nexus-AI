"""add report metadata"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0013_reports"
down_revision: Union[str, None] = "0012_agent_approval_expiry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("agent_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("file_format", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])
    op.create_index("ix_reports_user_id", "reports", ["user_id"])
    op.create_index("ix_reports_execution_id", "reports", ["execution_id"])
    op.create_index("ix_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_table("reports")
