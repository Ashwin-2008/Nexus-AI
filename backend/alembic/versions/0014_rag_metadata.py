"""RAG metadata: document versions, chunk provenance, query telemetry, evaluations"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_rag_metadata"
down_revision: Union[str, None] = "0013_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- documents: hash, connector linkage, version, access scope -------------
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("source_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("documents", sa.Column("access_scope", sa.String(32), nullable=False, server_default="organization"))
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_foreign_key(
        "fk_documents_source_id_data_sources",
        "documents",
        "data_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- document_chunks: full technical chunk metadata ------------------------
    op.add_column("document_chunks", sa.Column("section_heading", sa.String(512), nullable=True))
    op.add_column("document_chunks", sa.Column("parent_chunk_id", sa.Uuid(), nullable=True))
    op.add_column("document_chunks", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("document_chunks", sa.Column("token_count", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("chunk_strategy", sa.String(32), nullable=True))
    op.add_column("document_chunks", sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("document_chunks", sa.Column("access_scope", sa.String(32), nullable=False, server_default="organization"))
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])

    # -- document_versions ------------------------------------------------------
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_strategy", sa.String(32), nullable=True),
        sa.Column("embedding_provider", sa.String(64), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="indexed"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_document_versions_doc_version"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_organization_id", "document_versions", ["organization_id"])
    op.create_index("ix_document_versions_status", "document_versions", ["status"])

    # -- rag_query_logs ---------------------------------------------------------
    op.create_table(
        "rag_query_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False, server_default="hybrid"),
        sa.Column("filters", sa.Text(), nullable=True),
        sa.Column("retrieved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reranked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_mode", sa.String(24), nullable=True),
        sa.Column("verification_status", sa.String(32), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rag_query_logs_organization_id", "rag_query_logs", ["organization_id"])
    op.create_index("ix_rag_query_logs_user_id", "rag_query_logs", ["user_id"])
    op.create_index("ix_rag_query_logs_conversation_id", "rag_query_logs", ["conversation_id"])
    op.create_index("ix_rag_query_logs_trace_id", "rag_query_logs", ["trace_id"])

    # -- rag_evaluation_runs ----------------------------------------------------
    op.create_table(
        "rag_evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dataset_name", sa.String(255), nullable=False, server_default="inline"),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rag_evaluation_runs_organization_id", "rag_evaluation_runs", ["organization_id"])
    op.create_index("ix_rag_evaluation_runs_user_id", "rag_evaluation_runs", ["user_id"])
    op.create_index("ix_rag_evaluation_runs_status", "rag_evaluation_runs", ["status"])


def downgrade() -> None:
    op.drop_table("rag_evaluation_runs")
    op.drop_table("rag_query_logs")
    op.drop_table("document_versions")

    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_column("document_chunks", "access_scope")
    op.drop_column("document_chunks", "document_version")
    op.drop_column("document_chunks", "chunk_strategy")
    op.drop_column("document_chunks", "token_count")
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("document_chunks", "parent_chunk_id")
    op.drop_column("document_chunks", "section_heading")

    op.drop_constraint("fk_documents_source_id_data_sources", "documents", type_="foreignkey")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "access_scope")
    op.drop_column("documents", "version")
    op.drop_column("documents", "source_id")
    op.drop_column("documents", "content_hash")
